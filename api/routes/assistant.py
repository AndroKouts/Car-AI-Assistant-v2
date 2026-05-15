"""
api/routes/assistant.py
───────────────────────
Start, stop, and query the assistant bridge.

The bridge runs as an asyncio Task inside the FastAPI process.
Starting creates the task; stopping cancels it cleanly.
The task reference lives in module-level state — safe because this
only runs on one machine for one user.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assistant", tags=["assistant"])

# Module-level task reference
_bridge_task: asyncio.Task | None = None
_bridge_instance: Any = None  # RealtimeBridge


# ── Schemas ───────────────────────────────────────────────────────────────────

class StatusOut(BaseModel):
    running: bool
    session_id: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=StatusOut)
async def get_status():
    """Return whether the assistant is currently running."""
    running = _bridge_task is not None and not _bridge_task.done()
    session_id = _bridge_instance._session_id if running and _bridge_instance else None
    return StatusOut(running=running, session_id=session_id)


@router.post("/start", response_model=StatusOut)
async def start_assistant():
    """Start the assistant bridge. No-op if already running."""
    global _bridge_task, _bridge_instance

    if _bridge_task is not None and not _bridge_task.done():
        raise HTTPException(status_code=409, detail="Assistant is already running")

    # Import here to avoid circular imports at module load
    from db.database import init_db
    from db.service import DatabaseService
    from email_folder.graph_client import GraphClient
    from email_folder.models import EmailAgentDeps
    from shared.observability import setup_observability
    from orchestration.realtime_bridge import RealtimeBridge
    from spotify_folder.spotify_agent import SpotifyDeps
    from spotify_folder.spotify_client import SpotifyClient
    import shared.config as config

    observer = setup_observability()

    spotify_deps = None
    try:
        spotify_deps = SpotifyDeps(spotify=SpotifyClient())
    except Exception as exc:
        logger.warning("Spotify unavailable: %s", exc)

    db = DatabaseService()

    async def _run():
        """Inner coroutine — opens GraphClient for the session lifetime."""
        async with GraphClient() as graph_client:
            email_deps = EmailAgentDeps(
                graph_client=graph_client,
                user_email=config.AZURE_USER_EMAIL,
                driving_mode=True,
            )
            bridge = RealtimeBridge(
                observer=observer,
                email_deps=email_deps,
                spotify_deps=spotify_deps,
                db=db,
            )
            global _bridge_instance
            _bridge_instance = bridge
            await bridge.run()

    _bridge_task = asyncio.create_task(_run(), name="bridge")
    logger.info("Assistant started")

    return StatusOut(running=True, session_id=None)


@router.post("/stop", response_model=StatusOut)
async def stop_assistant():
    """Stop the assistant bridge gracefully."""
    global _bridge_task, _bridge_instance

    if _bridge_task is None or _bridge_task.done():
        raise HTTPException(status_code=409, detail="Assistant is not running")

    _bridge_task.cancel()
    try:
        await asyncio.wait_for(_bridge_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    _bridge_task = None
    _bridge_instance = None
    logger.info("Assistant stopped")

    return StatusOut(running=False, session_id=None)
