"""
api/routes/live.py
──────────────────
WebSocket endpoint that streams real-time assistant events to the browser.

Architecture
────────────
The RealtimeBridge pushes events into a module-level asyncio.Queue
(EVENT_QUEUE) as it processes Realtime API events. The WebSocket endpoint
drains that queue and forwards events to any connected browser client.

Only one browser client is expected (personal use, single machine) so we
use a single queue rather than a pub/sub broadcaster.

Event schema
────────────
All events are JSON objects with a "type" field:

  { "type": "state",      "state": "idle|listening|processing|speaking" }
  { "type": "transcript", "role": "user|assistant", "text": "...", "final": bool }
  { "type": "action",     "intent": "email|spotify", "text": "..." }
  { "type": "session",    "active": true|false }

The frontend consumes these to drive the visualiser, transcript feed,
and action card.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["live"])

# ── Shared event queue ────────────────────────────────────────────────────────
# The bridge imports this and calls push_event() to emit events.
# The WebSocket endpoint drains it.

EVENT_QUEUE: asyncio.Queue[dict] = asyncio.Queue()


async def push_event(event: dict) -> None:
    """Called by the bridge to emit an event to the browser."""
    await EVENT_QUEUE.put(event)


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/live")
async def live_ws(websocket: WebSocket):
    """
    Persistent WebSocket connection to the browser.
    Drains EVENT_QUEUE and forwards each event as JSON.
    """
    await websocket.accept()
    logger.info("Live WebSocket client connected")

    try:
        while True:
            try:
                # Wait up to 1 second for an event, then send a keepalive ping
                event = await asyncio.wait_for(EVENT_QUEUE.get(), timeout=1.0)
                await websocket.send_text(json.dumps(event))
            except asyncio.TimeoutError:
                # Send a ping to keep the connection alive
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
    except WebSocketDisconnect:
        logger.info("Live WebSocket client disconnected")
    except Exception as exc:
        logger.warning("Live WebSocket error: %s", exc)
