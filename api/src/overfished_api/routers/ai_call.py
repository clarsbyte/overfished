"""AI conversational vessel-call router.

Three endpoints:
    POST /comms/ai-call          → place an outbound Twilio call powered by Claude Haiku.
    POST /twilio/voice/start     → TwiML webhook hit by Twilio when the call connects.
    POST /twilio/voice/respond   → TwiML webhook for each user speech turn.

Backend logic lives in ``backend/comms_lookup.py`` (PDF text extraction, session
state, Claude Haiku call). This router is the FastAPI surface only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from dotenv import load_dotenv
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import Response

_BACKEND_DIR = Path(__file__).resolve().parents[4] / "backend"
if _BACKEND_DIR.is_dir() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
load_dotenv(_BACKEND_DIR / ".env", override=False)

import comms_lookup  # noqa: E402  — backend module, requires sys.path patch above

router = APIRouter(tags=["ai-call"])

TWIML_VOICE = "Polly.Joanna-Neural"
DEFAULT_AI_CASE_ID = comms_lookup.DEFAULT_DEMO_CASE_ID
DEFAULT_AI_DOC = comms_lookup.DEFAULT_DEMO_DOC


def _twiml(body: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>{body}</Response>'
    return Response(content=xml, media_type="application/xml")


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _gather(action_url: str, prompt: str) -> str:
    return (
        f'<Gather input="speech" action="{_xml_escape(action_url)}" method="POST" '
        f'speechTimeout="auto" timeout="6" language="en-US">'
        f'<Say voice="{TWIML_VOICE}">{_xml_escape(prompt)}</Say>'
        f"</Gather>"
    )


async def _twilio_form(request: Request) -> dict[str, str]:
    """Parse Twilio's url-encoded webhook body without requiring python-multipart."""
    raw = await request.body()
    if not raw:
        return {}
    parsed = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items() if v}


def _respond_action_url(
    request: Request,
    vessel_name: str,
    mmsi: str,
    case_id: str,
    doc: str,
    port_name: str = "",
    port_country: str = "",
) -> str:
    base = str(request.base_url).rstrip("/")
    qs = urlencode(
        {
            "vessel_name": vessel_name,
            "mmsi": mmsi,
            "case_id": case_id,
            "doc": doc,
            "port_name": port_name,
            "port_country": port_country,
        }
    )
    return f"{base}/twilio/voice/respond?{qs}"


def _build_greeting(vessel_name: str, mmsi: str, port_name: str) -> str:
    """Compose the opening line. When port_name is set we are reporting TO the
    port authority about the vessel; otherwise we fall back to the legacy flow
    that warns the vessel directly."""
    if port_name:
        return (
            f"Hello, Port of {port_name}. This is an automated alert from the "
            f"IUU fishing monitoring system. We are reporting suspicious "
            f"vessel {vessel_name}, MMSI {mmsi}, detected near your jurisdiction. "
            f"A full case file has been transmitted to your authority for review."
        )
    return comms_lookup.build_warning_text(vessel_name)


@router.post("/twilio/voice/start")
async def twilio_voice_start(request: Request) -> Response:
    """Initial TwiML — speak the warning, gather first question."""
    qp = request.query_params
    vessel_name = qp.get("vessel_name", "Unknown Vessel")
    mmsi = qp.get("mmsi", "000000000")
    case_id = qp.get("case_id", DEFAULT_AI_CASE_ID)
    doc = qp.get("doc", DEFAULT_AI_DOC)
    port_name = qp.get("port_name", "")
    port_country = qp.get("port_country", "")

    form = await _twilio_form(request)
    call_sid = form.get("CallSid", "")

    try:
        comms_lookup.register_call_session(
            call_sid,
            vessel_name=vessel_name,
            mmsi=mmsi,
            case_id=case_id,
            doc_filename=doc,
            port_name=port_name,
            port_country=port_country,
        )
    except FileNotFoundError as exc:
        greeting = _build_greeting(vessel_name, mmsi, port_name)
        body = (
            f'<Say voice="{TWIML_VOICE}">{_xml_escape(greeting)}</Say>'
            f'<Say voice="{TWIML_VOICE}">Case file unavailable: '
            f"{_xml_escape(str(exc))}.</Say><Hangup/>"
        )
        return _twiml(body)

    greeting = _build_greeting(vessel_name, mmsi, port_name)
    action_url = _respond_action_url(
        request, vessel_name, mmsi, case_id, doc, port_name, port_country
    )
    follow_up = (
        "Do you have any questions about the case file?"
        if port_name
        else "Do you have any questions about this notice?"
    )
    body = (
        f'<Say voice="{TWIML_VOICE}">{_xml_escape(greeting)}</Say>'
        f'<Pause length="1"/>'
        + _gather(action_url, follow_up)
        + f'<Say voice="{TWIML_VOICE}">No response received. Goodbye.</Say><Hangup/>'
    )
    return _twiml(body)


@router.post("/twilio/voice/respond")
async def twilio_voice_respond(request: Request) -> Response:
    """Per-turn TwiML — pass speech to Claude Haiku, speak the reply, gather again."""
    qp = request.query_params
    vessel_name = qp.get("vessel_name", "Unknown Vessel")
    mmsi = qp.get("mmsi", "000000000")
    case_id = qp.get("case_id", DEFAULT_AI_CASE_ID)
    doc = qp.get("doc", DEFAULT_AI_DOC)
    port_name = qp.get("port_name", "")
    port_country = qp.get("port_country", "")

    form = await _twilio_form(request)
    call_sid = form.get("CallSid", "")
    user_text = (form.get("SpeechResult") or "").strip()

    if call_sid and not comms_lookup.get_call_session(call_sid):
        try:
            comms_lookup.register_call_session(
                call_sid,
                vessel_name=vessel_name,
                mmsi=mmsi,
                case_id=case_id,
                doc_filename=doc,
                port_name=port_name,
                port_country=port_country,
            )
        except FileNotFoundError:
            return _twiml(
                f'<Say voice="{TWIML_VOICE}">Case file unavailable. Goodbye.</Say><Hangup/>'
            )

    action_url = _respond_action_url(
        request, vessel_name, mmsi, case_id, doc, port_name, port_country
    )

    if not user_text:
        body = (
            _gather(action_url, "I did not catch that. Could you repeat your question?")
            + f'<Say voice="{TWIML_VOICE}">Goodbye.</Say><Hangup/>'
        )
        return _twiml(body)

    if any(
        kw in user_text.lower()
        for kw in ("goodbye", "good bye", "hang up", "end call", "thank you that is all")
    ):
        comms_lookup.end_call_session(call_sid)
        return _twiml(
            f'<Say voice="{TWIML_VOICE}">Acknowledged. Comply with the order. Goodbye.</Say><Hangup/>'
        )

    try:
        reply = comms_lookup.haiku_respond(call_sid, user_text)
    except Exception as exc:
        reply = f"System error generating response: {exc}. Please contact the issuing authority directly."

    body = (
        f'<Say voice="{TWIML_VOICE}">{_xml_escape(reply)}</Say>'
        + _gather(action_url, "Do you have any other questions?")
        + f'<Say voice="{TWIML_VOICE}">Goodbye.</Say><Hangup/>'
    )
    return _twiml(body)


@router.post("/comms/ai-call")
def place_ai_call(body: dict = Body(...)) -> dict:
    """Place an outbound Twilio call driven by Claude Haiku grounded in the case PDF."""
    to_number = (body.get("to_number") or "").strip()
    if not to_number:
        raise HTTPException(status_code=400, detail="to_number is required")

    vessel_name = body.get("vessel_name") or "Unknown Vessel"
    mmsi = body.get("mmsi") or "000000000"
    case_id = body.get("case_id") or DEFAULT_AI_CASE_ID
    doc = body.get("doc") or DEFAULT_AI_DOC
    port_name = (body.get("port_name") or "").strip()
    port_country = (body.get("port_country") or "").strip()
    public_base_url = (
        body.get("public_base_url") or os.getenv("PUBLIC_BASE_URL", "")
    ).strip()
    if not public_base_url:
        raise HTTPException(
            status_code=400,
            detail=(
                "public_base_url is required (Twilio cannot reach localhost). "
                "Provide an ngrok URL, or set PUBLIC_BASE_URL in .env."
            ),
        )

    qs = urlencode(
        {
            "vessel_name": vessel_name,
            "mmsi": mmsi,
            "case_id": case_id,
            "doc": doc,
            "port_name": port_name,
            "port_country": port_country,
        }
    )
    webhook_url = f"{public_base_url.rstrip('/')}/twilio/voice/start?{qs}"

    from call_lookup import call_with_ai_conversation

    try:
        sid = call_with_ai_conversation(to_number, webhook_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Twilio call failed: {exc!s}") from exc

    return {
        "call_sid": sid,
        "webhook_url": webhook_url,
        "vessel_name": vessel_name,
        "mmsi": mmsi,
        "case_id": case_id,
        "doc": doc,
    }
