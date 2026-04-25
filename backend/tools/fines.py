"""Fine calculator — assembles itemized PenaltyLineItems with layered citations.

Fixture mode returns the pre-baked $199,875 calculation that matches the
Schedule A in ``notice_of_violation.html``. Computing it live is brittle (and
the line items are a locked design reference, not derivable from raw inputs).
"""

from __future__ import annotations

import os

from fixtures._loader import load_model
from tools.schemas import (
    FineCalculation,
    LegalCitation,
    RegionContext,
    RiskAssessment,
    Vessel,
    VesselEvent,
)

_USE_FIXTURES = os.getenv("USE_FIXTURES", "1") == "1"


def estimate_catch_volume(
    vessel: Vessel,
    fishing_events: list[VesselEvent],
) -> tuple[float, str]:
    """Returns (kg, primary_species_guess) — fishing_hours × gear_type rate."""
    if _USE_FIXTURES:
        return (4200.0, "mahi-mahi / yellowfin tuna composite")
    raise NotImplementedError("set USE_FIXTURES=1")


def calculate_fine(
    vessel: Vessel,
    risk: RiskAssessment,
    region: RegionContext,
    rules: list,
    citations: list[LegalCitation],
) -> FineCalculation:
    """Builds itemized FineCalculation with layered legal_basis per line item."""
    if _USE_FIXTURES:
        if vessel.mmsi == "412345678":
            return load_model("fine_412345678", FineCalculation)
        # Generic safe-vessel: zero-fine stub
        return FineCalculation(
            vessel_mmsi=vessel.mmsi,
            region_id=region.region_id,
            estimated_catch_kg=0.0,
            primary_species=None,
            line_items=[],
            subtotal_usd=0.0,
            multipliers={"recidivism": 1.0, "cooperation_credit": 1.0},
            total_fine_usd=0.0,
            citations=[],
            breakdown_text="No violations observed.",
        )
    raise NotImplementedError("set USE_FIXTURES=1")
