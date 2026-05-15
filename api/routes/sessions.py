"""
api/routes/sessions.py
──────────────────────
Session history endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.database import get_session as db_session
from db.models import EmailAction, Session, SpotifyAction, Turn
from sqlalchemy import select

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ── Response schemas ──────────────────────────────────────────────────────────

class SessionOut(BaseModel):
    id: str
    started_at: str
    ended_at: str | None
    user_email: str
    turn_count: int = 0

    class Config:
        from_attributes = True


class TurnOut(BaseModel):
    id: str
    timestamp: str
    transcript: str | None
    intent: str | None
    instruction: str | None
    result: str | None
    duration_ms: int | None

    class Config:
        from_attributes = True


class EmailActionOut(BaseModel):
    id: str
    timestamp: str
    action: str
    subject: str | None
    sender_email: str | None
    recipient: str | None

    class Config:
        from_attributes = True


class SpotifyActionOut(BaseModel):
    id: str
    timestamp: str
    action: str
    track_name: str | None
    artist: str | None
    query: str | None

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SessionOut])
async def list_sessions(limit: int = 20):
    """Return the most recent drive sessions."""
    async with db_session() as db:
        result = await db.execute(
            select(Session)
            .order_by(Session.started_at.desc())
            .limit(limit)
        )
        sessions = result.scalars().all()

        # Attach turn counts
        out = []
        for s in sessions:
            turn_result = await db.execute(
                select(Turn).where(Turn.session_id == s.id)
            )
            turns = turn_result.scalars().all()
            out.append(SessionOut(
                id=s.id,
                started_at=s.started_at,
                ended_at=s.ended_at,
                user_email=s.user_email,
                turn_count=len(turns),
            ))
        return out


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str):
    """Return a single session by ID."""
    async with db_session() as db:
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        turn_result = await db.execute(
            select(Turn).where(Turn.session_id == session_id)
        )
        turns = turn_result.scalars().all()
        return SessionOut(
            id=session.id,
            started_at=session.started_at,
            ended_at=session.ended_at,
            user_email=session.user_email,
            turn_count=len(turns),
        )


@router.get("/{session_id}/turns", response_model=list[TurnOut])
async def get_turns(session_id: str):
    """Return all turns for a session ordered by time."""
    async with db_session() as db:
        result = await db.execute(
            select(Turn)
            .where(Turn.session_id == session_id)
            .order_by(Turn.timestamp.asc())
        )
        return result.scalars().all()


@router.get("/{session_id}/spotify", response_model=list[SpotifyActionOut])
async def get_spotify_actions(session_id: str):
    """Return all Spotify actions for a session."""
    async with db_session() as db:
        result = await db.execute(
            select(SpotifyAction)
            .where(SpotifyAction.session_id == session_id)
            .order_by(SpotifyAction.timestamp.asc())
        )
        return result.scalars().all()


@router.get("/{session_id}/email", response_model=list[EmailActionOut])
async def get_email_actions(session_id: str):
    """Return all email actions for a session."""
    async with db_session() as db:
        result = await db.execute(
            select(EmailAction)
            .where(EmailAction.session_id == session_id)
            .order_by(EmailAction.timestamp.asc())
        )
        return result.scalars().all()
