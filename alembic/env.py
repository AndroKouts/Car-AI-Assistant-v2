"""
alembic/env.py
──────────────
Async-aware Alembic migration environment.

Uses SQLAlchemy's async engine pattern so migrations run correctly with
asyncpg. The DATABASE_URL is read from config.py — never hardcoded here.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

import shared.config as config
from db.models import Base

# Alembic Config object — gives access to values in alembic.ini
alembic_config = context.config

# Set up Python logging from the ini file
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# Metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — generates SQL without a DB connection.
    Useful for reviewing migrations before applying them.
    """
    context.configure(
        url=config.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode with an async engine."""
    connectable = create_async_engine(config.DATABASE_URL)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
