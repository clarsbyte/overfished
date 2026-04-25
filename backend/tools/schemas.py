"""Pydantic schemas — the contract between tool layer, frontend, and agents.

These models are the single source of truth. The frontend's TypeScript types are
auto-generated from them via ``scripts/generate_ts_types.py``. The fixtures in
``backend/fixtures/`` validate against them on load.

Datetimes serialize as ISO strings with explicit ``+00:00`` offset (Pydantic v2
default). Frontends should parse with ``new Date(s)``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

__all__ = [
    "LatLon",
    "RegionContext",
    "Vessel",
    "VesselEvent",
    "IUURule",
    "RiskAssessment",
    "LegalCitation",
    "PenaltyLineItem",
    "FineCalculation",
    "DocumentArtifact",
    "VesselDetection",
    "CaseFile",
]


class _Strict(BaseModel):
    """Base for every model — forbids extras so fixture drift surfaces in tests."""

    model_config = ConfigDict(extra="forbid")


class LatLon(_Strict):
    """A single geographic coordinate."""

    lat: float
    lon: float


class RegionContext(_Strict):
    """Resolved metadata for a user-drawn region (or pre-baked demo region)."""

    region_id: str
    name: str
    polygon_geojson: dict
    eez_country: Optional[str] = None
    mpa_wdpa_ids: list[int] = []
    rfmo_ids: list[str] = []
    centroid: LatLon
    area_km2: float


class Vessel(_Strict):
    """Vessel identity, ownership, and last-known position."""

    mmsi: str
    imo: Optional[str] = None
    name: Optional[str] = None
    flag: Optional[str] = None
    gear_type: Optional[str] = None
    length_m: Optional[float] = None
    owner: Optional[str] = None
    authorizations: list[str] = []
    last_position: Optional[LatLon] = None
    last_seen: Optional[datetime] = None


class VesselEvent(_Strict):
    """A single behavioural event from GFW Events API or equivalent."""

    event_id: str
    mmsi: str
    type: Literal["FISHING", "GAP", "ENCOUNTER", "LOITERING", "PORT_VISIT"]
    start: datetime
    end: Optional[datetime] = None
    position: LatLon
    duration_hours: Optional[float] = None
    metadata: dict = {}


class IUURule(_Strict):
    """A structured IUU rule extracted from a legal instrument."""

    rule_id: str
    source_doc: str
    jurisdiction: str
    category: Literal[
        "no_take_zone",
        "seasonal_closure",
        "gear_restriction",
        "license_required",
        "ais_required",
        "catch_limit",
        "size_limit",
        "species_protected",
    ]
    description: str
    machine_check: dict
    penalty_text: Optional[str] = None


class RiskAssessment(_Strict):
    """Output of the risk engine — feeds the document generator."""

    vessel: Vessel
    region_id: str
    risk_score: float
    classification: Literal["safe", "suspect", "high_risk", "confirmed_iuu"]
    triggered_rules: list[str]
    evidence: list[VesselEvent]
    reasoning: str


class LegalCitation(_Strict):
    """A single legal citation, layered across instruments."""

    instrument: str
    layer: Literal["international", "national", "rfmo", "voluntary"]
    full_title: str
    role: str
    excerpt: Optional[str] = None
    source_url: Optional[str] = None


class PenaltyLineItem(_Strict):
    """One row in the Schedule A penalty table."""

    description: str
    legal_basis: list[LegalCitation]
    amount_usd: float
    is_multiplier: bool = False
    multiplier_value: Optional[float] = None


class FineCalculation(_Strict):
    """Itemised civil-penalty calculation for a vessel."""

    vessel_mmsi: str
    region_id: str
    estimated_catch_kg: float
    primary_species: Optional[str] = None
    line_items: list[PenaltyLineItem]
    subtotal_usd: float
    multipliers: dict[str, float]
    total_fine_usd: float
    citations: list[LegalCitation]
    breakdown_text: str


class DocumentArtifact(_Strict):
    """A rendered legal document, ready for download."""

    artifact_id: str
    case_id: str
    doc_type: Literal[
        "notice_of_violation",
        "cease_and_desist_order",
        "port_inspection_order",
        "evidence_package",
        "combined_legal_package",
    ]
    html_url: str
    pdf_url: str
    sha256: str
    rendered_at: datetime
    page_count: int


class VesselDetection(_Strict):
    """A CV detection from David's pipeline (SAR or optical)."""

    detection_id: str
    timestamp: datetime
    position: LatLon
    confidence: float
    estimated_length_m: Optional[float] = None
    matched_mmsi: Optional[str] = None
    source: Literal["sar", "optical"]
    image_url: str


class CaseFile(_Strict):
    """Shared state object — flows through Clarissa's LangGraph and the renderer."""

    case_id: str
    region: RegionContext
    vessel: Vessel
    events: list[VesselEvent]
    detections: list[VesselDetection] = []
    rules: list[IUURule]
    citations: list[LegalCitation]
    risk: Optional[RiskAssessment] = None
    fine: Optional[FineCalculation] = None
    documents: list[DocumentArtifact] = []
    cease_desist_audio_url: Optional[str] = None
    notified_port: Optional[str] = None
    call_recording_url: Optional[str] = None
    timeline: list[dict] = []
