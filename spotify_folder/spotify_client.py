"""
spotify_client.py
─────────────────
Thin wrapper around the Spotipy library.
Every public method returns a plain string so the PydanticAI tools can
hand it straight back to the LLM as a tool result.

OAuth note
──────────
On first run Spotipy will open a browser to authenticate and cache the
token at SPOTIFY_CACHE_PATH (default: .spotify_cache). Subsequent runs
reuse the cached token silently. Make sure the Redirect URI in your
Spotify Developer Dashboard matches SPOTIFY_REDIRECT_URI in .env.

All credentials are read from config.py — no direct os.getenv() calls here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

import shared.config as config


# ── OAuth scopes ──────────────────────────────────────────────────────────────

_SCOPES = " ".join([
    "user-modify-playback-state",   # play, pause, skip, queue, shuffle, volume
    "user-read-playback-state",     # devices, current playback
    "user-read-currently-playing",  # currently playing track
    "playlist-read-private",        # search & play private playlists
])


@dataclass
class PlaybackInfo:
    name: str
    artist: str
    album: str
    is_playing: bool

    def __str__(self) -> str:
        status = "Playing" if self.is_playing else "Paused"
        return f'{status}: "{self.name}" by {self.artist} (from {self.album})'


class SpotifyClient:
    def __init__(self) -> None:
        self._sp = spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=config.SPOTIFY_CLIENT_ID,
                client_secret=config.SPOTIFY_CLIENT_SECRET,
                redirect_uri=config.SPOTIFY_REDIRECT_URI,
                scope=_SCOPES,
                cache_path=config.SPOTIFY_CACHE_PATH,
                open_browser=True,
            ),
            requests_timeout=10,
        )

    # ── Device helpers ────────────────────────────────────────────────────────

    def _active_device_id(self) -> Optional[str]:
        """Return the ID of the active device, or the first available one."""
        data = self._sp.devices()
        devices = (data or {}).get("devices", [])
        if not devices:
            return None
        active = [d for d in devices if d.get("is_active")]
        return active[0]["id"] if active else devices[0]["id"]

    def _require_device(self) -> tuple[bool, str]:
        """Return (ok, device_id_or_error_message)."""
        dev = self._active_device_id()
        if dev is None:
            return False, (
                "No active Spotify device found. "
                "Please open Spotify on any device first."
            )
        return True, dev

    def _safe(self, fn, *args, **kwargs) -> str:
        """Call fn; translate common Spotipy exceptions into user-friendly strings."""
        try:
            fn(*args, **kwargs)
            return "ok"
        except spotipy.SpotifyException as e:
            msg = str(e)
            if "Premium required" in msg or "PREMIUM_REQUIRED" in msg:
                return "This action requires a Spotify Premium account."
            if "NO_ACTIVE_DEVICE" in msg:
                return "No active Spotify device. Open Spotify and start playing something first."
            return f"Spotify error: {msg}"

    # ── Playback controls ─────────────────────────────────────────────────────

    def skip_to_next(self) -> str:
        ok, dev = self._require_device()
        if not ok:
            return dev
        result = self._safe(self._sp.next_track, device_id=dev)
        return "Skipped to next track." if result == "ok" else result

    def skip_to_previous(self) -> str:
        ok, dev = self._require_device()
        if not ok:
            return dev
        result = self._safe(self._sp.previous_track, device_id=dev)
        return "Went back to previous track." if result == "ok" else result

    def pause(self) -> str:
        ok, dev = self._require_device()
        if not ok:
            return dev
        result = self._safe(self._sp.pause_playback, device_id=dev)
        return "Playback paused." if result == "ok" else result

    def resume(self) -> str:
        ok, dev = self._require_device()
        if not ok:
            return dev
        result = self._safe(self._sp.start_playback, device_id=dev)
        return "Playback resumed." if result == "ok" else result

    def set_volume(self, percent: int) -> str:
        percent = max(0, min(100, percent))
        ok, dev = self._require_device()
        if not ok:
            return dev
        result = self._safe(self._sp.volume, percent, device_id=dev)
        return f"Volume set to {percent} percent." if result == "ok" else result

    def toggle_shuffle(self, enabled: bool) -> str:
        ok, dev = self._require_device()
        if not ok:
            return dev
        result = self._safe(self._sp.shuffle, enabled, device_id=dev)
        label = "enabled" if enabled else "disabled"
        return f"Shuffle {label}." if result == "ok" else result

    # ── Search & play ─────────────────────────────────────────────────────────

    def search_and_play(self, query: str) -> str:
        """
        Search for tracks first; fall back to playlists for mood/genre queries.
        Plays the best match immediately.
        """
        ok, dev = self._require_device()
        if not ok:
            return dev

        # Try specific track search first
        track_results = self._sp.search(q=query, type="track", limit=5)
        tracks = (track_results or {}).get("tracks", {}).get("items", [])

        if tracks:
            track = tracks[0]
            result = self._safe(self._sp.start_playback, device_id=dev, uris=[track["uri"]])
            if result == "ok":
                artist = track["artists"][0]["name"]
                return f'Now playing "{track["name"]}" by {artist}.'
            return result

        # Fall back to playlist for mood/era/genre queries
        pl_results = self._sp.search(q=query, type="playlist", limit=5)
        playlists = [p for p in (pl_results or {}).get("playlists", {}).get("items", []) if p]

        if playlists:
            playlist = playlists[0]
            result = self._safe(
                self._sp.start_playback,
                device_id=dev,
                context_uri=playlist["uri"],
            )
            if result == "ok":
                return f'Playing playlist "{playlist["name"]}".'
            return result

        return f'Could not find anything for "{query}". Try rephrasing.'

    def add_to_queue(self, query: str) -> str:
        ok, dev = self._require_device()
        if not ok:
            return dev

        results = self._sp.search(q=query, type="track", limit=1)
        tracks = (results or {}).get("tracks", {}).get("items", [])
        if not tracks:
            return f'Could not find "{query}" to add to the queue.'

        track = tracks[0]
        result = self._safe(self._sp.add_to_queue, track["uri"], device_id=dev)
        if result == "ok":
            artist = track["artists"][0]["name"]
            return f'Added "{track["name"]}" by {artist} to the queue.'
        return result

    # ── Status ────────────────────────────────────────────────────────────────

    def get_now_playing(self) -> str:
        current = self._sp.currently_playing()
        if not current or not current.get("item"):
            return "Nothing is currently playing on Spotify."

        track = current["item"]
        info = PlaybackInfo(
            name=track["name"],
            artist=track["artists"][0]["name"],
            album=track["album"]["name"],
            is_playing=current.get("is_playing", False),
        )
        return str(info)

    def list_devices(self) -> str:
        data = self._sp.devices()
        devices = (data or {}).get("devices", [])
        if not devices:
            return "No Spotify devices found. Open Spotify on any device."
        lines = []
        for d in devices:
            active_marker = " active" if d.get("is_active") else ""
            lines.append(f"{d['name']} ({d['type']}){active_marker}")
        return "Available devices: " + ", ".join(lines) + "."
