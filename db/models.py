"""
db/models.py
────────────
SQLAlchemy 2.0 ORM models for the car assistant.

Tables
──────
sessions        One row per drive session.
turns           One row per tool call (email or Spotify request).
email_actions   One row per email read/reply/send within a turn.
spotify_actions One row per Spotify action within a turn.
preferences     One row per user — configurable settings.

Design notes
────────────
- All primary keys are UUIDs stored as TEXT. We already generate session
  UUIDs in the bridge; turn and action IDs are generated here at insert time.
- Timestamps are stored as TEXT in ISO 8601 format (UTC). Simple, portable,
  and directly comparable as strings for ordering.
- JSON fields (priority_senders, blocked_senders) are stored as TEXT and
  serialised/deserialised by the service layer — keeps the model simple.
- All foreign keys use ondelete="CASCADE" so deleting a session cleans up
  all its turns and actions automatically.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    ended_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_email: Mapped[str] = mapped_column(Text, nullable=False)

    turns: Mapped[list["Turn"]] = relationship(
        "Turn", back_populates="session", cascade="all, delete-orphan"
    )


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[str] = mapped_column(Text, nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped["Session"] = relationship("Session", back_populates="turns")
    email_actions: Mapped[list["EmailAction"]] = relationship(
        "EmailAction", back_populates="turn", cascade="all, delete-orphan"
    )
    spotify_actions: Mapped[list["SpotifyAction"]] = relationship(
        "SpotifyAction", back_populates="turn", cascade="all, delete-orphan"
    )


class EmailAction(Base):
    __tablename__ = "email_actions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[str] = mapped_column(
        Text, ForeignKey("turns.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)   # read | reply | send
    email_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient: Mapped[str | None] = mapped_column(Text, nullable=True)

    turn: Mapped["Turn"] = relationship("Turn", back_populates="email_actions")


class SpotifyAction(Base):
    __tablename__ = "spotify_actions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[str] = mapped_column(
        Text, ForeignKey("turns.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)  # play | pause | skip | volume | queue
    track_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    artist: Mapped[str | None] = mapped_column(Text, nullable=True)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)

    turn: Mapped["Turn"] = relationship("Turn", back_populates="spotify_actions")


class Preference(Base):
    __tablename__ = "preferences"

    user_email: Mapped[str] = mapped_column(Text, primary_key=True)
    priority_senders: Mapped[str] = mapped_column(Text, default="[]")   # JSON array
    blocked_senders: Mapped[str] = mapped_column(Text, default="[]")    # JSON array
    assistant_voice: Mapped[str] = mapped_column(Text, default="alloy")
    sub_agent_model: Mapped[str] = mapped_column(Text, default="openai:gpt-4.1-mini")
    driving_mode: Mapped[int] = mapped_column(Integer, default=1)       # 1 = True