"""ElevenLabs TTS client for vessel warning audio generation.

Generates a spoken maritime warning message for a vessel and saves it as an MP3.

Usage:
    from comms_lookup import generate_vessel_warning
    result = generate_vessel_warning("EVER GIVEN", "123456789", "AIS gap detected inside no-take MPA.")
    print(result["audio_path"])  # path to saved MP3
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam — clear, authoritative
DEFAULT_MODEL = "eleven_multilingual_v2"

# Saved relative to this file so the web app can serve from a known path.
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "audio_output"


def _headers() -> dict[str, str]:
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. Get a free key at https://elevenlabs.io "
            "and add it to your .env file."
        )
    return {"xi-api-key": key, "Content-Type": "application/json"}


def _draft_message(vessel_name: str, mmsi: str, violations: str) -> str:
    name = vessel_name if vessel_name and vessel_name.upper() != "UNKNOWN" else f"vessel MMSI {mmsi}"
    return (
        f"Attention {name}. "
        f"This is an automated IUU fishing compliance notice. "
        f"{violations.rstrip('.')}. "
        f"You are required to cease current activity and contact the nearest maritime authority immediately."
    )


def _generate_audio(
    text: str,
    filename: str,
    output_dir: Path,
    voice_id: str,
) -> Path:
    url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)
    body: dict[str, Any] = {
        "text": text,
        "model_id": DEFAULT_MODEL,
        "voice_settings": {"stability": 0.6, "similarity_boost": 0.8},
    }
    resp = requests.post(url, json=body, headers=_headers(), timeout=30)
    resp.raise_for_status()

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename
    out_path.write_bytes(resp.content)
    return out_path


def generate_vessel_warning(
    vessel_name: str,
    mmsi: str,
    violations: str,
    voice_id: str = DEFAULT_VOICE_ID,
    output_dir: Path | str | None = None,
) -> dict[str, str]:
    """Draft and generate an audio warning for a vessel.

    Args:
        vessel_name: display name of the vessel.
        mmsi: MMSI number, used to name the output file.
        violations: short description of the concerning behaviour (1–2 sentences).
        voice_id: ElevenLabs voice ID. Defaults to Adam.
        output_dir: directory to save the MP3. Defaults to backend/audio_output/.

    Returns:
        {"message": <spoken text>, "audio_path": <absolute path to MP3>}
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    mmsi_safe = mmsi.strip().replace(" ", "_") or "vessel"
    filename = f"warning_{mmsi_safe}.mp3"

    message = _draft_message(vessel_name, mmsi, violations)
    audio_path = _generate_audio(message, filename, out_dir, voice_id)

    return {"message": message, "audio_path": str(audio_path.resolve())}


def generate_and_call(
    vessel_name: str,
    mmsi: str,
    violations: str,
    phone_number: str,
    audio_base_url: str,
    voice_id: str = DEFAULT_VOICE_ID,
    output_dir: Path | str | None = None,
) -> dict[str, str]:
    """Generate a warning audio file and place a phone call to play it.

    Args:
        vessel_name: display name of the vessel.
        mmsi: MMSI number.
        violations: short description of the concerning behaviour (1–2 sentences).
        phone_number: E.164 destination number (e.g. "+15551234567").
        audio_base_url: base URL where audio_output/ is served (e.g. "http://localhost:8000/audio").
        voice_id: ElevenLabs voice ID. Defaults to Adam.
        output_dir: directory to save the MP3. Defaults to backend/audio_output/.

    Returns:
        {"message", "audio_path", "audio_url", "call_sid"}
    """
    from call_lookup import call_with_audio

    warning = generate_vessel_warning(vessel_name, mmsi, violations, voice_id, output_dir)
    mmsi_safe = mmsi.strip().replace(" ", "_") or "vessel"
    audio_url = f"{audio_base_url.rstrip('/')}/warning_{mmsi_safe}.mp3"
    call_sid = call_with_audio(phone_number, audio_url)

    return {**warning, "audio_url": audio_url, "call_sid": call_sid}
