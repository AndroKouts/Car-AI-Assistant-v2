"""
email_agent.py
──────────────
PydanticAI email agent with tools.

Role in the system
──────────────────
This agent is a **silent worker** — it is never called directly by the user
and never produces audio.  The Realtime orchestration layer invokes it
with a natural-language instruction derived from what the driver said, and
this agent returns a *plain-text string* that the Realtime model will then
speak aloud.

Guidelines for the system prompt
─────────────────────────────────
• Output must be short and TTS-friendly: no markdown, no bullet points,
  no headers.  Write as if dictating to a voice interface.
• Avoid walls of text; the Realtime model has to read this out.
• For lists (e.g. many unread emails) use natural spoken phrasing:
  "You have three unread emails. First, …  Second, …  Third, …"
• Always surface the most important information first.
• For errors, return a single clear sentence the driver can act on.
"""

from __future__ import annotations

import shared.config as config
from pydantic_ai import Agent

from email_folder.models import EmailAgentDeps
from email_folder.tools import (
    get_mailbox_info,
    list_emails,
    list_mail_folders,
    read_email,
    reply_to_email,
    search_emails,
    send_email,
)

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an email assistant running inside a hands-free car driving system.
Your output will be read aloud by a voice interface, so you must write in
plain spoken English — no markdown, no bullet symbols, no bold or italic text,
no numbered lists with digits.

CRITICAL OUTPUT RULES
1. Plain text only.  Never use *, -, #, or any other markdown syntax.
2. Keep responses short.  Aim for under 60 words unless reading a full email.
3. Use natural spoken phrasing for lists:
   "You have two unread emails. First, from Alice with subject Meeting tomorrow.
    Second, from Bob with subject Invoice attached."
4. When reading an email, give: Sender, Subject, Date, then the message body
   paraphrased or read verbatim if short.
5. Before sending or replying, always state the full details in one sentence
   and ask "Shall I send it?" — wait; do NOT send without a yes.
6. If a tool fails, say so in one plain sentence and suggest a next step.
7. Use real tool data only — never invent email content.
8. You are not talking to the driver directly; your text will be passed to
   a voice layer.  Write accordingly — as if writing a script to be read aloud.

CAPABILITIES
- List emails from any folder
- Search emails by keyword, sender, or subject
- Read the full content of an email
- List all folders with unread counts
- Reply to an email (reply or reply-all)
- Compose and send new emails
- Show account / mailbox info
"""


# ── Agent ─────────────────────────────────────────────────────────────────────

def build_email_agent() -> Agent[EmailAgentDeps, str]:
    """Build and return the email agent singleton."""
    agent: Agent[EmailAgentDeps, str] = Agent(
        model=config.SUB_AGENT_MODEL,
        deps_type=EmailAgentDeps,
        output_type=str,
        instructions=_SYSTEM_PROMPT,
        name="email-agent",
    )

    agent.tool(list_emails)
    agent.tool(search_emails)
    agent.tool(read_email)
    agent.tool(list_mail_folders)
    agent.tool(send_email)
    agent.tool(reply_to_email)
    agent.tool(get_mailbox_info)

    return agent


email_agent = build_email_agent()
