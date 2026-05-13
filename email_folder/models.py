"""
models.py
─────────
Pydantic models that describe structured email data.
Used for type-safe inter-module communication and agent deps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ── Lightweight email summary (returned by list / search tools) ───────────────

class EmailSummary(BaseModel):
    id: str
    subject: str
    sender_name: str
    sender_email: str
    received_at: str        # ISO 8601 string, kept as str to stay JSON-serialisable
    is_read: bool
    preview: str            # first ~255 chars of body
    has_attachments: bool
    importance: str         # low | normal | high
    folder: str = "unknown"

    @classmethod
    def from_graph(cls, msg: dict[str, Any], folder: str = "unknown") -> "EmailSummary":
        sender = msg.get("from", {}).get("emailAddress", {})
        return cls(
            id=msg["id"],
            subject=msg.get("subject") or "(no subject)",
            sender_name=sender.get("name", ""),
            sender_email=sender.get("address", ""),
            received_at=msg.get("receivedDateTime", ""),
            is_read=msg.get("isRead", False),
            preview=msg.get("bodyPreview", "")[:300],
            has_attachments=msg.get("hasAttachments", False),
            importance=msg.get("importance", "normal"),
            folder=folder,
        )

    def to_driving_summary(self) -> str:
        """
        Compact one-liner suitable for audio/driving context.
        Keeps information density low so the driver isn't overwhelmed.
        """
        read_flag = "" if self.is_read else "[UNREAD] "
        attach_flag = " [has attachment]" if self.has_attachments else ""
        imp_flag = " [IMPORTANT]" if self.importance == "high" else ""
        return (
            f"{read_flag}From {self.sender_name or self.sender_email} — "
            f'"{self.subject}"{imp_flag}{attach_flag} — {self.received_at[:10]}'
        )


# ── Full email (returned by read_email tool) ──────────────────────────────────

class EmailDetail(BaseModel):
    id: str
    subject: str
    sender_name: str
    sender_email: str
    to_recipients: list[str]
    cc_recipients: list[str]
    received_at: str
    body_text: str          # plain-text body (or HTML stripped to text)
    is_read: bool
    importance: str

    @classmethod
    def from_graph(cls, msg: dict[str, Any]) -> "EmailDetail":
        sender = msg.get("from", {}).get("emailAddress", {})
        body = msg.get("body", {})

        # Use plain-text content if available; otherwise use HTML as-is
        # (the LLM will handle basic HTML tags in its summarisation)
        body_text = body.get("content", "")
        if body.get("contentType", "").lower() == "html":
            # Very basic HTML strip — good enough for LLM context
            import re
            body_text = re.sub(r"<[^>]+>", " ", body_text)
            body_text = re.sub(r"\s{2,}", " ", body_text).strip()

        def _extract_addresses(field: list[dict]) -> list[str]:
            return [r.get("emailAddress", {}).get("address", "") for r in field]

        return cls(
            id=msg["id"],
            subject=msg.get("subject") or "(no subject)",
            sender_name=sender.get("name", ""),
            sender_email=sender.get("address", ""),
            to_recipients=_extract_addresses(msg.get("toRecipients", [])),
            cc_recipients=_extract_addresses(msg.get("ccRecipients", [])),
            received_at=msg.get("receivedDateTime", ""),
            body_text=body_text[:8000],   # cap at 8k chars to keep within context
            is_read=msg.get("isRead", False),
            importance=msg.get("importance", "normal"),
        )


# ── Agent dependencies ────────────────────────────────────────────────────────

@dataclass
class EmailAgentDeps:
    """
    Injected into every tool call via RunContext.deps.
    Carries the live GraphClient instance so tools share one HTTP connection.
    """
    graph_client: Any   # GraphClient (typed as Any to avoid circular imports)
    user_email: str     # the signed-in mailbox address
    driving_mode: bool = True   # agent keeps responses concise when True