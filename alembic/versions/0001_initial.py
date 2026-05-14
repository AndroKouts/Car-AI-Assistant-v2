"""
alembic/versions/0001_initial.py
─────────────────────────────────
Initial migration — creates all tables.

Generated against db/models.py. Run with:
    alembic upgrade head
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("ended_at", sa.Text, nullable=True),
        sa.Column("user_email", sa.Text, nullable=False),
    )

    op.create_table(
        "turns",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("session_id", sa.Text, sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp", sa.Text, nullable=False),
        sa.Column("transcript", sa.Text, nullable=True),
        sa.Column("intent", sa.Text, nullable=True),
        sa.Column("instruction", sa.Text, nullable=True),
        sa.Column("result", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
    )

    op.create_table(
        "email_actions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("session_id", sa.Text, sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_id", sa.Text, sa.ForeignKey("turns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("email_id", sa.Text, nullable=True),
        sa.Column("subject", sa.Text, nullable=True),
        sa.Column("sender_email", sa.Text, nullable=True),
        sa.Column("recipient", sa.Text, nullable=True),
    )

    op.create_table(
        "spotify_actions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("session_id", sa.Text, sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_id", sa.Text, sa.ForeignKey("turns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("track_name", sa.Text, nullable=True),
        sa.Column("artist", sa.Text, nullable=True),
        sa.Column("query", sa.Text, nullable=True),
    )

    op.create_table(
        "preferences",
        sa.Column("user_email", sa.Text, primary_key=True),
        sa.Column("priority_senders", sa.Text, nullable=False, server_default="[]"),
        sa.Column("blocked_senders", sa.Text, nullable=False, server_default="[]"),
        sa.Column("assistant_voice", sa.Text, nullable=False, server_default="alloy"),
        sa.Column("sub_agent_model", sa.Text, nullable=False, server_default="openai:gpt-4.1-mini"),
        sa.Column("driving_mode", sa.Integer, nullable=False, server_default="1"),
    )

    # Indexes for common query patterns
    op.create_index("ix_sessions_user_email", "sessions", ["user_email"])
    op.create_index("ix_turns_session_id", "turns", ["session_id"])
    op.create_index("ix_email_actions_session_id", "email_actions", ["session_id"])
    op.create_index("ix_spotify_actions_session_id", "spotify_actions", ["session_id"])


def downgrade() -> None:
    op.drop_table("preferences")
    op.drop_table("spotify_actions")
    op.drop_table("email_actions")
    op.drop_table("turns")
    op.drop_table("sessions")
