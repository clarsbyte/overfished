"""Risk engine — combines rule evaluations into a RiskAssessment.

Fixture mode returns a deterministic high-confidence outcome for the demo
vessel so the document family lands consistently. Real mode would run rule
evaluations + GFW Insights + LLM reasoning.
"""

from __future__ import annotations

import os

from fixtures._loader import load_model
from tools.schemas import (
    CaseFile,
    IUURule,
    RegionContext,
    RiskAssessment,
    Vessel,
    VesselDetection,
    VesselEvent,
)

_USE_FIXTURES = os.getenv("USE_FIXTURES", "1") == "1"


def calculate_risk(
    vessel: Vessel,
    events: list[VesselEvent],
    rules: list[IUURule],
    region: RegionContext,
    detections: list[VesselDetection] | None = None,
) -> RiskAssessment:
    """Pipeline: rule eval → score → classify."""
    if _USE_FIXTURES:
        # The dossier carries the canonical RiskAssessment for the demo vessel.
        # TODO(chan): replace with real LLM call once Gemini key is wired.
        if vessel.mmsi == "412345678":
            case = load_model("case_galapagos_demo", CaseFile)
            assert case.risk is not None  # dossier always populates this
            return case.risk
        # Default: low risk for any other fixture vessel.
        return RiskAssessment(
            vessel=vessel,
            region_id=region.region_id,
            risk_score=0.12,
            classification="safe",
            triggered_rules=[],
            evidence=[],
            reasoning="No rule violations observed for this vessel in the demo region.",
        )
    raise NotImplementedError("set USE_FIXTURES=1")


def cross_reference_dark_vessels(
    detections: list[VesselDetection],
    ais_vessels: list[Vessel],
    radius_km: float = 5.0,
) -> list[VesselDetection]:
    """Returns detections that have no matched MMSI within ``radius_km``."""
    if _USE_FIXTURES:
        # Fixture mode: trust the matched_mmsi field already on the detection.
        return [d for d in detections if d.matched_mmsi is None]
    raise NotImplementedError("set USE_FIXTURES=1")
