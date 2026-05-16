"""
realtime_bridge.py
──────────────────
The single orchestration layer for the car driving assistant.

Responsibilities
────────────────
1. Maintain a persistent WebSocket connection to the OpenAI Realtime API.
2. Stream microphone audio in; stream model audio out to the speaker.
3. When the Realtime model fires a function-call tool, dispatch directly to
   the appropriate PydanticAI sub-agent and inject the result back.
4. Wrap every sub-agent call in a Langfuse trace span for observability.

Why no LangGraph
────────────────
The "orchestration" here is just: hear intent → call one of two agents →
speak result. That is a dispatch table, not a graph. LangGraph would add a
dependency and runtime overhead for zero architectural benefit. The bridge
IS the orchestrator — it is a straightforward asyncio event loop with a
match statement.

Architecture
────────────

  Driver speaks
       │ PCM 24 kHz
       ▼
  ┌─────────────────────────────────────────────────────────┐
  │   OpenAI Realtime API  (gpt-realtime-mini)              │
  │                                                         │
  │   • Listens (semantic VAD, auto turn detection)         │
  │   • Detects intent: email OR spotify                    │
  │   • Calls a tool with a short instruction string        │
  │   • Speaks the result back to the driver                │
  │                                                         │
  │   Tools registered:                                     │
  │     handle_email_request(instruction: str)              │
  │     handle_spotify_request(instruction: str)            │
  └───────────────────────┬─────────────────────────────────┘
                          │ response.function_call_arguments.done
                          ▼
  ┌─────────────────────────────────────────────────────────┐
  │   RealtimeBridge._handle_tool_call()                    │
  │                                                         │
  │   match tool_name:                                      │
  │     "handle_email_request"   → email_agent.run(...)     │
  │     "handle_spotify_request" → spotify_agent.run(...)   │
  │     _                        → fallback string          │
  └───────────────────────┬─────────────────────────────────┘
                          │ plain-text result string
                          ▼
  conversation.item.create (function_call_output)
       + response.create
                          │
                          ▼
              Realtime model speaks the answer

Cost strategy
─────────────
The Realtime model (expensive audio tokens) does ONLY: listen, detect intent,
extract a short instruction string, speak the answer. All actual reasoning is
done by the cheap sub-agents (gpt-4.1-mini / gpt-4o-mini).

Audio format
────────────
  Input:  PCM16, 24 kHz, mono
  Output: PCM16, 24 kHz, mono
  VAD:    semantic_vad (server-side, automatic turn detection)

Observability
─────────────
  • One Langfuse span per drive session   (name: "realtime-session")
  • One Langfuse span per sub-agent call  (name: "email-agent-call" /
                                                  "spotify-agent-call")
  • PydanticAI internal spans (LLM calls, tool calls) emitted automatically
    via Agent.instrument_all() into the same OTel provider.
  All spans are linked by session_id via propagate_attributes.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from shared.observability import LangfuseObserver
from db.service import DatabaseService
from api.routes.live import push_event


logger = logging.getLogger(__name__)

def import_config_user_email() -> str:
    """Lazy helper — reads AZURE_USER_EMAIL from config after load_dotenv."""
    import shared.config as config  # noqa: PLC0415
    return config.AZURE_USER_EMAIL

# ── Constants ─────────────────────────────────────────────────────────────────

REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime-mini"

AUDIO_SAMPLE_RATE  = 24_000
AUDIO_CHANNELS     = 1
AUDIO_FRAME_BYTES  = 2           # int16 = 2 bytes per sample
CHUNK_DURATION_MS  = 100         # send audio in 100 ms chunks
CHUNK_FRAMES       = int(AUDIO_SAMPLE_RATE * CHUNK_DURATION_MS / 1000)
CHUNK_BYTES        = CHUNK_FRAMES * AUDIO_FRAME_BYTES * AUDIO_CHANNELS


# ── Realtime session configuration ───────────────────────────────────────────

_REALTIME_INSTRUCTIONS = """\
You are a concise hands-free driving assistant. The driver talks to you while
driving a car. You have exactly two capabilities:

1. EMAIL — anything to do with emails (reading, searching, replying, sending).
2. SPOTIFY — anything to do with music playback (play, pause, skip, volume,
   shuffle, queue).

ROUTING RULES
─────────────
• If the driver's request is email-related, call handle_email_request with a
  short plain-English instruction describing what they want.
• If the driver's request is music/Spotify-related, call
  handle_spotify_request with a short plain-English instruction describing
  what they want.
• After the tool returns, speak the result naturally in one or two sentences.
  Do not read out JSON, code, or raw data. Summarise if needed.
• If you are unsure which tool to use, ask one clarifying question.
• For anything outside email or Spotify, say you can only help with those two
  things.

CONFIRMATION FOR DESTRUCTIVE EMAIL ACTIONS
──────────────────────────────────────────
Before calling handle_email_request for a send or reply action, confirm the
key details with the driver in a single yes/no question. Do not send without
a confirmation.

STYLE
─────
• Very brief — one or two sentences maximum when speaking.
• Driving context — safety first. No long monologues.
• Speak in the same language the driver uses.
• Be warm but efficient.
"""

_REALTIME_TOOLS = [
    {
        "type": "function",
        "name": "handle_email_request",
        "description": (
            "Handle any email-related driver request. "
            "Pass a concise English instruction describing what the driver wants."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": (
                        "Short natural-language instruction. Examples: "
                        "'List my 5 most recent unread emails', "
                        "'Read the last email from Alice', "
                        "'Reply to Bob saying I will be 10 minutes late'."
                    ),
                }
            },
            "required": ["instruction"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "handle_spotify_request",
        "description": (
            "Control Spotify playback on behalf of the driver. "
            "Pass a concise English instruction describing what the driver wants."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": (
                        "Short natural-language instruction. Examples: "
                        "'Skip to the next song', "
                        "'Play some 90s rock', "
                        "'Set the volume to 40 percent', "
                        "'What is currently playing'."
                    ),
                }
            },
            "required": ["instruction"],
            "additionalProperties": False,
        },
    },
]


# ── RealtimeBridge ────────────────────────────────────────────────────────────

class RealtimeBridge:
    """
    Manages a single Realtime API WebSocket session for the drive.

    Usage:
        bridge = RealtimeBridge(observer, email_deps, spotify_deps)
        await bridge.run()          # blocks until session ends
    """

    def __init__(
        self,
        observer: LangfuseObserver,
        email_deps: Any | None,
        spotify_deps: Any | None,
        db: DatabaseService | None = None,
    ) -> None:
        self._observer    = observer
        self._email_deps   = email_deps
        self._spotify_deps = spotify_deps
        self._db = db

        # Unique ID for this drive session — used to group all Langfuse spans
        self._session_id: str = str(uuid.uuid4())

        self._ws: ClientConnection | None = None

        # PCM audio chunks to play; None is a flush/end-of-turn sentinel
        self._audio_out: asyncio.Queue[bytes | None] = asyncio.Queue()

        # FIX: Keep strong references to background tasks so they aren't
        # garbage-collected before completion, and log any unhandled exceptions.
        self._tasks: set[asyncio.Task] = set()

        # Accumulate streamed function-call argument deltas keyed by item_id
        # Structure: { item_id: {"name": str, "call_id": str, "args": str} }
        self._pending_calls: dict[str, dict[str, str]] = {}

        # Maps call_id → transcript so we can attach driver speech to a turn
        self._pending_transcripts: dict[str, str] = {}
        # Holds the most recent driver transcript not yet assigned to a turn
        self._latest_transcript: str | None = None

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Open the Realtime WebSocket and run the session.
        Blocks until the session ends or is cancelled (Ctrl+C).
        """
        import shared.config as config  # noqa: PLC0415
        headers = {
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        }

        # Wrap the entire session in one Langfuse root span
        # trace_command is a sync contextmanager — use `with`, not `async with`
        with self._observer.trace_command(
            command="drive-session",
            session_id=self._session_id,
            name="realtime-session",
            tags=["realtime", "drive", "assistant"],
        ) as session_trace:
            try:
                async with websockets.connect(
                    REALTIME_URL,
                    additional_headers=headers,
                    # Keep the connection alive with pings
                    ping_interval=20,
                    ping_timeout=30,
                ) as ws:
                    self._ws = ws
                    logger.info(
                        "Connected to Realtime API  session_id=%s", self._session_id
                    )
                    await self._configure_session()

                      # Record session start
                    if self._db:
                        asyncio.create_task(
                            self._db.create_session(
                                self._session_id,
                                import_config_user_email(),
                            )
                        )
                    
                    asyncio.create_task(push_event({"type": "session", "active": True}))
                    asyncio.create_task(push_event({"type": "state", "state": "listening"}))

                    # Run all three loops concurrently; if any raises the
                    # others are cancelled
                    await asyncio.gather(
                        self._event_loop(),
                        self._mic_producer(),
                        self._speaker_consumer(),
                    )

                    # Record session end
                    if self._db:
                        asyncio.create_task(
                            self._db.end_session(self._session_id)
                        )

                    asyncio.create_task(push_event({"type": "session", "active": False}))
                    asyncio.create_task(push_event({"type": "state", "state": "idle"}))

                session_trace.success("session ended normally")

            except asyncio.CancelledError:
                session_trace.success("session cancelled by user")
                raise
            except Exception as exc:
                session_trace.error(str(exc))
                logger.exception("Session error: %s", exc)
                raise
            finally:
                # FIX: hard-clear any calls that never completed — guards
                # against leaks when the session ends due to a network error
                # before response.done had a chance to fire.
                if self._pending_calls:
                    logger.warning(
                        "Session teardown: discarding %d incomplete pending call(s): %s",
                        len(self._pending_calls),
                        list(self._pending_calls.keys()),
                    )
                    self._pending_calls.clear()

    # ── Session configuration ─────────────────────────────────────────────────

    async def _configure_session(self) -> None:
        await self._send({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": "gpt-realtime-mini",
                "instructions": _REALTIME_INSTRUCTIONS,

                "audio": {
                    "output": {
                        "voice": "alloy"
                    }
                },

                "output_modalities": ["audio"],
                "tools": _REALTIME_TOOLS,
                "tool_choice": "auto",
            }
        })

    # ── WebSocket event loop ──────────────────────────────────────────────────

    async def _event_loop(self) -> None:
        """
        Main receive loop. Reads server events and dispatches them.

        Tool calls are handled in background tasks so audio streaming is
        never stalled while a sub-agent is running.
        """
        ws = self._ws
        if ws is None:
            raise RuntimeError("WebSocket is not connected")

        async for raw in ws:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON message from Realtime API")
                continue

            etype = event.get("type", "")

            match etype:

                case "session.created" | "session.updated":
                    sid = event.get("session", {}).get("id", "?")
                    logger.info("Realtime session ready  id=%s", sid)

                case "input_audio_buffer.speech_started":
                    logger.debug("Driver: started speaking")
                    asyncio.create_task(push_event({
                        "type": "state",
                        "state": "listening"
                    }))

                case "input_audio_buffer.speech_stopped":
                    logger.debug("Driver: stopped speaking")
                    asyncio.create_task(push_event({
                        "type": "state",
                        "state": "processing"
                    }))

                # ── Streaming audio output ────────────────────────────────

                case "response.output_audio.delta" | "response.audio.delta":
                    delta_b64 = event.get("delta", "")

                    asyncio.create_task(push_event({
                        "type": "state",
                        "state": "speaking"
                    }))

                    if delta_b64:
                        await self._audio_out.put(base64.b64decode(delta_b64))

                case "response.output_audio.done" | "response.audio.done":
                    await self._audio_out.put(None)

                    asyncio.create_task(push_event({
                        "type": "state",
                        "state": "listening"
                    }))

                # ── Transcript (for logging / debugging only) ─────────────

                case "response.audio_transcript.delta":
                    delta = event.get("delta", "")

                    logger.debug("Model: %s", delta)

                    if delta:
                        asyncio.create_task(push_event({
                            "type": "transcript",
                            "role": "assistant",
                            "text": delta,
                            "final": False,
                        }))

                case "conversation.item.input_audio_transcription.completed":
                    transcript = event.get("transcript", "")

                    logger.info(
                        "Driver said: %r",
                        transcript,
                    )

                    self._latest_transcript = transcript

                    if transcript:
                        asyncio.create_task(push_event({
                            "type": "transcript",
                            "role": "user",
                            "text": transcript,
                            "final": True,
                        }))

                # ── Function call argument streaming ──────────────────────

                case "response.function_call_arguments.delta":
                    # Accumulate argument JSON as it streams in
                    item_id     = event.get("item_id", "")
                    delta       = event.get("delta", "")
                    response_id = event.get("response_id", "")
                    if item_id not in self._pending_calls:
                        self._pending_calls[item_id] = {
                            "name":        event.get("name", ""),
                            "call_id":     event.get("call_id", ""),
                            "args":        "",
                            # FIX: track which response owns this call so we
                            # can purge orphans when response.done fires.
                            "response_id": response_id,
                        }
                    self._pending_calls[item_id]["args"] += delta

                case "response.function_call_arguments.done":
                    # Arguments fully received — dispatch to sub-agent
                    item_id  = event.get("item_id", "")
                    name     = event.get("name", "")
                    call_id  = event.get("call_id", "")
                    # Prefer the accumulated buffer; fall back to the event
                    # field (some server versions send everything at once)
                    args_raw = event.get("arguments", "")

                    if item_id in self._pending_calls:
                        accumulated = self._pending_calls.pop(item_id)
                        if not args_raw:
                            args_raw = accumulated["args"]
                        if not name:
                            name = accumulated["name"]
                        if not call_id:
                            call_id = accumulated["call_id"]

                    # FIX: Store task reference to prevent silent GC, and
                    # attach a done-callback that logs any unhandled exception.
                    task = asyncio.create_task(
                        self._handle_tool_call(name, call_id, args_raw),
                        name=f"tool-{call_id or item_id}",
                    )
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                    task.add_done_callback(self._log_task_exception)

                case "response.done":
                    # FIX: purge any _pending_calls entries that belong to
                    # this response but never received a .done event (dropped
                    # connection, server error, interrupted response, etc.).
                    # Without this they would leak for the lifetime of the session.
                    finished_response_id = event.get("response", {}).get("id", "")
                    if finished_response_id:
                        orphans = [
                            iid for iid, meta in self._pending_calls.items()
                            if meta.get("response_id") == finished_response_id
                        ]
                        for iid in orphans:
                            dropped = self._pending_calls.pop(iid)
                            logger.warning(
                                "Dropped orphaned pending call  item_id=%s  name=%s  "
                                "response_id=%s  partial_args=%r",
                                iid,
                                dropped["name"],
                                finished_response_id,
                                dropped["args"][:80],
                            )
                    logger.debug("Response complete  id=%s", finished_response_id)

                case "error":
                    err = event.get("error", {})
                    logger.error(
                        "Realtime API error  code=%s message=%s",
                        err.get("code"),
                        err.get("message"),
                    )

                case _:
                    # Silently ignore bookkeeping events we don't need
                    pass

    # ── Task exception logger ─────────────────────────────────────────────────

    @staticmethod
    def _log_task_exception(task: asyncio.Task) -> None:
        """
        Done-callback attached to every background tool-call task.

        If the task raised an unhandled exception, log it as an error so it
        is never silently swallowed. CancelledError is not an error — ignore it.
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "Unhandled exception in background task %r: %s",
                task.get_name(),
                exc,
                exc_info=exc,
            )

    # ── Tool call dispatch (the actual orchestration) ─────────────────────────

    async def _handle_tool_call(
        self,
        name: str,
        call_id: str,
        args_raw: str,
    ) -> None:
        """
        Parse a Realtime tool call, run the matching sub-agent, and inject
        the plain-text result back into the session.

        This is the entirety of the "orchestration" layer. It is intentionally
        simple: a match statement over the two tool names.
        """
        # Parse arguments
        try:
            args = json.loads(args_raw) if args_raw else {}
        except json.JSONDecodeError:
            args = {}

        instruction: str = args.get("instruction", "").strip()
        if not instruction:
            instruction = name.replace("_", " ")

        logger.info("Tool call  name=%s  instruction=%r", name, instruction)

        # Capture and clear the latest transcript so it belongs to this turn
        transcript = self._latest_transcript
        self._latest_transcript = None
 
        # Track timing for the DB record
        import time  # noqa: PLC0415
        start_ms = int(time.monotonic() * 1000)

        # Dispatch and trace
        match name:
            case "handle_email_request":
                intent = "email"
                result = await self._run_email_agent(instruction)
            case "handle_spotify_request":
                intent = "spotify"
                result = await self._run_spotify_agent(instruction)
            case _:
                intent = "unknown"
                logger.warning("Unknown tool: %s", name)
                result = (
                    "I am not sure how to handle that. "
                    "I can help with emails or Spotify."
                )
        
        asyncio.create_task(push_event({
            "type": "action",
            "intent": intent,
            "text": result
        }))

        duration_ms = int(time.monotonic() * 1000) - start_ms
 
        # Write turn + action to DB (fire-and-forget)
        if self._db:
            asyncio.create_task(
                self._persist_turn(
                    intent=intent,
                    instruction=instruction,
                    result=result,
                    duration_ms=duration_ms,
                    transcript=transcript,
                )
            )

        # Feed the result back to the Realtime model so it can speak it
        await self._return_tool_result(call_id, result)

    # ── Sub-agent runners ─────────────────────────────────────────────────────

    async def _run_email_agent(self, instruction: str) -> str:
        """Run the email PydanticAI agent and return a TTS-ready string."""
        if self._email_deps is None:
            return "Email is not configured. Please check your credentials."

        from email_folder.email_agent import email_agent  # lazy import avoids circular deps

        with self._observer.trace_command(
            command=instruction,
            session_id=self._session_id,
            name="email-agent-call",
            tags=["email", "sub-agent"],
        ) as handle:
            try:
                run_result = await email_agent.run(instruction, deps=self._email_deps)
                result = run_result.output
                handle.success(result)
                logger.info("email_agent  result=%r", result[:120])
            except Exception as exc:
                result = f"Sorry, I could not access your email right now. {exc}"
                handle.error(str(exc))
                logger.exception("email_agent error: %s", exc)

        return result

    async def _run_spotify_agent(self, instruction: str) -> str:
        """Run the Spotify PydanticAI agent and return a TTS-ready string."""
        if self._spotify_deps is None:
            return "Spotify is not configured. Please check your credentials."

        from spotify_folder.spotify_agent import spotify_agent  # lazy import

        with self._observer.trace_command(
            command=instruction,
            session_id=self._session_id,
            name="spotify-agent-call",
            tags=["spotify", "sub-agent"],
        ) as handle:
            try:
                run_result = await spotify_agent.run(
                    instruction, deps=self._spotify_deps
                )
                result = run_result.output
                handle.success(result)
                logger.info("spotify_agent  result=%r", result[:120])
            except Exception as exc:
                result = f"Sorry, I could not control Spotify right now. {exc}"
                handle.error(str(exc))
                logger.exception("spotify_agent error: %s", exc)

        return result
    

    # ── DB persistence ────────────────────────────────────────────────────────
 
    async def _persist_turn(
        self,
        intent: str,
        instruction: str,
        result: str,
        duration_ms: int,
        transcript: str | None,
    ) -> None:
        """
        Write a completed turn and its domain action to the database.
        Called as a fire-and-forget task — never raises to the caller.
        """
        if not self._db:
            return
        try:
            turn_id = await self._db.create_turn(
                session_id=self._session_id,
                intent=intent,
                instruction=instruction,
                result=result,
                duration_ms=duration_ms,
                transcript=transcript,
            )
            if turn_id is None:
                logger.warning("DB: skipping action insert — turn was not created")
                return
            if intent == "email":
                await self._db.create_email_action(
                    session_id=self._session_id,
                    turn_id=turn_id,
                    instruction=instruction,
                    result=result,
                )
            elif intent == "spotify":
                await self._db.create_spotify_action(
                    session_id=self._session_id,
                    turn_id=turn_id,
                    instruction=instruction,
                    result=result,
                )
        except Exception as exc:
            logger.warning("DB: _persist_turn failed: %s", exc)


    # ── Result injection ──────────────────────────────────────────────────────

    async def _return_tool_result(self, call_id: str, result: str) -> None:
        """
        Inject a sub-agent result back into the Realtime session.

        Step 1 — conversation.item.create (type: function_call_output):
            Tells the model what the tool returned.
        Step 2 — response.create:
            Triggers the model to generate a spoken response from that result.
        """
        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result,
            },
        })
        await self._send({
            "type": "response.create",
            "response": {
                "output_modalities": ["audio"],
            },
        })
        logger.debug("Injected tool result  call_id=%s  len=%d", call_id, len(result))

    # ── Audio I/O ─────────────────────────────────────────────────────────────

    async def _mic_producer(self) -> None:
        """
        Continuously read microphone input and stream it to the Realtime API
        as base64-encoded PCM16 chunks.

        Runs in an executor to avoid blocking the event loop on blocking
        pyaudio reads. If pyaudio is not installed, logs a warning and exits
        gracefully (useful for unit testing without audio hardware).
        """
        try:
            import pyaudio
        except ImportError:
            logger.warning("pyaudio is not installed — microphone input disabled.")
            try:
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass
            return

        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=AUDIO_CHANNELS,
            rate=AUDIO_SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_FRAMES,
        )
        loop = asyncio.get_running_loop()
        logger.debug("Microphone streaming started")

        try:
            while True:
                chunk: bytes = await loop.run_in_executor(
                    None,
                    lambda: stream.read(CHUNK_FRAMES, exception_on_overflow=False),
                )
                await self._send({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(chunk).decode(),
                })
        except asyncio.CancelledError:
            pass
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()
            logger.debug("Microphone streaming stopped")

    async def _speaker_consumer(self) -> None:
        """
        Dequeue PCM audio chunks produced by the Realtime model and play
        them through the default speaker.

        None in the queue is an end-of-turn sentinel; we just discard it
        (the stream plays synchronously so there is nothing to flush).
        If pyaudio is not installed the queue is drained silently.
        """
        try:
            import pyaudio
        except ImportError:
            logger.warning(
                "pyaudio is not installed — speaker output disabled.  "
                "Draining audio queue silently."
            )
            while True:
                await self._audio_out.get()
            return  # unreachable but satisfies linters

        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=AUDIO_CHANNELS,
            rate=AUDIO_SAMPLE_RATE,
            output=True,
        )
        loop = asyncio.get_running_loop()
        logger.debug("Speaker output started")

        try:
            while True:
                chunk = await self._audio_out.get()
                if chunk is None:
                    continue  # end-of-turn sentinel; stream already flushed
                # Write PCM to speaker in executor to avoid blocking
                await loop.run_in_executor(None, stream.write, chunk)
        except asyncio.CancelledError:
            pass
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()
            logger.debug("Speaker output stopped")

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _send(self, payload: dict) -> None:
        """Serialise payload as JSON and send over the WebSocket."""
        if self._ws is None:
            raise RuntimeError("WebSocket is not connected")
        await self._ws.send(json.dumps(payload))