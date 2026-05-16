"""
server.py
─────────
FastAPI entry point for the car driving assistant.

Replaces main.py — the assistant is now started and stopped
via the /assistant/start and /assistant/stop API endpoints,
controlled from the React dashboard.

Run:
    uvicorn server:app --reload --port 8000

The React frontend is served from /frontend/dist after building:
    cd frontend && npm run build
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

import shared.config  as config # noqa: F401 — triggers load_dotenv() and env validation
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import assistant, live, preferences, sessions
from db.database import init_db
from shared.observability import setup_observability

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("server")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # Startup
    setup_observability()
    await init_db()
    logger.info("Server ready — open http://localhost:8000 in your browser")
    yield
    # Shutdown — stop bridge if running
    from api.routes.assistant import _bridge_task
    if _bridge_task and not _bridge_task.done():
        _bridge_task.cancel()
    logger.info("Server shut down")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Car Assistant API",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the React dev server (port 5173) to call the API during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(sessions.router, prefix="/api")
app.include_router(preferences.router, prefix="/api")
app.include_router(assistant.router, prefix="/api")
app.include_router(live.router)

# ── Static frontend (production) ──────────────────────────────────────────────
# After `cd frontend && npm run build`, serve the built React app.
# Comment this out during development when using `npm run dev`.
import os
if os.path.exists("frontend/dist"):
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")