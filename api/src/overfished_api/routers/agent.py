from __future__ import annotations

import asyncio
import json
import queue as _queue
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from overfished_api.deps import AgentBackendDep

_BACKEND_DIR = Path(__file__).resolve().parents[4] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
load_dotenv(_BACKEND_DIR / ".env", override=False)

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    query: str = Field(..., min_length=1)
    context: dict[str, Any] | None = None


@router.post("/run")
async def run_agent(body: AgentRunRequest, backend: AgentBackendDep) -> dict[str, Any]:
    result = await backend.run(body.query, body.context)
    return {
        "status": result.status,
        "message": result.message,
        "detail": result.detail,
    }


class CompleteRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_miles: float = Field(50.0, gt=0, le=500)
    port_country_code: str | None = Field(None, min_length=3, max_length=3)
    mmsi: str | None = None


@router.post("/complete")
async def run_pipeline(body: CompleteRequest) -> dict[str, Any]:
    try:
        from pipeline_agent import evaluate_incident_structured
    except ImportError as exc:
        raise HTTPException(500, f"backend import failed: {exc}") from exc

    try:
        result = await asyncio.to_thread(
            evaluate_incident_structured,
            body.latitude,
            body.longitude,
            radius_miles=body.radius_miles,
            port_country_code=body.port_country_code,
            mmsi=body.mmsi,
        )
    except Exception as exc:
        raise HTTPException(502, f"pipeline failed: {exc}") from exc

    return {"agent": "pipeline", **result}


@router.get("/complete/stream")
async def stream_pipeline(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_miles: float = Query(50.0, gt=0, le=500),
    port_country_code: str | None = Query(None, min_length=3, max_length=3),
    mmsi: str | None = Query(None),
) -> StreamingResponse:
    """SSE endpoint — streams pipeline stage events then the final result.

    Each event is a JSON object on a `data:` line:
      {"stage": "<name>", "status": "started"|"running"|"done"|"error"|"complete", "detail": ...}

    The final event has stage="complete" and includes the full result dict.
    Connect with EventSource or fetch+ReadableStream.
    """
    try:
        from pipeline_agent import evaluate_incident_structured
    except ImportError as exc:
        raise HTTPException(500, f"backend import failed: {exc}") from exc

    progress_q: _queue.Queue = _queue.Queue()

    async def event_generator():
        async def _run():
            try:
                return await asyncio.to_thread(
                    evaluate_incident_structured,
                    latitude,
                    longitude,
                    radius_miles=radius_miles,
                    port_country_code=port_country_code,
                    mmsi=mmsi,
                    progress_queue=progress_q,
                )
            finally:
                progress_q.put(None)  # sentinel — signals the loop to stop

        task = asyncio.create_task(_run())

        while True:
            try:
                event = progress_q.get_nowait()
            except _queue.Empty:
                await asyncio.sleep(0.05)
                continue
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

        try:
            result = await task
        except Exception as exc:
            yield f"data: {json.dumps({'stage': 'error', 'status': 'error', 'detail': str(exc)})}\n\n"
            return

        yield f"data: {json.dumps({'stage': 'complete', 'status': 'done', 'result': {'agent': 'pipeline', **result}})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
