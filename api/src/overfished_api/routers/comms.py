"""Comms router — vessel audio warnings and phone calls."""

from __future__ import annotations

import os
import xml.sax.saxutils as saxutils
from pathlib import Path
from typing import Any

import requests as http
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from twilio.rest import Client as TwilioClient

router = APIRouter(prefix="/comms", tags=["comms"])

_ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam — clear, authoritative
_DEFAULT_MODEL = "eleven_multilingual_v2"

_el_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
_twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
_twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
_twilio_from = os.getenv("TWILIO_FROM_NUMBER", "").strip()
_audio_dir = Path(os.getenv("AUDIO_OUTPUT_DIR", "audio_output"))


class CallRequest(BaseModel):
    vessel_name: str
    mmsi: str
    violations: str
    phone_number: str = Field(..., pattern=r"^\+[1-9]\d{1,14}$")


def _draft_message(vessel_name: str, mmsi: str, violations: str) -> str:
    name = vessel_name if vessel_name and vessel_name.upper() != "UNKNOWN" else f"vessel MMSI {mmsi}"
    return (
        f"Attention {name}. "
        f"This is an automated IUU fishing compliance notice. "
        f"{violations.rstrip('.')}. "
        f"You are required to cease current activity and contact the nearest maritime authority immediately."
    )


def _elevenlabs_tts(text: str) -> bytes:
    resp = http.post(
        _ELEVENLABS_TTS_URL.format(voice_id=_DEFAULT_VOICE_ID),
        json={
            "text": text,
            "model_id": _DEFAULT_MODEL,
            "voice_settings": {"stability": 0.6, "similarity_boost": 0.8},
        },
        headers={"xi-api-key": _el_key, "Content-Type": "application/json"},
        timeout=30,
    )
    if not resp.ok:
        raise HTTPException(502, f"ElevenLabs error {resp.status_code}: {resp.text[:200]}")
    return resp.content


def _upload_audio(filename: str, data: bytes) -> str | None:
    """Upload audio to a public file host and return the URL, trying multiple services."""
    # catbox.moe — reliable, no account needed
    try:
        r = http.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (filename, data, "audio/mpeg")},
            timeout=30,
        )
        if r.ok and r.text.strip().startswith("https://"):
            return r.text.strip()
    except Exception:
        pass

    # 0x0.st — fallback
    try:
        r = http.post(
            "https://0x0.st",
            files={"file": (filename, data, "audio/mpeg")},
            timeout=30,
        )
        if r.ok and r.text.strip().startswith("https://"):
            return r.text.strip()
    except Exception:
        pass

    return None


@router.post("/call")
async def call_vessel(body: CallRequest) -> dict[str, Any]:
    """Generate audio and call a vessel contact's phone number."""
    if not _el_key:
        raise HTTPException(500, "ELEVENLABS_API_KEY not configured on server")
    if not all([_twilio_sid, _twilio_token, _twilio_from]):
        raise HTTPException(500, "Twilio credentials not configured on server")

    message = _draft_message(body.vessel_name, body.mmsi, body.violations)

    # Generate audio — keep bytes in memory, also save locally for reference
    audio_bytes = _elevenlabs_tts(message)
    mmsi_safe = body.mmsi.strip().replace(" ", "_") or "vessel"
    filename = f"warning_{mmsi_safe}.mp3"
    _audio_dir.mkdir(parents=True, exist_ok=True)
    (_audio_dir / filename).write_bytes(audio_bytes)

    audio_url = _upload_audio(filename, audio_bytes)
    if not audio_url:
        raise HTTPException(502, "Could not upload audio to a public host. Twilio requires a public URL.")

    # Escape message for safe XML embedding in TwiML
    safe_url = saxutils.escape(audio_url)
    call = TwilioClient(_twilio_sid, _twilio_token).calls.create(
        to=body.phone_number,
        from_=_twilio_from,
        twiml=f"<Response><Play>{safe_url}</Play></Response>",
        machine_detection="DetectMessageEnd",
    )

    return {"status": "calling", "message": message, "audio_url": audio_url, "call_sid": call.sid}
