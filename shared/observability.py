"""
observability.py
────────────────
Single-layer observability via the Langfuse v4 SDK.

Langfuse v4 is OTel-native: get_client() registers a global OTel
TracerProvider that exports directly to Langfuse.  Calling
Agent.instrument_all() tells pydantic-ai to emit its spans into that
same provider, so every LLM call, tool invocation, and retry appears in
Langfuse automatically — no separate logfire wiring required.

Each user command is wrapped with start_as_current_observation() so it
becomes a named root span in Langfuse, grouped by session_id and tagged.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from langfuse import get_client, propagate_attributes
from pydantic_ai.agent import Agent


# ── Startup ──────────────────────────────────────────────────────────────────

def setup_observability() -> "LangfuseObserver":
    """
    Call once at startup, before any agents are created.

    Reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL
    from the environment.  Registers Langfuse's OTel TracerProvider globally
    and enables pydantic-ai instrumentation against it.
    """
    get_client()           # initialises Langfuse + registers global TracerProvider
    Agent.instrument_all() # pydantic-ai emits spans into Langfuse's provider
    return LangfuseObserver()


# ── Per-command trace wrapper ─────────────────────────────────────────────────

class _TraceHandle:
    """Returned by LangfuseObserver.trace_command(); caller marks success/error."""

    def __init__(self, span) -> None:  # type: ignore[type-arg]
        self._span = span

    def success(self, output: str) -> None:
        self._span.update(output={"response": output})

    def error(self, message: str) -> None:
        self._span.update(output={"error": message}, metadata={"status": "error"})


class LangfuseObserver:
    """
    Wraps each user command in a Langfuse root span so all child
    observations (pydantic-ai model calls, tool calls, etc.) are grouped
    under a single named trace in the Langfuse UI.
    """

    @contextmanager
    def trace_command(
        self,
        command: str,
        session_id: str,
        name: str = "agent-command",
        tags: list[str] | None = None,
    ) -> Generator[_TraceHandle, None, None]:
        lf = get_client()
        with lf.start_as_current_observation(
            as_type="span",
            name=name,
            input={"command": command},
        ) as span:
            with propagate_attributes(
                session_id=session_id,
                tags=tags or [],
            ):
                yield _TraceHandle(span)

        # Flush after every command so traces appear in the UI promptly.
        lf.flush()

    def shutdown(self) -> None:
        get_client().shutdown()