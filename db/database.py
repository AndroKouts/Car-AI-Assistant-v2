"""
db/database.py
──────────────
Async SQLAlchemy engine, session factory, and database initialisation.

Usage
─────
Call init_db() once at startup (in main.py) to create tables if they don't
exist. Use get_session() as an async context manager for all DB operations:

    async with get_session() as session:
        session.add(some_model)
        await session.commit()

The engine is module-level and reused across all calls — SQLAlchemy's async
engine manages its own connection pool (asyncpg under the hood).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import shared.config as config
from db.models import Base

logger = logging.getLogger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────

engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,          # set True temporarily to see SQL in logs
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # verify connections before use — handles Postgres restarts
)

# ── Session factory ───────────────────────────────────────────────────────────

_SessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # keep model attributes accessible after commit
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session, committing on success and rolling back on error."""
    async with _SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Initialisation ────────────────────────────────────────────────────────────

async def init_db() -> None:
    """
    Create all tables if they do not already exist.

    Called once at startup in main.py. In production you'd use Alembic
    migrations instead; this is the fast path for development.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database ready")
