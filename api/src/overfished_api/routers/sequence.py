"""RNN / BiLSTM soft-probability reports (optional `overfished-ml` install)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/ml", tags=["ml-sequence"])


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


# --- in-process cache of the latest successful report ----------------------
# Used by GET /ml/sequence/latest (frontend polling) and by the LangChain
# `lookup_model_context` tool in backend/pipeline_agent.py so the supervisor
# can read static runtime context without re-running training.
_LATEST: dict[str, Any] | None = None


def _set_latest(report: dict[str, Any], *, source: str) -> None:
    global _LATEST
    _LATEST = {
        "ready": True,
        "report": report,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }


def get_latest_report() -> dict[str, Any] | None:
    """Public accessor for in-process callers (LangChain tools, tests)."""
    return _LATEST


class TrainingParams(BaseModel):
    """Subset of :class:`overfished_ml.sequence.TrainingConfig` for HTTP input."""

    epochs: int = Field(1, ge=1, le=50)
    seq_len: int = Field(4, ge=2, le=128)
    hidden_dim: int = Field(32, ge=4, le=1024)
    batch_size: int = Field(4, ge=1, le=256)
    val_fraction: float = Field(0.25, ge=0.05, lt=0.5)
    top_k: int = Field(3, ge=1, le=20)
    max_val_rows: int = Field(20, ge=0, le=500)


class SequenceReportRequest(BaseModel):
    use_sample: bool = Field(
        default=False,
        description="If true, run on built-in synthetic vessel events (ignores csv_path).",
    )
    csv_path: str | None = Field(
        default=None,
        description="Repo-relative (or absolute) path under repo root, e.g. `data/local_pipeline/sample_fishing_events.csv`.",
    )
    training: TrainingParams = Field(default_factory=TrainingParams)
    include_narration: bool = True


@router.get(
    "/sequence/demo",
    response_model=dict[str, Any],
    summary="Live RNN+BiLSTM soft-prob demo (synthetic data, ~10–20s)",
)
async def get_sequence_demo() -> dict[str, Any]:
    """Trains 1 epoch on a tiny built-in dataset; returns JSON + `narration` text."""
    return await _run_report(
        SequenceReportRequest(
            use_sample=True,
            include_narration=True,
            training=TrainingParams(
                epochs=1,
                seq_len=3,
                hidden_dim=8,
                batch_size=2,
                top_k=3,
                max_val_rows=8,
            ),
        ),
        source="demo",
    )


@router.post("/sequence/report", response_model=dict[str, Any])
async def post_sequence_report(body: SequenceReportRequest) -> dict[str, Any]:
    source = "canonical" if body.csv_path and not body.use_sample else "demo"
    return await _run_report(body, source=source)


CANONICAL_CSV = "data/local_pipeline/gold_vessel_detections_enriched.csv"


@router.post(
    "/sequence/run-canonical",
    response_model=dict[str, Any],
    summary="Train on canonical 300-row GFW CSV; result feeds map markers and agent context.",
)
async def post_run_canonical() -> dict[str, Any]:
    return await _run_report(
        SequenceReportRequest(
            use_sample=False,
            csv_path=CANONICAL_CSV,
            include_narration=True,
            training=TrainingParams(
                epochs=2,
                seq_len=4,
                hidden_dim=16,
                batch_size=8,
                top_k=3,
                max_val_rows=64,
            ),
        ),
        source="canonical",
    )


class SequenceLatestResponse(BaseModel):
    ready: bool
    report: dict[str, Any] | None = None
    generated_at: str | None = None
    source: Literal["demo", "canonical"] | None = None


@router.get("/sequence/latest", response_model=SequenceLatestResponse)
async def get_sequence_latest() -> SequenceLatestResponse:
    if _LATEST is None:
        return SequenceLatestResponse(ready=False)
    return SequenceLatestResponse(**_LATEST)


async def _run_report(body: SequenceReportRequest, *, source: str) -> dict[str, Any]:
    try:
        from overfished_ml.sequence.report import (
            build_sequence_report,
            format_sequence_narration,
            resolve_allowed_csv_path,
            synthetic_events_dataframe,
        )
        from overfished_ml.sequence.train import TrainingConfig
    except ImportError as exc:  # pragma: no cover - only when ml not installed
        raise HTTPException(
            status_code=503,
            detail={
                "error": "overfished-ml is not installed. From repo root: `pip install -e ./ml` and reinstall the API with optional `[ml]`.",
                "import_error": str(exc),
            },
        ) from exc

    cfg = TrainingConfig(
        seq_len=body.training.seq_len,
        batch_size=body.training.batch_size,
        val_fraction=body.training.val_fraction,
        epochs=body.training.epochs,
        hidden_dim=body.training.hidden_dim,
        top_k=body.training.top_k,
    )

    def _run() -> dict[str, Any]:
        if body.use_sample or not (body.csv_path and str(body.csv_path).strip()):
            report: dict[str, Any] = build_sequence_report(
                dataframe=synthetic_events_dataframe(),
                config=cfg,
                top_k=body.training.top_k,
                max_val_rows=body.training.max_val_rows,
            )
        else:
            p = resolve_allowed_csv_path(str(body.csv_path), repo_root=_repo_root())
            report = build_sequence_report(
                csv_path=p,
                config=cfg,
                top_k=body.training.top_k,
                max_val_rows=body.training.max_val_rows,
            )
        if body.include_narration:
            report = {
                **report,
                "narration": format_sequence_narration(report),
            }
        return report

    try:
        report = await asyncio.to_thread(_run)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc) or "sequence report failed") from exc

    _set_latest(report, source=source)
    return report
