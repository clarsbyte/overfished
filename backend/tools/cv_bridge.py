"""CV bridge — reads David's VesselDetection JSON outputs."""

from __future__ import annotations

import os
from datetime import datetime

from fixtures._loader import load_models
from tools.schemas import VesselDetection

_USE_FIXTURES = os.getenv("USE_FIXTURES", "1") == "1"


def get_cv_detections(
    region_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[VesselDetection]:
    """Return CV detections for the region.

    Two modes:
      * Live (real): HTTP call to David's inference service.
      * Fixture: load from ``backend/fixtures/cv_detections_<mmsi>.json`` for the
        demo vessel — the only set we have during the hackathon.
    """
    if _USE_FIXTURES:
        if region_id == "galapagos":
            return load_models("cv_detections_412345678", VesselDetection)
        return []
    raise NotImplementedError("set USE_FIXTURES=1")
