"""
alembic/versions/0002_preferences_update.py
────────────────────────────────────────────
Add new preference columns:
  - microsoft_email
  - default_volume
  - startup_playlist
  - preferred_device

Run with: alembic upgrade head
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("preferences", sa.Column("microsoft_email", sa.Text, nullable=False, server_default=""))
    op.add_column("preferences", sa.Column("default_volume", sa.Integer, nullable=False, server_default="50"))
    op.add_column("preferences", sa.Column("startup_playlist", sa.Text, nullable=False, server_default=""))
    op.add_column("preferences", sa.Column("preferred_device", sa.Text, nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("preferences", "preferred_device")
    op.drop_column("preferences", "startup_playlist")
    op.drop_column("preferences", "default_volume")
    op.drop_column("preferences", "microsoft_email")
