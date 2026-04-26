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
       gemma_respond(call_sid, user_text)  -> str
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
from dotenv import load_dotenv

# Load backend/.env regardless of cwd (test_ai_call.py may be run from any dir).
load_dotenv(Path(__file__).parent / ".env")

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam — clear, authoritative
DEFAULT_MODEL = "eleven_multilingual_v2"

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "audio_output"

# ── Claude Haiku conversational layer ──────────────────────────────────────

VOICE_MODEL_DEFAULT = "gemma3:4b"
OLLAMA_HOST_DEFAULT = "http://localhost:11434"
EVIDENCE_OUTPUT_DIR = Path(__file__).parent / "output"
DEFAULT_DEMO_CASE_ID = "SCB-2026-0425-001"
DEFAULT_DEMO_DOC = "cease_and_desist_order.pdf"

WARNING_TEMPLATE = "Warning. Ship {name} is at high risk of illegal fishing."

AI_SYSTEM_PROMPT = """You are an automated maritime compliance and enforcement voice agent.
You are speaking by phone with the captain or crew of a vessel suspected of
Illegal, Unreported, and Unregulated (IUU) fishing. The case file for this
vessel is reproduced below as the EVIDENCE DOCUMENT.

CRITICAL RULES:
1. Answer strictly from facts present in the EVIDENCE DOCUMENT. Do not invent
   regulations, dates, coordinates, fines, or vessel details that are not
   explicitly written there.
2. When the caller asks a general question like "what is the evidence", "what
   does the file say", or "why are you calling", give a brief spoken summary
   of the key findings from the EVIDENCE DOCUMENT — vessel name, MMSI, the
   specific violations or risk indicators documented, and the order issued.
3. Only reply "That information is not in the case file. Please contact the
   issuing authority directly." when the specific detail asked is genuinely
   absent from the document (e.g. fines, prison sentences, specific dates not
   listed).
4. Keep every reply under three short sentences. This is a phone call.
5. Tone: calm, factual, official. Never offer legal advice or negotiate.
6. If the caller disputes the findings, reply: "These findings are documented
   in the case file. You are required to comply with the order."

EVIDENCE DOCUMENT
-----------------
{evidence}
-----------------
"""


PORT_AUTHORITY_SYSTEM_PROMPT = """You are an automated maritime intelligence voice agent.
You are calling the port authority of {port_name}{port_country_suffix} to report
a suspicious vessel detected near their jurisdiction. The case file is reproduced
below as the EVIDENCE DOCUMENT.

REPORTING SUBJECT:
- Vessel: {vessel_name} (MMSI {mmsi})
- Recipient port: {port_name}

You are speaking with port-authority staff who have received the case file and
may have follow-up questions. Help them act on the report — what was detected,
where, why we believe it is suspicious, and what action the case file recommends.

CRITICAL RULES:
1. Answer strictly from facts present in the EVIDENCE DOCUMENT. Do not invent
   regulations, dates, coordinates, fines, or vessel details that are not
   explicitly written there.
2. If the port authority asks anything not covered by the evidence, reply exactly:
   "That information is not in the case file. The full dossier and supporting
   data are available on request from the issuing monitoring authority."
3. Keep every reply under two short sentences. This is a phone call.
4. Tone: calm, factual, professional, like one enforcement agency briefing
   another. You are not accusing the port — you are sharing intelligence
   for their review and action.
5. If the port authority asks what you want them to do, summarise the case
   file's recommended actions (port-state inspection, denial of port entry,
   notification chain) using only language present in the EVIDENCE DOCUMENT.

EVIDENCE DOCUMENT
-----------------
{evidence}
-----------------
"""

# call_sid -> {vessel_name, mmsi, case_id, evidence, history: list[{role, content}]}
_CALL_SESSIONS: dict[str, dict[str, Any]] = {}

# Process-wide "active" knowledge base used when a call has no preregistered
# session (i.e. set via POST /voice/knowledge before the call connects).
_ACTIVE_EVIDENCE: dict[str, Any] | None = None


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


def load_pdf_evidence_from_url(url: str) -> str:
    """Download a PDF over HTTP(S) and extract its text."""
    import io

    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        from PyPDF2 import PdfReader  # type: ignore

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    reader = PdfReader(io.BytesIO(resp.content))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(pages).strip()


def build_warning_text(vessel_name: str | None) -> str:
    name = (vessel_name or "").strip()
    if not name or name.upper() == "UNKNOWN":
        name = "Unknown Vessel"
    return WARNING_TEMPLATE.format(name=name)


def place_ai_call(
    vessel_name: str,
    mmsi: str,
    case_id: str,
    phone_number: str,
    public_base_url: str,
    doc_filename: str = "combined_legal_package.pdf",
) -> str:
    """Place a Twilio AI call grounded in the rendered case PDF.

    Twilio connects the call and fetches /twilio/voice/start on the running
    API server, which registers the session (loads the PDF) and drives a
    Claude-Haiku Q&A loop. Returns the Twilio CallSid.
    """
    from urllib.parse import urlencode
    from call_lookup import call_with_ai_conversation

    params = urlencode({
        "vessel_name": vessel_name or "Unknown Vessel",
        "mmsi": mmsi,
        "case_id": case_id,
        "doc": doc_filename,
    })
    webhook_url = f"{public_base_url.rstrip('/')}/twilio/voice/start?{params}"
    return call_with_ai_conversation(phone_number, webhook_url)


def register_call_session(
    call_sid: str,
    *,
    vessel_name: str,
    mmsi: str,
    case_id: str = DEFAULT_DEMO_CASE_ID,
    doc_filename: str = DEFAULT_DEMO_DOC,
    port_name: str = "",
    port_country: str = "",
) -> dict[str, Any]:
    """Pre-load the evidence PDF text once per call so each turn is cheap.

    When `port_name` is set, the recipient is treated as the port authority and
    the Haiku grounding prompt reframes the conversation as a *report TO the
    port* about a suspicious vessel (rather than a warning TO the vessel).
    """
    evidence = load_pdf_evidence(case_id, doc_filename)
    print(f"[call_session] {call_sid}: loaded {len(evidence)} chars from {case_id}/{doc_filename}")
    session = {
        "vessel_name": vessel_name,
        "mmsi": mmsi,
        "case_id": case_id,
        "evidence": evidence,
        "port_name": port_name or "",
        "port_country": port_country or "",
        "history": [],
    }
    _CALL_SESSIONS[call_sid] = session
    return session


def register_call_session_with_evidence(
    call_sid: str,
    *,
    vessel_name: str,
    mmsi: str,
    evidence_text: str,
    case_id: str = "",
) -> dict[str, Any]:
    """Register a session with already-loaded evidence text (e.g. from a URL)."""
    session = {
        "vessel_name": vessel_name,
        "mmsi": mmsi,
        "case_id": case_id,
        "evidence": evidence_text,
        "history": [],
    }
    _CALL_SESSIONS[call_sid] = session
    return session


def place_ai_call_from_pdf_url(
    *,
    vessel_name: str,
    mmsi: str,
    phone_number: str,
    pdf_url: str,
    public_base_url: str | None = None,
) -> str:
    """Download a PDF from *pdf_url*, place a Twilio AI call, and preregister
    the resulting CallSid so the /twilio/voice/start webhook reuses the
    parsed evidence rather than reading from disk.

    ``public_base_url`` defaults to the ``PUBLIC_API_BASE_URL`` env var; it
    must be a publicly reachable URL where this API is served (e.g. ngrok
    tunnel) since Twilio fetches the webhook over the public internet.
    """
    from urllib.parse import urlencode

    from call_lookup import call_with_ai_conversation

    base = (public_base_url or os.getenv("PUBLIC_API_BASE_URL", "")).strip()
    if not base:
        raise RuntimeError(
            "PUBLIC_API_BASE_URL must be set in .env (e.g. https://abc123.ngrok.io)"
        )

    evidence = load_pdf_evidence_from_url(pdf_url)

    params = urlencode({
        "vessel_name": vessel_name or "Unknown Vessel",
        "mmsi": mmsi,
    })
    webhook_url = f"{base.rstrip('/')}/twilio/voice/start?{params}"
    call_sid = call_with_ai_conversation(phone_number, webhook_url)

    register_call_session_with_evidence(
        call_sid,
        vessel_name=vessel_name or "Unknown Vessel",
        mmsi=mmsi or "000000000",
        evidence_text=evidence,
    )
    return call_sid


def get_call_session(call_sid: str) -> dict[str, Any] | None:
    return _CALL_SESSIONS.get(call_sid)


def end_call_session(call_sid: str) -> None:
    _CALL_SESSIONS.pop(call_sid, None)


def set_active_evidence(pdf_url: str) -> dict[str, Any]:
    """Download the PDF at *pdf_url* and store it as the active knowledge base.

    Subsequent voice calls without a preregistered session will use this
    evidence as their grounding context.
    """
    global _ACTIVE_EVIDENCE
    evidence = load_pdf_evidence_from_url(pdf_url)
    _ACTIVE_EVIDENCE = {"pdf_url": pdf_url, "evidence": evidence}
    return _ACTIVE_EVIDENCE


def get_active_evidence() -> dict[str, Any] | None:
    return _ACTIVE_EVIDENCE


def clear_active_evidence() -> None:
    global _ACTIVE_EVIDENCE
    _ACTIVE_EVIDENCE = None


def _ollama_chat(
    system: str,
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    host: str | None = None,
    max_tokens: int = 300,
) -> str:
    """Call a local Ollama-served chat model and return the assistant text.

    Defaults to ``gemma3:4b`` on ``http://localhost:11434``. Override via the
    ``VOICE_MODEL`` and ``OLLAMA_HOST`` environment variables.
    """
    base = (host or os.getenv("OLLAMA_HOST", OLLAMA_HOST_DEFAULT)).rstrip("/")
    model_name = model or os.getenv("VOICE_MODEL", VOICE_MODEL_DEFAULT)
    # Ollama defaults num_ctx to 2048 tokens — far too small to fit a
    # multi-page legal PDF in the system prompt. Bump it so Gemma actually
    # sees the evidence. Gemma 3 supports up to 128K; 16K is plenty here.
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
    payload = {
        "model": model_name,
        "messages": [{"role": "system", "content": system}, *messages],
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.2,
            "num_ctx": num_ctx,
        },
    }
    resp = requests.post(f"{base}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return ((data.get("message") or {}).get("content") or "").strip()


def gemma_respond(call_sid: str, user_text: str) -> str:
    """Generate a voice-agent response grounded in the session's evidence PDF.

    Now backed by a local Ollama model (``gemma3:4b`` by default) instead of
    Claude Haiku — the function name is preserved so existing call sites
    (Twilio webhook, test_ai_call.py) keep working.

    Updates the session's conversation history in place.
    """
    session = _CALL_SESSIONS.get(call_sid)
    if not session:
        raise KeyError(
            f"No registered call session for CallSid={call_sid}. "
            "Call register_call_session(...) before the first turn."
        )

    history: list[dict[str, str]] = session["history"]
    messages = list(history) + [{"role": "user", "content": user_text}]

    if session.get("port_name"):
        country = (session.get("port_country") or "").strip()
        suffix = f" ({country})" if country else ""
        system = PORT_AUTHORITY_SYSTEM_PROMPT.format(
            port_name=session["port_name"],
            port_country_suffix=suffix,
            vessel_name=session["vessel_name"],
            mmsi=session["mmsi"],
            evidence=session["evidence"],
        )
    else:
        system = AI_SYSTEM_PROMPT.format(evidence=session["evidence"])

    reply = _ollama_chat(system, messages) or "I am unable to respond at this time."

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply})
    return reply
