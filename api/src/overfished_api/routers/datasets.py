"""Host canonical demo datasets for the map so the browser does not duplicate `data/`."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/datasets", tags=["datasets"])

GOLD_VESSEL_CSV = Path("data") / "local_pipeline" / "gold_vessel_detections_enriched.csv"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


@router.get(
    "/gold_vessel_detections_enriched",
    response_class=FileResponse,
    summary="Canonical 300-vessel GFW gold table (same file ML + sequence use).",
)
async def get_gold_vessel_detections_enriched() -> FileResponse:
    path = _repo_root() / GOLD_VESSEL_CSV
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Missing {GOLD_VESSEL_CSV}; run the local pipeline or copy the gold CSV into place.",
        )
    return FileResponse(
        path,
        media_type="text/csv",
        filename=path.name,
    )
