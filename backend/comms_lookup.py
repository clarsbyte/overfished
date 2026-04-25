"""ElevenLabs TTS + Claude Haiku conversational client for vessel warnings.

Two surfaces:

1. The original ElevenLabs flow (kept for backward compat with gfw_agent.py):
       generate_vessel_warning(...)  -> writes an MP3
       generate_and_call(...)        -> writes the MP3 and dials Twilio with <Play>

2. A new Claude-Haiku-powered conversational flow used by the FastAPI Twilio
   webhooks. The vessel hears a fixed warning ("Warning. Ship NAME is at high
   risk of illegal fishing.") and is then handed to Claude Haiku, which answers
   follow-up questions strictly from the evidence PDF for the case.

       register_call_session(call_sid, vessel_name=..., mmsi=..., case_id=...)
       haiku_respond(call_sid, user_text)  -> str
       build_warning_text(vessel_name)     -> str
       load_pdf_evidence(case_id)          -> str

Conversation state is held in process memory (``_CALL_SESSIONS``) keyed by the
Twilio CallSid. This is fine for the demo — restart the server and sessions
clear.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam — clear, authoritative
DEFAULT_MODEL = "eleven_multilingual_v2"

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "audio_output"

# ── Claude Haiku conversational layer ──────────────────────────────────────

HAIKU_MODEL = "claude-haiku-4-5-20251001"
EVIDENCE_OUTPUT_DIR = Path(__file__).parent / "output"
DEFAULT_DEMO_CASE_ID = "IUU-PIPELINE-TEST-001"
DEFAULT_DEMO_DOC = "combined_legal_package.pdf"

WARNING_TEMPLATE = "Warning. Ship {name} is at high risk of illegal fishing."

AI_SYSTEM_PROMPT = """You are an automated maritime compliance and enforcement voice agent.
You are speaking by phone with the captain or crew of a vessel suspected of
Illegal, Unreported, and Unregulated (IUU) fishing. The case file for this
vessel is reproduced below as the EVIDENCE DOCUMENT.

CRITICAL RULES:
1. Answer strictly from facts present in the EVIDENCE DOCUMENT. Do not invent
   regulations, dates, coordinates, fines, or vessel details that are not
   explicitly written there.
2. If the caller asks anything not covered by the evidence, reply exactly:
   "That information is not in the case file. Please contact the issuing
   authority directly."
3. Keep every reply under two short sentences. This is a phone call.
4. Tone: calm, factual, official. Never offer legal advice or negotiate.
5. If the caller disputes the findings, reply: "These findings are documented
   in the case file. You are required to comply with the order."

EVIDENCE DOCUMENT
-----------------
{evidence}
-----------------
"""

# call_sid -> {vessel_name, mmsi, case_id, evidence, history: list[{role, content}]}
_CALL_SESSIONS: dict[str, dict[str, Any]] = {}


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


# ── Claude Haiku conversational helpers ────────────────────────────────────


def _read_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF. Prefers ``pypdf``, falls back to ``PyPDF2``."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        from PyPDF2 import PdfReader  # type: ignore
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(pages).strip()


def load_pdf_evidence(
    case_id: str = DEFAULT_DEMO_CASE_ID,
    doc_filename: str = DEFAULT_DEMO_DOC,
    output_dir: Path | str | None = None,
) -> str:
    """Read the case PDF for use as Claude context.

    Falls back to ``evidence_package.pdf`` if the requested file is missing.
    Raises ``FileNotFoundError`` if neither exists.
    """
    base = Path(output_dir) if output_dir else EVIDENCE_OUTPUT_DIR
    case_dir = base / case_id
    pdf_path = case_dir / doc_filename
    if not pdf_path.exists():
        pdf_path = case_dir / "evidence_package.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"No evidence PDF found for case {case_id!r} in {case_dir}"
        )
    return _read_pdf_text(pdf_path)


def build_warning_text(vessel_name: str | None) -> str:
    name = (vessel_name or "").strip()
    if not name or name.upper() == "UNKNOWN":
        name = "Unknown Vessel"
    return WARNING_TEMPLATE.format(name=name)


def register_call_session(
    call_sid: str,
    *,
    vessel_name: str,
    mmsi: str,
    case_id: str = DEFAULT_DEMO_CASE_ID,
    doc_filename: str = DEFAULT_DEMO_DOC,
) -> dict[str, Any]:
    """Pre-load the evidence PDF text once per call so each turn is cheap."""
    evidence = load_pdf_evidence(case_id, doc_filename)
    session = {
        "vessel_name": vessel_name,
        "mmsi": mmsi,
        "case_id": case_id,
        "evidence": evidence,
        "history": [],
    }
    _CALL_SESSIONS[call_sid] = session
    return session


def get_call_session(call_sid: str) -> dict[str, Any] | None:
    return _CALL_SESSIONS.get(call_sid)


def end_call_session(call_sid: str) -> None:
    _CALL_SESSIONS.pop(call_sid, None)


def _anthropic_client():
    import anthropic

    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")
    return anthropic.Anthropic(api_key=key)


def haiku_respond(call_sid: str, user_text: str) -> str:
    """Generate a Claude Haiku response grounded in the session's evidence PDF.

    Updates the session's conversation history in place.
    """
    session = _CALL_SESSIONS.get(call_sid)
    if not session:
        raise KeyError(
            f"No registered call session for CallSid={call_sid}. "
            "Call register_call_session(...) before the first turn."
        )

    client = _anthropic_client()
    history: list[dict[str, str]] = session["history"]
    messages = list(history) + [{"role": "user", "content": user_text}]
    resp = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=300,
        system=AI_SYSTEM_PROMPT.format(evidence=session["evidence"]),
        messages=messages,
    )
    parts: list[str] = []
    for block in resp.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    reply = "".join(parts).strip() or "I am unable to respond at this time."

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply})
    return reply
