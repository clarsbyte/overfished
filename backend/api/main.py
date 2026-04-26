"""FastAPI surface for the frontend.

Thin REST wrapper that delegates to the tool layer. CORS is wide-open in dev.
``/static/`` serves rendered PDFs and HTML straight from ``backend/output/``.

Run::

    USE_FIXTURES=1 uvicorn api.main:app --reload --port 8000

OpenAPI docs render at ``http://localhost:8000/docs``.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

import comms_lookup
from documents.render import render_document_family
from fixtures._loader import load_model
from tools import comms, cv_bridge, fines, ports, region, regulations, risk, species_exposure, vessels
from tools.schemas import CaseFile

app = FastAPI(title="Overfish AI Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(OUTPUT_DIR)), name="static")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "use_fixtures": os.getenv("USE_FIXTURES", "1") == "1"}


# ── region ──────────────────────────────────────────────────────────────


@app.post("/region")
def define_region(polygon: dict = Body(...)):
    """Resolve a user-drawn GeoJSON Polygon into a populated RegionContext."""
    return region.define_region(polygon)


# ── vessels ─────────────────────────────────────────────────────────────


@app.get("/vessels")
def list_vessels(region_id: str = "galapagos", days: int = 7):
    return vessels.get_vessels_in_region(region_id)


@app.get("/heatmap")
def heatmap(region_id: str = "galapagos", days: int = 30):
    return vessels.get_fishing_effort_heatmap(region_id)


@app.get("/fishery-regions")
def fishery_regions():
    """Named fishery regions worldwide with risk classification — feeds globe.gl Hexed Polygons."""
    return region.get_fishery_regions()


@app.get("/species-fishing-exposure")
def species_fishing_exposure_route(species: str = "cod"):
    """Curated species → fishery regions ranked by demo IUU-style risk (fixture-only)."""
    try:
        return species_exposure.get_species_fishing_exposure(species)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e


@app.get("/vessel-tracks/global")
def global_vessel_tracks():
    """~25 vessel tracks worldwide — feeds the ambient animated Paths layer."""
    return vessels.get_global_vessel_tracks()


@app.get("/vessel/{mmsi}")
def vessel_info(mmsi: str):
    try:
        return vessels.get_vessel_info(mmsi)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/vessel/{mmsi}/events")
def vessel_events(mmsi: str):
    return vessels.get_vessel_events(mmsi)


@app.get("/vessel/{mmsi}/track")
def vessel_track(mmsi: str, hours: int = 24):
    return vessels.get_vessel_track(mmsi, hours)


@app.get("/vessel/{mmsi}/risk")
def vessel_risk(mmsi: str, region_id: str = "galapagos"):
    region_ctx = region.define_region({})
    rules = regulations.extract_iuu_rules([], region_ctx)
    vessel = vessels.get_vessel_info(mmsi)
    events = vessels.get_vessel_events(mmsi)
    detections = cv_bridge.get_cv_detections(region_id)
    return risk.calculate_risk(vessel, events, rules, region_ctx, detections)


# ── citations / regulations ─────────────────────────────────────────────


@app.get("/citations")
def citations(region_id: str = "galapagos"):
    region_ctx = region.define_region({})
    rules = regulations.extract_iuu_rules([], region_ctx)
    return regulations.build_citation_roster(rules, region_ctx)


@app.get("/regulations")
def list_regulations(region_id: str = "galapagos"):
    region_ctx = region.define_region({})
    return regulations.extract_iuu_rules([], region_ctx)


# ── case actions ────────────────────────────────────────────────────────


def _load_demo_case() -> CaseFile:
    return load_model("case_galapagos_demo", CaseFile)


@app.post("/case/{case_id}/documents")
async def render_documents(case_id: str):
    """Render the full four-document family for a case.

    For the demo, ``case_id`` is ignored — we always render the canonical
    ``case_galapagos_demo`` dossier. Real mode would look up the CaseFile
    by ID from agent state.
    """
    case = _load_demo_case()
    artifacts = await render_document_family(case)
    return artifacts


@app.post("/case/{case_id}/hail")
def hail_vessel(case_id: str):
    case = _load_demo_case()
    region_ctx = case.region
    rules = regulations.extract_iuu_rules([], region_ctx)
    assessment = risk.calculate_risk(case.vessel, case.events, rules, region_ctx)
    audio_url = comms.generate_cease_and_desist_audio(case.vessel, assessment, region_ctx)
    script = comms.build_cease_and_desist_script(case.vessel, region_ctx)
    return {"audio_url": audio_url, "script": script}


@app.post("/case/{case_id}/notify-port")
def notify_port(case_id: str):
    case = _load_demo_case()
    predictions = ports.predict_next_port(case.vessel.mmsi)
    if not predictions:
        raise HTTPException(status_code=404, detail="No port prediction available")
    primary = predictions[0]
    test_phone = os.getenv("DEMO_PHONE_NUMBER", "+1-555-0100")
    call = ports.notify_port_authority(primary, case, test_phone)
    return {"port": primary, "call": call, "predictions": predictions}


# ── case fine (used by frontend for the count-up) ───────────────────────


@app.get("/case/{case_id}/fine")
def case_fine(case_id: str):
    case = _load_demo_case()
    region_ctx = case.region
    rules = regulations.extract_iuu_rules([], region_ctx)
    citations_list = regulations.build_citation_roster(rules, region_ctx)
    assessment = risk.calculate_risk(case.vessel, case.events, rules, region_ctx)
    return fines.calculate_fine(case.vessel, assessment, region_ctx, rules, citations_list)


# ── Twilio AI conversation webhooks ─────────────────────────────────────
#
# Flow:
#   1. POST /case/{case_id}/ai-call kicks off an outbound Twilio call.
#   2. Twilio answers and POSTs to /twilio/voice/start, which returns TwiML
#      that says the warning, then <Gather>s the caller's speech.
#   3. Each user turn POSTs to /twilio/voice/respond. We ask Claude Haiku to
#      reply using only the case PDF as evidence, speak the reply, and
#      <Gather> again until the caller hangs up.

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
        f'</Gather>'
    )


def _respond_action_url(request: Request, vessel_name: str, mmsi: str, case_id: str, doc: str) -> str:
    base = str(request.base_url).rstrip("/")
    from urllib.parse import urlencode

    qs = urlencode(
        {"vessel_name": vessel_name, "mmsi": mmsi, "case_id": case_id, "doc": doc}
    )
    return f"{base}/twilio/voice/respond?{qs}"


@app.post("/twilio/voice/start")
async def twilio_voice_start(request: Request):
    """Initial TwiML when Twilio connects the call.

    Reads ``vessel_name``, ``mmsi``, ``case_id``, ``doc`` from the query string,
    registers a per-CallSid session pre-loaded with the evidence PDF, says the
    fixed warning, then gathers the caller's first question.
    """
    qp = request.query_params
    vessel_name = qp.get("vessel_name", "Unknown Vessel")
    mmsi = qp.get("mmsi", "000000000")
    case_id = qp.get("case_id", DEFAULT_AI_CASE_ID)
    doc = qp.get("doc", DEFAULT_AI_DOC)

    form = await request.form()
    call_sid = form.get("CallSid", "")

    try:
        comms_lookup.register_call_session(
            call_sid, vessel_name=vessel_name, mmsi=mmsi, case_id=case_id, doc_filename=doc
        )
    except FileNotFoundError as exc:
        # No evidence PDF — speak the warning then end the call.
        warning = comms_lookup.build_warning_text(vessel_name)
        body = (
            f'<Say voice="{TWIML_VOICE}">{_xml_escape(warning)}</Say>'
            f'<Say voice="{TWIML_VOICE}">'
            f'Case file unavailable: {_xml_escape(str(exc))}.'
            f'</Say><Hangup/>'
        )
        return _twiml(body)

    warning = comms_lookup.build_warning_text(vessel_name)
    action_url = _respond_action_url(request, vessel_name, mmsi, case_id, doc)
    body = (
        f'<Say voice="{TWIML_VOICE}">{_xml_escape(warning)}</Say>'
        f'<Pause length="1"/>'
        + _gather(action_url, "Do you have any questions about this notice?")
        + f'<Say voice="{TWIML_VOICE}">No response received. Goodbye.</Say><Hangup/>'
    )
    return _twiml(body)


@app.post("/twilio/voice/respond")
async def twilio_voice_respond(request: Request):
    """Per-turn TwiML: pass the caller's speech to Claude Haiku, speak the reply, gather again."""
    qp = request.query_params
    vessel_name = qp.get("vessel_name", "Unknown Vessel")
    mmsi = qp.get("mmsi", "000000000")
    case_id = qp.get("case_id", DEFAULT_AI_CASE_ID)
    doc = qp.get("doc", DEFAULT_AI_DOC)

    form = await request.form()
    call_sid = form.get("CallSid", "")
    user_text = (form.get("SpeechResult") or "").strip()

    # Re-register if a fresh process picked up this call (in-memory state lost).
    if call_sid and not comms_lookup.get_call_session(call_sid):
        try:
            comms_lookup.register_call_session(
                call_sid, vessel_name=vessel_name, mmsi=mmsi, case_id=case_id, doc_filename=doc
            )
        except FileNotFoundError:
            return _twiml(
                f'<Say voice="{TWIML_VOICE}">Case file unavailable. Goodbye.</Say><Hangup/>'
            )

    action_url = _respond_action_url(request, vessel_name, mmsi, case_id, doc)

    if not user_text:
        body = (
            _gather(action_url, "I did not catch that. Could you repeat your question?")
            + f'<Say voice="{TWIML_VOICE}">Goodbye.</Say><Hangup/>'
        )
        return _twiml(body)

    if any(kw in user_text.lower() for kw in ("goodbye", "good bye", "hang up", "end call", "thank you that is all")):
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


@app.post("/case/{case_id}/ai-call")
def place_ai_call(case_id: str, body: dict = Body(...)):
    """Place an outbound Twilio call powered by Claude Haiku.

    Request body::

        {
          "to_number": "+15551234567",
          "vessel_name": "LU RONG YUAN YU 666",
          "mmsi": "412345678",
          "doc": "combined_legal_package.pdf",  # optional
          "public_base_url": "https://abc123.ngrok.io"  # optional; required when Twilio cannot reach localhost
        }
    """
    to_number = (body.get("to_number") or "").strip()
    if not to_number:
        raise HTTPException(status_code=400, detail="to_number is required")

    vessel_name = body.get("vessel_name") or "Unknown Vessel"
    mmsi = body.get("mmsi") or "000000000"
    doc = body.get("doc") or DEFAULT_AI_DOC
    public_base_url = (body.get("public_base_url") or os.getenv("PUBLIC_BASE_URL", "")).strip()
    if not public_base_url:
        raise HTTPException(
            status_code=400,
            detail=(
                "public_base_url is required (Twilio cannot reach localhost). "
                "Provide an ngrok URL, or set PUBLIC_BASE_URL in .env."
            ),
        )

    from urllib.parse import urlencode

    qs = urlencode(
        {"vessel_name": vessel_name, "mmsi": mmsi, "case_id": case_id, "doc": doc}
    )
    webhook_url = f"{public_base_url.rstrip('/')}/twilio/voice/start?{qs}"
    from call_lookup import call_with_ai_conversation

    sid = call_with_ai_conversation(to_number, webhook_url)
    return {
        "call_sid": sid,
        "webhook_url": webhook_url,
        "vessel_name": vessel_name,
        "mmsi": mmsi,
        "case_id": case_id,
    }
