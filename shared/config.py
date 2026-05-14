"""
config.py
─────────
Single source of truth for all configuration across the project.

Every module imports constants from here. No other module should call
os.getenv() or os.environ directly — all env var access is centralised here.

Calling `import config` at the top of main.py triggers load_dotenv() before
anything else runs, so all subsequent imports see the correct env vars.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present (no-op when vars are already set in the environment)
load_dotenv()


def _require(key: str) -> str:
    """Return the value of a required env var or raise a clear error."""
    val = os.getenv(key)
    if not val:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            "Copy .env.example to .env and fill in the values."
        )
    return val

# ── Database ─────────────────────────────────────────────────────────────────
 
# asyncpg connection URL — used by SQLAlchemy async engine and Alembic.
# Assembled from individual vars so each piece can be set independently.
_DB_USER     = os.getenv("POSTGRES_USER",     "assistant")
_DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "assistant")
_DB_HOST     = os.getenv("POSTGRES_HOST",     "localhost")
_DB_PORT     = os.getenv("POSTGRES_PORT",     "5432")
_DB_NAME     = os.getenv("POSTGRES_DB",       "car_assistant")
 
DATABASE_URL: str = (
    f"postgresql+asyncpg://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
)

# ── OpenAI ────────────────────────────────────────────────────────────────────

OPENAI_API_KEY: str = _require("OPENAI_API_KEY")

# Model used by both PydanticAI sub-agents (email + Spotify).
# Change here to upgrade both agents at once.
SUB_AGENT_MODEL: str = "openai:gpt-4.1-mini"

# ── Langfuse ──────────────────────────────────────────────────────────────────

LANGFUSE_PUBLIC_KEY: str = _require("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY: str = _require("LANGFUSE_SECRET_KEY")
LANGFUSE_BASE_URL: str = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

# ── Microsoft Graph / Azure ───────────────────────────────────────────────────

AZURE_CLIENT_ID: str = _require("AZURE_CLIENT_ID")
AZURE_TENANT_ID: str = os.getenv("AZURE_TENANT_ID", "common")
AZURE_USER_EMAIL: str = _require("AZURE_USER_EMAIL")

GRAPH_SCOPES: list[str] = [
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "User.Read",
]

GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"

# MSAL token cache — persisted to disk so login survives restarts
MSAL_TOKEN_CACHE_PATH: Path = Path(
    os.getenv("MSAL_TOKEN_CACHE", ".token_cache.json")
)

# ── Spotify ───────────────────────────────────────────────────────────────────

SPOTIFY_CLIENT_ID: str = _require("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET: str = _require("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI: str = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
)
# Token cache file — persisted to disk so OAuth survives restarts
SPOTIFY_CACHE_PATH: str = os.getenv("SPOTIFY_CACHE", ".spotify_cache")
