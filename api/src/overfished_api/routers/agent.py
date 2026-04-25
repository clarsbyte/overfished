"""LangChain vessel agents (see `../backend/*_agent.py` and `api/README.md`)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from overfished_api.deps import AgentBackendDep

router = APIRouter(prefix="/agent", tags=["agent"])


def _repo_root() -> Path:
    # api/src/overfished_api/routers/agent.py -> parents[4] == repo root
    return Path(__file__).resolve().parents[4]


def _ensure_backend_on_path() -> Path:
    root = _repo_root()
    backend = root / "backend"
    s = str(backend)
    if s not in sys.path:
        sys.path.insert(0, s)
    # README: keys in `backend/.env`; also load repo root `.env` for convenience.
    load_dotenv(root / ".env", override=False)
    load_dotenv(backend / ".env", override=False)
    return backend


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


# --- Four LangChain agents (README "Agent endpoints") ---


class GfwAgentRequest(BaseModel):
    query: str = Field(..., min_length=1, description="MMSI, IMO, or vessel name")
    days_back: int = Field(365, ge=1, le=3650)


class VesselAgentRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_miles: float = Field(100, ge=1, le=500)


class LawAgentRequest(BaseModel):
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    region_id: str | None = Field(None, min_length=1)
    port_country_code: str | None = None
    vessel_flag: str | None = None
    gear: str | None = None
    species: str | None = None

    @model_validator(mode="after")
    def _lat_lon_or_region(self) -> LawAgentRequest:
        if self.region_id:
            return self
        if self.latitude is not None and self.longitude is not None:
            return self
        raise ValueError("Provide either region_id or both latitude and longitude")


class CompleteAgentRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_miles: float = Field(50, ge=1, le=500)
    port_country_code: str | None = None
    mmsi: str | None = None


def _coerce_output(out: Any) -> str:
    """LangChain + Anthropic sometimes returns the agent's final message as
    a list of content blocks ({'text': ..., 'type': 'text'}) rather than a flat
    string. Flatten to text so the API contract is always {agent, output: str}
    and the frontend can safely render it as a React child.
    """
    if isinstance(out, str):
        return out
    if isinstance(out, list):
        parts: list[str] = []
        for block in out:
            if isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
                    continue
            parts.append(str(block))
        return "\n".join(p for p in parts if p)
    return str(out)


def _agent_response(agent: str, output: Any) -> dict[str, Any]:
    return {"agent": agent, "output": _coerce_output(output)}


@router.post("/gfw", summary="GFW IUU classification for one vessel")
async def post_agent_gfw(body: GfwAgentRequest) -> dict[str, Any]:
    _ensure_backend_on_path()

    def _run() -> Any:
        from gfw_agent import classify_vessel

        return classify_vessel(body.query, body.days_back)

    try:
        out = await asyncio.to_thread(_run)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail={"error": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "gfw agent failed") from exc
    return _agent_response("gfw_agent", out)


@router.post("/vessel", summary="AIS lookup near a coordinate")
async def post_agent_vessel(body: VesselAgentRequest) -> dict[str, Any]:
    _ensure_backend_on_path()

    def _run() -> Any:
        from vessel_agent import run_agent

        return run_agent(body.longitude, body.latitude, body.radius_miles)

    try:
        out = await asyncio.to_thread(_run)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail={"error": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "vessel agent failed") from exc
    return _agent_response("vessel_agent", out)


@router.post("/law", summary="Citation-backed legal dossier at a point or by region_id")
async def post_agent_law(body: LawAgentRequest) -> dict[str, Any]:
    _ensure_backend_on_path()

    def _run() -> Any:
        from regional_agent import evaluate_point, evaluate_region

        if body.region_id:
            return evaluate_region(body.region_id)
        lat, lon = body.latitude, body.longitude
        assert lat is not None and lon is not None
        return evaluate_point(
            lat,
            lon,
            port_country_code=body.port_country_code,
            vessel_flag=body.vessel_flag,
            gear=body.gear,
            species=body.species,
        )

    try:
        out = await asyncio.to_thread(_run)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=503, detail={"error": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "law agent failed") from exc
    return _agent_response("regional_agent", out)


@router.post("/complete", summary="Full multi-agent vessel-incursion pipeline")
async def post_agent_complete(body: CompleteAgentRequest) -> dict[str, Any]:
    _ensure_backend_on_path()

    def _run() -> Any:
        from pipeline_agent import evaluate_incident

        return evaluate_incident(
            body.latitude,
            body.longitude,
            body.radius_miles,
            body.port_country_code,
            body.mmsi,
        )

    try:
        out = await asyncio.to_thread(_run)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail={"error": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "pipeline agent failed") from exc
    return _agent_response("pipeline_agent", out)
