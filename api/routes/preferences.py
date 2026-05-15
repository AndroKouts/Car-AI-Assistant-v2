"""
api/routes/preferences.py
─────────────────────────
Get and update user preferences.
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel, Field

import shared.config as config
from db.service import DatabaseService

router = APIRouter(prefix="/preferences", tags=["preferences"])
_db = DatabaseService()


# ── Schemas ───────────────────────────────────────────────────────────────────

class PreferencesOut(BaseModel):
    microsoft_email: str
    priority_senders: list[str]
    blocked_senders: list[str]
    default_volume: int
    startup_playlist: str
    preferred_device: str
    assistant_voice: str
    sub_agent_model: str
    driving_mode: bool


class PreferencesIn(BaseModel):
    microsoft_email: str = Field(default="")
    priority_senders: list[str] = Field(default_factory=list)
    blocked_senders: list[str] = Field(default_factory=list)
    default_volume: int = Field(default=50, ge=0, le=100)
    startup_playlist: str = Field(default="")
    preferred_device: str = Field(default="")
    assistant_voice: str = Field(default="alloy")
    sub_agent_model: str = Field(default="openai:gpt-4.1-mini")
    driving_mode: bool = Field(default=True)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=PreferencesOut)
async def get_preferences():
    """Return current preferences for the configured user."""
    prefs = await _db.ensure_preferences(config.AZURE_USER_EMAIL)
    return PreferencesOut(
        microsoft_email=prefs.microsoft_email or config.AZURE_USER_EMAIL,
        priority_senders=_parse_json_list(prefs.priority_senders),
        blocked_senders=_parse_json_list(prefs.blocked_senders),
        default_volume=prefs.default_volume,
        startup_playlist=prefs.startup_playlist or "",
        preferred_device=prefs.preferred_device or "",
        assistant_voice=prefs.assistant_voice,
        sub_agent_model=prefs.sub_agent_model,
        driving_mode=bool(prefs.driving_mode),
    )


@router.put("", response_model=PreferencesOut)
async def update_preferences(body: PreferencesIn):
    """Save updated preferences."""
    prefs = await _db.update_preferences(
        user_email=config.AZURE_USER_EMAIL,
        microsoft_email=body.microsoft_email,
        priority_senders=body.priority_senders,
        blocked_senders=body.blocked_senders,
        default_volume=body.default_volume,
        startup_playlist=body.startup_playlist,
        preferred_device=body.preferred_device,
        assistant_voice=body.assistant_voice,
        sub_agent_model=body.sub_agent_model,
        driving_mode=body.driving_mode,
    )
    if prefs is None:
        return PreferencesOut(
            microsoft_email="",
            priority_senders=[],
            blocked_senders=[],
            default_volume=50,
            startup_playlist="",
            preferred_device="",
            assistant_voice="default",
            sub_agent_model="gpt-4.1-mini",
            driving_mode=False,
        )
    return PreferencesOut(
        microsoft_email=prefs.microsoft_email or "",
        priority_senders=_parse_json_list(prefs.priority_senders),
        blocked_senders=_parse_json_list(prefs.blocked_senders),
        default_volume=prefs.default_volume,
        startup_playlist=prefs.startup_playlist or "",
        preferred_device=prefs.preferred_device or "",
        assistant_voice=prefs.assistant_voice,
        sub_agent_model=prefs.sub_agent_model,
        driving_mode=bool(prefs.driving_mode),
    )


def _parse_json_list(value: str) -> list[str]:
    try:
        return json.loads(value) if value else []
    except (json.JSONDecodeError, TypeError):
        return []
