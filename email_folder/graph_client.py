"""
graph_client.py
───────────────
Thin async wrapper around the Microsoft Graph REST API.

Authentication uses MSAL's Device Code Flow (delegated permissions):
  1. On first run the user visits a URL and enters a code — one-time setup.
  2. Tokens are cached to disk; subsequent runs refresh silently.
  3. No client secret needed — suitable for a personal-use driving agent.

All HTTP calls are made with httpx.AsyncClient for compatibility with
pydantic-ai's async tool execution.

Bug fixes applied in this version
───────────────────────────────────
1. Token baked into httpx headers at construction — expired after 1 h with
   no recovery.  Fixed: token fetched fresh per-request via _auth_header().
2. _headers() was dead code — never called by any request method.  Removed.
3. Account lookup used strict username match — different UPN casing caused
   silent fall-through to device flow on every run.  Fixed: iterate all
   cached accounts.
4. Blocking MSAL calls ran directly on the async event loop.  Fixed: all
   MSAL I/O offloaded to a thread via run_in_executor().
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
import msal

from shared.config import (
    AZURE_CLIENT_ID,
    AZURE_TENANT_ID,
    GRAPH_BASE_URL,
    GRAPH_SCOPES,
    MSAL_TOKEN_CACHE_PATH,
)

logger = logging.getLogger(__name__)


# ── Token cache (file-backed) ─────────────────────────────────────────────────

def _load_token_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if MSAL_TOKEN_CACHE_PATH.exists():
        cache.deserialize(MSAL_TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    return cache


def _save_token_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        MSAL_TOKEN_CACHE_PATH.write_text(
            cache.serialize(), encoding="utf-8"
        )


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _build_app(cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        client_id=AZURE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
        token_cache=cache,
    )


# ── Graph API client ──────────────────────────────────────────────────────────

class GraphClient:
    """
    Async Microsoft Graph API client with automatic mid-session token refresh.

    Usage:
        async with GraphClient() as client:
            emails = await client.list_messages(top=10)

    Token refresh strategy
    ──────────────────────
    Graph access tokens expire after ~1 hour.  We do NOT bake the token into
    the httpx.AsyncClient headers at construction time (original bug: once
    baked in, a stale token caused silent 401s with no recovery path).

    Instead, _auth_header() is called on every request.  It runs MSAL's
    silent-refresh flow in a thread pool (FIX 4) and MSAL's internal
    access-token cache means it only hits the network when the token is
    actually about to expire — overhead is negligible on 99 % of calls.
    """

    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None
        # Keep cache + app alive for the session so MSAL's in-memory
        # access-token cache is reused between calls.
        self._cache: msal.SerializableTokenCache = _load_token_cache()
        self._app: msal.PublicClientApplication = _build_app(self._cache)

    async def __aenter__(self) -> "GraphClient":
        # Eagerly authenticate so any device-code prompt appears at startup.
        await self._get_valid_token()
        # No Authorization header baked in — injected per-request (FIX 1+2).
        self._http = httpx.AsyncClient(
            base_url=GRAPH_BASE_URL,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._http:
            await self._http.aclose()

    # ── Token refresh ─────────────────────────────────────────────────────────

    async def _get_valid_token(self) -> str:
        """
        Return a valid access token, silently refreshing via the cached
        refresh token when needed.  Falls back to Device Code Flow if no
        usable token exists in the cache at all.

        FIX 3: iterate ALL cached accounts instead of filtering by username,
                avoiding silent fall-through when UPN casing differs.
        FIX 4: all MSAL calls run in a thread pool so the event loop is
                never blocked — especially important for device-flow which
                can wait up to 15 minutes for the user.
        """
        app = self._app
        cache = self._cache
        scopes = GRAPH_SCOPES

        def _refresh() -> str:
            # Try every cached account for a silent refresh (no user prompt).
            for account in app.get_accounts():
                result = app.acquire_token_silent(scopes, account=account)
                if result and "access_token" in result:
                    _save_token_cache(cache)
                    logger.debug(
                        "Silent token refresh OK for %s",
                        account.get("username", "?"),
                    )
                    return result["access_token"]

            # No usable cached token — Device Code Flow (one-time setup).
            flow = app.initiate_device_flow(scopes=scopes)
            if "user_code" not in flow:
                raise RuntimeError(
                    f"Failed to start device flow: {flow.get('error_description', flow)}"
                )
            print("\n" + "=" * 60)
            print("  MICROSOFT LOGIN REQUIRED (one-time setup)")
            print("=" * 60)
            print(flow["message"])
            print("=" * 60 + "\n")
            # Blocks the thread (safe — we're in run_in_executor).
            result = app.acquire_token_by_device_flow(flow)
            if "access_token" not in result:
                raise RuntimeError(
                    f"Authentication failed: {result.get('error_description', result)}"
                )
            _save_token_cache(cache)
            return result["access_token"]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _refresh)

    async def _auth_header(self) -> dict[str, str]:
        """
        FIX 1+2: per-request Authorization header built from a freshly
        validated token.  Replaces the dead _headers() method and the
        stale baked-in header approach.
        """
        token = await self._get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # ── Internal HTTP helpers ─────────────────────────────────────────────────

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        assert self._http is not None, "Use GraphClient as an async context manager"
        resp = await self._http.get(path, params=params, headers=await self._auth_header())
        if not resp.is_success:
            print(f"\n>>> GRAPH ERROR BODY: {resp.text}\n")   # temp debug line
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        assert self._http is not None
        resp = await self._http.post(path, json=body, headers=await self._auth_header())
        if not resp.is_success:
            print(f"\n>>> GRAPH ERROR BODY: {resp.text}\n")   # temp debug
        resp.raise_for_status()
        if resp.status_code == 202 or not resp.content:
            return {"status": "accepted"}
        return resp.json()

    async def _patch(self, path: str, body: dict[str, Any]) -> Any:
        assert self._http is not None
        resp = await self._http.patch(path, json=body, headers=await self._auth_header())
        if not resp.is_success:
            print(f"\n>>> GRAPH ERROR BODY: {resp.text}\n")   # temp debug
        resp.raise_for_status()
        return resp.json()

    # ── Mail folder operations ────────────────────────────────────────────────

    async def list_folders(self) -> list[dict[str, Any]]:
        """Return top-level mail folders for the signed-in user."""
        data = await self._get("/me/mailFolders", params={"$top": 20})
        return data.get("value", [])

    # ── Message listing / search ──────────────────────────────────────────────

    async def list_messages(
        self,
        folder: str = "Inbox",
        top: int = 10,
        search: str | None = None,
        filter_str: str | None = None,
        order_by: str = "receivedDateTime desc",
    ) -> list[dict[str, Any]]:
        """
        List messages from a folder with optional search/filter.

        Parameters
        ----------
        folder      : well-known folder name (Inbox, SentItems, Drafts, …)
                      or a folder ID.
        top         : max number of messages to return (1–50).
        search      : OData $search query string  (e.g. "subject:meeting")
        filter_str  : OData $filter expression    (e.g. "isRead eq false")
        order_by    : OData $orderby clause.
        """
        params: dict[str, Any] = {
            "$top": min(top, 50),
            "$orderby": order_by,
            "$select": (
                "id,subject,from,toRecipients,receivedDateTime,"
                "isRead,bodyPreview,hasAttachments,importance"
            ),
        }
        if search:
            params["$search"] = f'"{search}"'
        else:
            if filter_str:
                params["$filter"] = filter_str

        data = await self._get(f"/me/mailFolders/{folder}/messages", params=params)
        return data.get("value", [])

    async def search_messages_global(
        self,
        query: str,
        top: int = 10,
    ) -> list[dict[str, Any]]:
        """Search across all folders using $search on /me/messages."""
        params: dict[str, Any] = {
            "$search": f'"{query}"',
            "$top": min(top, 50),
            "$select": (
                "id,subject,from,toRecipients,receivedDateTime,"
                "isRead,bodyPreview,hasAttachments,importance,parentFolderId"
            ),
        }
        data = await self._get("/me/messages", params=params)
        return data.get("value", [])

    # ── Single message ────────────────────────────────────────────────────────

    async def get_message(self, message_id: str) -> dict[str, Any]:
        """Retrieve the full message including plain-text body."""
        return await self._get(
            f"/me/messages/{message_id}",
            params={
                "$select": (
                    "id,subject,from,toRecipients,ccRecipients,"
                    "receivedDateTime,body,isRead,importance"
                )
            },
        )

    async def mark_as_read(self, message_id: str) -> dict[str, Any]:
        """Mark a message as read."""
        return await self._patch(f"/me/messages/{message_id}", {"isRead": True})

    # ── Send / Reply ──────────────────────────────────────────────────────────

    async def send_new_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        importance: str = "normal",
        body_type: str = "Text",
    ) -> dict[str, Any]:
        """
        Compose and send a brand-new email.

        Parameters
        ----------
        to          : list of recipient email addresses
        subject     : email subject line
        body        : message body (plain text or HTML)
        cc          : optional list of CC addresses
        importance  : 'low' | 'normal' | 'high'
        body_type   : 'Text' | 'HTML'
        """
        def _recipient(addr: str) -> dict[str, Any]:
            return {"emailAddress": {"address": addr}}

        message: dict[str, Any] = {
            "subject": subject,
            "importance": importance,
            "body": {"contentType": body_type, "content": body},
            "toRecipients": [_recipient(a) for a in to],
        }
        if cc:
            message["ccRecipients"] = [_recipient(a) for a in cc]

        return await self._post("/me/sendMail", {"message": message, "saveToSentItems": True})

    async def reply_to_email(
        self,
        message_id: str,
        reply_body: str,
        reply_all: bool = False,
        body_type: str = "Text",
    ) -> dict[str, Any]:
        """
        Reply to an existing message.

        Parameters
        ----------
        message_id  : ID of the message to reply to
        reply_body  : the text of the reply
        reply_all   : if True, reply to all recipients
        body_type   : 'Text' | 'HTML'
        """
        endpoint = "replyAll" if reply_all else "reply"
        # Only "comment" is valid here — "message: {}" causes a 400 (fixed).
        body: dict[str, Any] = {
            "comment": reply_body,
        }
        return await self._post(f"/me/messages/{message_id}/{endpoint}", body)

    # ── User profile ──────────────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """Return basic profile info for the signed-in user."""
        return await self._get(
            "/me",
            params={"$select": "displayName,mail,userPrincipalName"},
        )