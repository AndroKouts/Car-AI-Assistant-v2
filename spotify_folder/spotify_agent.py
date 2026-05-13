"""
spotify_agent.py
────────────────
PydanticAI Spotify agent with tools.

Role in the system
──────────────────
This agent is a **silent worker** — it is never called directly by the user
and never produces audio.  The Realtime orchestration layer invokes it
with a natural-language instruction derived from what the driver said, and
this agent returns a *plain-text string* that the Realtime model will then
speak aloud.

Guidelines for the system prompt
─────────────────────────────────
• Output must be short and TTS-friendly: no markdown, no bullet points.
• One or two sentences is almost always enough.
• Prefer action confirmation: "Playing Bohemian Rhapsody by Queen."
• On errors, one plain sentence, suggest a fix.
"""

from __future__ import annotations

from dataclasses import dataclass

import shared.config as config
from pydantic_ai import Agent, RunContext

from spotify_folder.spotify_client import SpotifyClient


# ── Dependency injection container ────────────────────────────────────────────

@dataclass
class SpotifyDeps:
    spotify: SpotifyClient


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a Spotify controller running inside a hands-free car driving system.
Your output will be read aloud by a voice interface, so you must write in
plain spoken English — no markdown, no bullet symbols, no bold or italic text.

CRITICAL OUTPUT RULES
1. Plain text only.  Never use *, -, #, or any markdown syntax.
2. Be very concise — one or two sentences maximum.
3. Confirm the action that was taken:
   "Playing Bohemian Rhapsody by Queen."
   "Volume set to 60 percent."
   "Shuffle is now on."
4. If an action fails, say so in one plain sentence and suggest what to try.
5. You are not talking to the driver directly; your text will be passed to
   a voice layer.  Write as a script to be read aloud, not a chat message.

TOOL SELECTION TABLE
Intent                     → Tool
Skip / next song           → skip_song
Previous / go back         → previous_song
Play a specific song       → play_track  (query: "Song Artist")
Play by artist             → play_track  (query: "artist:Name")
Mood / genre / era         → play_track  (query: "year:YYYY genre:X mood")
Pause                      → pause_playback
Resume / continue          → resume_playback
What's playing             → get_now_playing
Set volume                 → set_volume  (0–100 integer)
Shuffle on/off             → toggle_shuffle  (true/false)
Add to queue               → add_to_queue  (query: "Song Artist")
List devices               → list_devices

SPOTIFY SEARCH TIPS
- Specific track:  "Blinding Lights The Weeknd"
- By artist:       "artist:Dua Lipa"
- Era + mood:      "year:2000-2009 upbeat pop"
- Genre:           "genre:indie rock 90s"
"""


# ── Agent ─────────────────────────────────────────────────────────────────────

agent: Agent[SpotifyDeps, str] = Agent(
    config.SUB_AGENT_MODEL,
    deps_type=SpotifyDeps,
    instructions=_SYSTEM_PROMPT,
    instrument=True,
    output_type=str,
    name="spotify-agent",
)


# ── Tools ─────────────────────────────────────────────────────────────────────

@agent.tool
async def skip_song(ctx: RunContext[SpotifyDeps]) -> str:
    """Skip to the next track in the queue."""
    return ctx.deps.spotify.skip_to_next()


@agent.tool
async def previous_song(ctx: RunContext[SpotifyDeps]) -> str:
    """Go back to the previous track."""
    return ctx.deps.spotify.skip_to_previous()


@agent.tool
async def play_track(ctx: RunContext[SpotifyDeps], query: str) -> str:
    """
    Search for and immediately play a track or playlist.

    Args:
        query: Spotify search query — track+artist, artist:Name,
               or mood/era/genre combo like "year:2000-2009 feel-good pop".
    """
    return ctx.deps.spotify.search_and_play(query)


@agent.tool
async def pause_playback(ctx: RunContext[SpotifyDeps]) -> str:
    """Pause the current playback."""
    return ctx.deps.spotify.pause()


@agent.tool
async def resume_playback(ctx: RunContext[SpotifyDeps]) -> str:
    """Resume or start playback on the active device."""
    return ctx.deps.spotify.resume()


@agent.tool
async def get_now_playing(ctx: RunContext[SpotifyDeps]) -> str:
    """Return what is currently playing on Spotify."""
    return ctx.deps.spotify.get_now_playing()


@agent.tool
async def set_volume(ctx: RunContext[SpotifyDeps], percent: int) -> str:
    """
    Set the playback volume.

    Args:
        percent: Volume level 0 (mute) to 100 (maximum).
    """
    return ctx.deps.spotify.set_volume(percent)


@agent.tool
async def toggle_shuffle(ctx: RunContext[SpotifyDeps], enabled: bool) -> str:
    """
    Enable or disable shuffle mode.

    Args:
        enabled: True = shuffle on, False = shuffle off.
    """
    return ctx.deps.spotify.toggle_shuffle(enabled)


@agent.tool
async def add_to_queue(ctx: RunContext[SpotifyDeps], query: str) -> str:
    """
    Search for a track and add it to the playback queue.

    Args:
        query: Search query, e.g. "Mr. Brightside The Killers".
    """
    return ctx.deps.spotify.add_to_queue(query)


@agent.tool
async def list_devices(ctx: RunContext[SpotifyDeps]) -> str:
    """List all available Spotify devices and show which is active."""
    return ctx.deps.spotify.list_devices()


# Expose the Spotify agent and its deps class for import by the orchestrator
spotify_agent = agent
