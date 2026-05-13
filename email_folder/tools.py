"""
tools.py
────────
PydanticAI tool functions registered on the email agent.

Each tool receives a RunContext[EmailAgentDeps] that carries the live
GraphClient instance, so all tools share one authenticated HTTP connection
for the lifetime of a single agent run.

Driving-context design rules applied here:
  • Return data is structured but concise — the agent prompt instructs the
    LLM to distil this further into short, scannable text.
  • Tools never raise unhandled exceptions; errors are returned as strings
    so the LLM can relay them gracefully to the user.
  • Heavy operations (reading full body) only happen when explicitly asked.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import RunContext

from email_folder.models import EmailAgentDeps, EmailDetail, EmailSummary

logger = logging.getLogger(__name__)



# ── Tool implementations ──────────────────────────────────────────────────────

async def list_emails(
    ctx: RunContext[EmailAgentDeps],
    folder: str = "Inbox",
    count: int = 10,
    unread_only: bool = False,
) -> list[dict[str, Any]]:
    """
    List the most recent emails from a mail folder.

    Parameters
    ----------
    folder      : Folder to list from. Common options: Inbox, SentItems,
                  Drafts, DeletedItems, Junk. Defaults to Inbox.
    count       : Number of emails to return (1–20). Defaults to 10.
    unread_only : If true, only return unread messages.

    Returns a list of email summaries suitable for a quick overview.
    """
    try:
        gc = ctx.deps.graph_client
        filter_str = "isRead eq false" if unread_only else None
        raw = await gc.list_messages(
            folder=folder,
            top=min(count, 20),
            filter_str=filter_str,
        )
        summaries = [
            EmailSummary.from_graph(m, folder=folder).model_dump()
            for m in raw
        ]
        return summaries
    except Exception as exc:
        logger.exception("list_emails failed")
        return [{"error": str(exc)}]


async def search_emails(
    ctx: RunContext[EmailAgentDeps],
    query: str,
    count: int = 10,
) -> list[dict[str, Any]]:
    """
    Search across ALL mail folders for emails matching a query.

    Parameters
    ----------
    query   : Free-text search string. Can include keywords like
              'subject:budget', 'from:alice@example.com', or just words
              that appear anywhere in the email.
    count   : Max number of results to return (1–20).

    Returns a list of matching email summaries with folder info.
    """
    try:
        gc = ctx.deps.graph_client
        raw = await gc.search_messages_global(query=query, top=min(count, 20))
        summaries = [
            EmailSummary.from_graph(m).model_dump()
            for m in raw
        ]
        return summaries
    except Exception as exc:
        logger.exception("search_emails failed")
        return [{"error": str(exc)}]


async def read_email(
    ctx: RunContext[EmailAgentDeps],
    email_id: str,
    mark_as_read: bool = True,
) -> dict[str, Any]:
    """
    Read the full content of a specific email by its ID.

    Parameters
    ----------
    email_id     : The 'id' field from a previous list_emails or
                   search_emails result.
    mark_as_read : Whether to mark the message as read after fetching.
                   Defaults to True (mirrors normal reading behaviour).

    Returns the full email including body text.
    """
    try:
        gc = ctx.deps.graph_client
        raw = await gc.get_message(email_id)
        detail = EmailDetail.from_graph(raw)
        if mark_as_read and not raw.get("isRead"):
            await gc.mark_as_read(email_id)
        return detail.model_dump()
    except Exception as exc:
        logger.exception("read_email failed")
        return {"error": str(exc)}


async def list_mail_folders(
    ctx: RunContext[EmailAgentDeps],
) -> list[dict[str, Any]]:
    """
    Return the list of mail folders in the user's mailbox.

    Useful when the user mentions a folder by name and you need to
    verify it exists or find its correct display name.
    """
    try:
        gc = ctx.deps.graph_client
        folders = await gc.list_folders()
        return [
            {
                "id": f.get("id"),
                "name": f.get("displayName"),
                "unread": f.get("unreadItemCount", 0),
                "total": f.get("totalItemCount", 0),
            }
            for f in folders
        ]
    except Exception as exc:
        logger.exception("list_mail_folders failed")
        return [{"error": str(exc)}]


async def send_email(
    ctx: RunContext[EmailAgentDeps],
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    importance: str = "normal",
) -> dict[str, Any]:
    """
    Compose and send a brand-new email from the user's mailbox.

    Parameters
    ----------
    to          : List of recipient email addresses (required).
    subject     : Subject line of the email (required).
    body        : Plain-text body of the email (required).
    cc          : Optional list of CC email addresses.
    importance  : 'low', 'normal', or 'high'. Defaults to 'normal'.

    Returns a status dict indicating success or failure.
    """
    if not to:
        return {"error": "At least one recipient is required."}
    if not subject.strip():
        return {"error": "Subject cannot be empty."}
    if not body.strip():
        return {"error": "Email body cannot be empty."}

    valid_importance = {"low", "normal", "high"}
    if importance not in valid_importance:
        importance = "normal"

    try:
        gc = ctx.deps.graph_client
        result = await gc.send_new_email(
            to=to,
            subject=subject,
            body=body,
            cc=cc or [],
            importance=importance,
        )
        return {
            "status": "sent",
            "to": to,
            "subject": subject,
            "message": "Email sent successfully.",
        }
    except Exception as exc:
        logger.exception("send_email failed")
        return {"error": str(exc)}


async def reply_to_email(
    ctx: RunContext[EmailAgentDeps],
    email_id: str,
    reply_body: str,
    reply_all: bool = False,
) -> dict[str, Any]:
    """
    Reply to an existing email by its ID.

    Parameters
    ----------
    email_id    : The 'id' of the email to reply to. Obtain this from
                  list_emails or search_emails.
    reply_body  : The plain-text content of your reply.
    reply_all   : If True, reply to all original recipients (Reply All).
                  Defaults to False (reply to sender only).

    Returns a status dict indicating success or failure.
    """
    if not reply_body.strip():
        return {"error": "Reply body cannot be empty."}
    try:
        gc = ctx.deps.graph_client
        result = await gc.reply_to_email(
            message_id=email_id,
            reply_body=reply_body,
            reply_all=reply_all,
        )
        return {
            "status": result.get("status", "accepted"),
            "reply_all": reply_all,
            "message": "Reply accepted by Microsoft Graph.",
        }
    except Exception as exc:
        logger.exception("reply_to_email failed")
        return {"error": str(exc)}


async def get_mailbox_info(
    ctx: RunContext[EmailAgentDeps],
) -> dict[str, Any]:
    """
    Return basic information about the signed-in user's mailbox
    (display name, email address).
    """
    try:
        gc = ctx.deps.graph_client
        me = await gc.get_me()
        return {
            "display_name": me.get("displayName"),
            "email": me.get("mail") or me.get("userPrincipalName"),
        }
    except Exception as exc:
        logger.exception("get_mailbox_info failed")
        return {"error": str(exc)}