"""
db/service.py
─────────────
DatabaseService — all database read and write operations.

Design principles
─────────────────
1. All public methods are async and safe to call with asyncio.create_task()
   from the bridge — a failure logs a warning but never raises to the caller.

2. The service owns all SQL; the bridge never imports SQLAlchemy directly.

3. Intent/action detection is done here via simple keyword matching on the
   instruction and result strings. This keeps the bridge clean — it just
   passes strings and lets the service figure out the semantics.

4. Timestamps are UTC ISO 8601 strings throughout.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

import shared.config as config
from db.database import get_session
from db.models import EmailAction, Preference, Session, SpotifyAction, Turn

logger = logging.getLogger(__name__)


def _now() -> str:
    """Return current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


# ── Action detection helpers ──────────────────────────────────────────────────

def _detect_email_action(instruction: str) -> str:
    """
    Infer the email action type from the instruction string.
    Returns one of: read | reply | send | list | search | other
    """
    instruction_lower = instruction.lower()
    if any(w in instruction_lower for w in ("reply", "respond")):
        return "reply"
    if any(w in instruction_lower for w in ("send", "compose", "write", "draft")):
        return "send"
    if any(w in instruction_lower for w in ("read", "open", "show me")):
        return "read"
    if any(w in instruction_lower for w in ("search", "find", "look for")):
        return "search"
    if any(w in instruction_lower for w in ("list", "inbox", "unread", "emails")):
        return "list"
    return "other"


def _detect_spotify_action(instruction: str) -> str:
    """
    Infer the Spotify action type from the instruction string.
    Returns one of: play | pause | skip | previous | volume | shuffle | queue | status | other
    """
    instruction_lower = instruction.lower()
    if any(w in instruction_lower for w in ("skip", "next")):
        return "skip"
    if any(w in instruction_lower for w in ("previous", "go back", "last song")):
        return "previous"
    if any(w in instruction_lower for w in ("pause", "stop")):
        return "pause"
    if any(w in instruction_lower for w in ("resume", "continue", "unpause")):
        return "resume"
    if any(w in instruction_lower for w in ("volume", "louder", "quieter", "turn up", "turn down")):
        return "volume"
    if "shuffle" in instruction_lower:
        return "shuffle"
    if any(w in instruction_lower for w in ("queue", "add to", "play next")):
        return "queue"
    if any(w in instruction_lower for w in ("playing", "what's on", "current")):
        return "status"
    if any(w in instruction_lower for w in ("play", "put on", "start")):
        return "play"
    return "other"


def _extract_track_info(result: str) -> tuple[str | None, str | None]:
    """
    Extract track name and artist from a Spotify result string.
    Result strings look like: 'Now playing "Song Name" by Artist Name.'
    Returns (track_name, artist) or (None, None) if not parseable.
    """
    import re
    match = re.search(r'"([^"]+)"\s+by\s+(.+?)\.?\s*$', result)
    if match:
        return match.group(1), match.group(2).strip()
    return None, None


# ── DatabaseService ───────────────────────────────────────────────────────────

class DatabaseService:
    """
    All database operations for the car assistant.

    Instantiated once in main.py and passed to RealtimeBridge.
    All methods are fire-and-forget safe — exceptions are caught and logged.
    """

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def create_session(self, session_id: str, user_email: str) -> None:
        """Record the start of a drive session."""
        try:
            async with get_session() as db:
                db.add(Session(
                    id=session_id,
                    started_at=_now(),
                    user_email=user_email,
                ))
            logger.debug("DB: session created  id=%s", session_id)
        except Exception as exc:
            logger.warning("DB: create_session failed: %s", exc)

    async def end_session(self, session_id: str) -> None:
        """Record the end time of a drive session."""
        try:
            async with get_session() as db:
                await db.execute(
                    update(Session)
                    .where(Session.id == session_id)
                    .values(ended_at=_now())
                )
            logger.debug("DB: session ended  id=%s", session_id)
        except Exception as exc:
            logger.warning("DB: end_session failed: %s", exc)

    # ── Turns ─────────────────────────────────────────────────────────────────

    async def create_turn(
        self,
        session_id: str,
        intent: str,
        instruction: str,
        result: str,
        duration_ms: int,
        transcript: str | None = None,
    ) -> str | None:
        """
        Record one complete tool-call turn.
        Returns the new turn ID so the caller can attach actions to it.
        """
        turn_id = _new_id()
        try:
            async with get_session() as db:
                db.add(Turn(
                    id=turn_id,
                    session_id=session_id,
                    timestamp=_now(),
                    transcript=transcript,
                    intent=intent,
                    instruction=instruction,
                    result=result,
                    duration_ms=duration_ms,
                ))
            logger.debug("DB: turn created  id=%s  intent=%s", turn_id, intent)
            return turn_id
        except Exception as exc:
            logger.warning("DB: create_turn failed: %s", exc)
            return None

    async def update_turn_transcript(self, turn_id: str, transcript: str) -> None:
        """Attach a driver transcript to an existing turn."""
        try:
            async with get_session() as db:
                await db.execute(
                    update(Turn)
                    .where(Turn.id == turn_id)
                    .values(transcript=transcript)
                )
        except Exception as exc:
            logger.warning("DB: update_turn_transcript failed: %s", exc)

    # ── Email actions ─────────────────────────────────────────────────────────

    async def create_email_action(
        self,
        session_id: str,
        turn_id: str,
        instruction: str,
        result: str,
        email_id: str | None = None,
        subject: str | None = None,
        sender_email: str | None = None,
        recipient: str | None = None,
    ) -> None:
        """Record an email action derived from a turn."""
        action = _detect_email_action(instruction)
        try:
            async with get_session() as db:
                db.add(EmailAction(
                    id=_new_id(),
                    session_id=session_id,
                    turn_id=turn_id,
                    timestamp=_now(),
                    action=action,
                    email_id=email_id,
                    subject=subject,
                    sender_email=sender_email,
                    recipient=recipient,
                ))
            logger.debug("DB: email_action  action=%s", action)
        except Exception as exc:
            logger.warning("DB: create_email_action failed: %s", exc)

    # ── Spotify actions ───────────────────────────────────────────────────────

    async def create_spotify_action(
        self,
        session_id: str,
        turn_id: str,
        instruction: str,
        result: str,
    ) -> None:
        """Record a Spotify action derived from a turn."""
        action = _detect_spotify_action(instruction)
        track_name, artist = _extract_track_info(result)
        try:
            async with get_session() as db:
                db.add(SpotifyAction(
                    id=_new_id(),
                    session_id=session_id,
                    turn_id=turn_id,
                    timestamp=_now(),
                    action=action,
                    track_name=track_name,
                    artist=artist,
                    query=instruction,
                ))
            logger.debug("DB: spotify_action  action=%s  track=%s", action, track_name)
        except Exception as exc:
            logger.warning("DB: create_spotify_action failed: %s", exc)

    # ── Preferences ───────────────────────────────────────────────────────────

    async def get_preferences(self, user_email: str) -> Preference | None:
        """Return the preference row for a user, or None if not yet created."""
        try:
            async with get_session() as db:
                result = await db.execute(
                    select(Preference).where(Preference.user_email == user_email)
                )
                return result.scalar_one_or_none()
        except Exception as exc:
            logger.warning("DB: get_preferences failed: %s", exc)
            return None

    async def ensure_preferences(self, user_email: str) -> Preference:
        """
        Return the preference row for a user, creating it with defaults
        if it doesn't exist yet.
        """
        try:
            async with get_session() as db:
                result = await db.execute(
                    select(Preference).where(Preference.user_email == user_email)
                )
                prefs = result.scalar_one_or_none()
                if prefs is None:
                    prefs = Preference(
                        user_email=user_email,
                        priority_senders="[]",
                        blocked_senders="[]",
                        assistant_voice="alloy",
                        sub_agent_model=config.SUB_AGENT_MODEL,
                        driving_mode=1,
                    )
                    db.add(prefs)
                return prefs
        except Exception as exc:
            logger.warning("DB: ensure_preferences failed: %s", exc)
            # Return a default in-memory object so the caller can continue
            return Preference(
                user_email=user_email,
                priority_senders="[]",
                blocked_senders="[]",
                assistant_voice="alloy",
                sub_agent_model=config.SUB_AGENT_MODEL,
                driving_mode=1,
            )
        
    
    async def update_preferences(
        self,
        user_email: str,
        microsoft_email: str | None = None,
        priority_senders: list[str] | None = None,
        blocked_senders: list[str] | None = None,
        default_volume: int | None = None,
        startup_playlist: str | None = None,
        preferred_device: str | None = None,
        assistant_voice: str | None = None,
        sub_agent_model: str | None = None,
        driving_mode: bool | None = None,
    ) -> Preference | None:
        """Update preference fields for a user. Only provided fields are updated."""
        try:
            async with get_session() as db:
                result = await db.execute(
                    select(Preference).where(Preference.user_email == user_email)
                )
                prefs = result.scalar_one_or_none()
                if prefs is None:
                    prefs = Preference(user_email=user_email)
                    db.add(prefs)
 
                if microsoft_email is not None:
                    prefs.microsoft_email = microsoft_email
                if priority_senders is not None:
                    prefs.priority_senders = json.dumps(priority_senders)
                if blocked_senders is not None:
                    prefs.blocked_senders = json.dumps(blocked_senders)
                if default_volume is not None:
                    prefs.default_volume = max(0, min(100, default_volume))
                if startup_playlist is not None:
                    prefs.startup_playlist = startup_playlist
                if preferred_device is not None:
                    prefs.preferred_device = preferred_device
                if assistant_voice is not None:
                    prefs.assistant_voice = assistant_voice
                if sub_agent_model is not None:
                    prefs.sub_agent_model = sub_agent_model
                if driving_mode is not None:
                    prefs.driving_mode = 1 if driving_mode else 0
 
                return prefs
        except Exception as exc:
            logger.warning("DB: update_preferences failed: %s", exc)
            return None

    async def get_priority_senders(self, user_email: str) -> list[str]:
        """Return the list of priority sender email addresses for a user."""
        prefs = await self.get_preferences(user_email)
        if prefs is None:
            return []
        try:
            return json.loads(prefs.priority_senders)
        except (json.JSONDecodeError, TypeError):
            return []

    async def get_blocked_senders(self, user_email: str) -> list[str]:
        """Return the list of blocked sender email addresses for a user."""
        prefs = await self.get_preferences(user_email)
        if prefs is None:
            return []
        try:
            return json.loads(prefs.blocked_senders)
        except (json.JSONDecodeError, TypeError):
            return []

    # ── Query helpers (for future dashboard) ─────────────────────────────────

    async def get_recent_sessions(self, user_email: str, limit: int = 10) -> list[Session]:
        """Return the most recent sessions for a user."""
        try:
            async with get_session() as db:
                result = await db.execute(
                    select(Session)
                    .where(Session.user_email == user_email)
                    .order_by(Session.started_at.desc())
                    .limit(limit)
                )
                return list(result.scalars().all())
        except Exception as exc:
            logger.warning("DB: get_recent_sessions failed: %s", exc)
            return []

    async def get_session_turns(self, session_id: str) -> list[Turn]:
        """Return all turns for a session, ordered by timestamp."""
        try:
            async with get_session() as db:
                result = await db.execute(
                    select(Turn)
                    .where(Turn.session_id == session_id)
                    .order_by(Turn.timestamp.asc())
                )
                return list(result.scalars().all())
        except Exception as exc:
            logger.warning("DB: get_session_turns failed: %s", exc)
            return []