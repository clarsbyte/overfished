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

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from documents.render import render_document_family
from fixtures._loader import load_model
from tools import comms, cv_bridge, fines, ports, region, regulations, risk, vessels
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
