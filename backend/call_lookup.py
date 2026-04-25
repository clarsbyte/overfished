"""Twilio REST client for vessel warning phone calls.

Usage:
    from call_lookup import call_with_audio
    sid = call_with_audio("+15551234567", "https://yourserver.com/audio/warning_123.mp3")
    print(sid)  # Twilio call SID
"""

from __future__ import annotations

import os

from twilio.rest import Client


def _client() -> Client:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not sid or not token:
        raise RuntimeError(
            "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set in .env"
        )
    return Client(sid, token)


def call_with_audio(
    to_number: str,
    audio_url: str,
    from_number: str | None = None,
) -> str:
    """Initiate a Twilio outbound call that plays an MP3 when answered.

    Args:
        to_number: E.164 destination number (e.g. "+15551234567").
        audio_url: Publicly reachable URL to the MP3 file.
        from_number: Twilio caller ID. Falls back to TWILIO_FROM_NUMBER env var.

    Returns:
        Twilio call SID.
    """
    from_num = from_number or os.getenv("TWILIO_FROM_NUMBER", "").strip()
    if not from_num:
        raise RuntimeError("TWILIO_FROM_NUMBER must be set in .env")

    call = _client().calls.create(
        to=to_number,
        from_=from_num,
        twiml=f"<Response><Play>{audio_url}</Play></Response>",
        machine_detection="DetectMessageEnd",  # waits for the beep before playing
    )
    return call.sid
