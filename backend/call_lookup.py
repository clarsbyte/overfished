"""Twilio REST client for vessel warning phone calls.

Two flows:

1. ``call_with_audio(to, mp3_url)`` — legacy single-shot: Twilio plays a
   pre-rendered MP3 and hangs up.

2. ``call_with_ai_conversation(to, webhook_url, ...)`` — Claude-Haiku-powered
   dialog. Twilio fetches TwiML from ``webhook_url`` when the call connects;
   the webhook (in ``api/main.py``) speaks the warning, gathers the caller's
   speech, and round-trips each turn through Claude Haiku grounded in the
   case's evidence PDF.

Usage:
    from call_lookup import call_with_audio, call_with_ai_conversation

    # Legacy
    sid = call_with_audio("+15551234567", "https://yourserver.com/audio/warning_123.mp3")

    # AI conversation
    sid = call_with_ai_conversation(
        "+15551234567",
        webhook_url=(
            "https://yourserver.com/twilio/voice/start"
            "?vessel_name=LU%20RONG%20YUAN%20YU%20666"
            "&mmsi=412345678"
            "&case_id=IUU-PIPELINE-TEST-001"
        ),
    )
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


def _resolve_from_number(from_number: str | None) -> str:
    from_num = from_number or os.getenv("TWILIO_FROM_NUMBER", "").strip()
    if not from_num:
        raise RuntimeError("TWILIO_FROM_NUMBER must be set in .env")
    return from_num


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
    call = _client().calls.create(
        to=to_number,
        from_=_resolve_from_number(from_number),
        twiml=f"<Response><Play>{audio_url}</Play></Response>",
        machine_detection="DetectMessageEnd",  # waits for the beep before playing
    )
    return call.sid


def call_with_ai_conversation(
    to_number: str,
    webhook_url: str,
    from_number: str | None = None,
) -> str:
    """Initiate a Twilio outbound call driven by a TwiML webhook.

    Twilio POSTs to ``webhook_url`` when the call is answered. That endpoint
    (``/twilio/voice/start`` in ``api/main.py``) returns TwiML that:
      1. Speaks the fixed warning ("Warning. Ship NAME is at high risk of
         illegal fishing.").
      2. Hands the caller to Claude Haiku, which answers questions strictly
         from the case evidence PDF.

    Args:
        to_number: E.164 destination number.
        webhook_url: Absolute URL Twilio will fetch on connect. Should encode
            ``vessel_name``, ``mmsi``, and (optionally) ``case_id`` as query
            params so the webhook knows which case to load.
        from_number: Twilio caller ID. Falls back to TWILIO_FROM_NUMBER.

    Returns:
        Twilio call SID.
    """
    call = _client().calls.create(
        to=to_number,
        from_=_resolve_from_number(from_number),
        url=webhook_url,
        method="POST",
        machine_detection="DetectMessageEnd",
    )
    return call.sid
