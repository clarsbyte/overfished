from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from overfished_api.ports.agent import AgentBackend, AgentRunResult


class FetchOrchestratorBackend:
    """Fetch.ai-style orchestrator scaffold with deterministic behavior."""

    async def run(self, query: str, context: dict[str, Any] | None = None) -> AgentRunResult:
        started = time.perf_counter()
        simulated_latency = float(os.getenv("FETCH_AGENT_SIMULATED_LATENCY_SECONDS", "0"))
        if simulated_latency > 0:
            await asyncio.sleep(simulated_latency)

        if os.getenv("FETCH_AGENT_FORCE_ERROR", "").strip().lower() in {"1", "true", "yes"}:
            raise RuntimeError("FETCH_AGENT_FORCE_ERROR enabled")

        payload = context or {}
        if _looks_like_sequence_request(query, payload):
            try:
                return await _sequence_model_report(query, payload)
            except Exception as exc:
                err = str(exc) or exc.__class__.__name__
                return AgentRunResult(
                    status="sequence_error",
                    message=f"[fetch] RNN/LSTM sequence report failed: {err}. Install overfished-ml or check your data file path.",
                    detail={"error": err, "context": "overfished_ml.sequence"},
                )

        legal_mode = _looks_like_legal_action_request(query, payload)
        selected_specialist = "legal_action_orchestrator" if legal_mode else "chat_orchestrator"

        detail: dict[str, Any] = {
            "plugin": "overfished_fetch_plugin",
            "selected_specialist": selected_specialist,
            "context_keys": sorted(payload.keys()),
        }

        if legal_mode:
            try:
                legal_result = await _run_existing_pdf_agent_bridge(payload)
                response = legal_result["message"]
                detail["legal_action"] = legal_result["detail"]
            except Exception as exc:
                err_text = str(exc) or exc.__class__.__name__
                response = (
                    "[fetch] Legal-action route triggered, but existing PDF pipeline bridge "
                    f"failed: {err_text}. Falling back to analyst review recommendation."
                )
                detail["legal_action"] = {
                    "bridge": "pipeline_agent.evaluate_incident",
                    "error": err_text,
                    "action_summary": (
                        "Recommended action: route case to legal analyst queue with "
                        "available vessel context and retry PDF generation after dependency check."
                    ),
                }
        else:
            response = f"[fetch] Routed query to {selected_specialist}: {query}"

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return AgentRunResult(
            status="fetch_ok",
            message=response,
            detail={**detail, "elapsed_ms": elapsed_ms},
        )


def build_agent_backend() -> AgentBackend:
    """Construct Fetch-backed agent implementation."""
    return FetchOrchestratorBackend()


def _looks_like_sequence_request(query: str, context: dict[str, Any]) -> bool:
    if context.get("sequence") in (True, 1, "1", "true", "True", "yes", "on"):
        return True
    if any(str(context.get(k) or "").strip() for k in ("events_csv", "sequence_csv", "csv_path")):
        return True
    c = (query or "").lower()
    if "sequence model" in c or "bilstm" in c or "lstm" in c:
        return True
    if "rnn" in c and "sequence" in c:
        return True
    if "soft" in c and "prob" in c:
        return True
    if "softmax" in c:
        return True
    if re.search(r"\bsus\b|suspicious|sketchy|suspect|sus ships|ships.*\bsus\b", c):
        return True
    return False


def _sequence_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


async def _sequence_model_report(query: str, context: dict[str, Any]) -> AgentRunResult:
    from overfished_ml.sequence.report import (  # type: ignore[import-not-found]
        build_sequence_report,
        format_sequence_narration,
        resolve_allowed_csv_path,
        synthetic_events_dataframe,
    )
    from overfished_ml.sequence.train import TrainingConfig  # type: ignore[import-not-found]

    def _load_and_run() -> dict[str, Any]:
        repo = _sequence_repo_root()
        p_raw = (context.get("events_csv") or context.get("sequence_csv") or context.get("csv_path") or "").strip()
        if context.get("use_synthetic") in (True, 1, "1", "true", "yes", "on"):
            p_raw = ""
        top_k = int(context.get("top_k", 3))
        max_val = int(context.get("max_val_rows", 20))
        cfg = TrainingConfig(
            seq_len=int(context.get("seq_len", 4)),
            batch_size=int(context.get("batch_size", 4)),
            val_fraction=float(context.get("val_fraction", 0.25)),
            epochs=int(context.get("epochs", 1)),
            hidden_dim=int(context.get("hidden_dim", 32)),
            top_k=top_k,
        )
        if not p_raw:
            return build_sequence_report(
                dataframe=synthetic_events_dataframe(),
                config=cfg,
                top_k=top_k,
                max_val_rows=max_val,
            )
        return build_sequence_report(
            csv_path=resolve_allowed_csv_path(p_raw, repo_root=repo),
            config=cfg,
            top_k=top_k,
            max_val_rows=max_val,
        )

    started = time.perf_counter()
    report: dict[str, Any] = await asyncio.wait_for(
        asyncio.to_thread(_load_and_run),
        timeout=float(os.getenv("SEQUENCE_MODEL_REPORT_TIMEOUT_SECONDS", "120")),
    )
    narration = format_sequence_narration(report)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return AgentRunResult(
        status="sequence_ok",
        message=narration,
        detail={**report, "elapsed_ms": elapsed_ms, "query_preview": (query or "")[:200]},
    )


def _looks_like_legal_action_request(query: str, context: dict[str, Any]) -> bool:
    q = (query or "").lower()
    has_location = "latitude" in context and "longitude" in context
    asks_legal = any(
        token in q
        for token in (
            "legal action",
            "what should we pursue",
            "what action",
            "prosecute",
            "iuu",
            "illegal",
            "unc",
            "law",
            "dossier",
            "pdf",
        )
    )
    return has_location and asks_legal


async def _run_existing_pdf_agent_bridge(context: dict[str, Any]) -> dict[str, Any]:
    # Demo default: produce immediate, deterministic action from context.
    no_llm = os.getenv("FETCH_AGENT_FAST_NO_LLM", "1").strip().lower() in {"1", "true", "yes"}
    if no_llm:
        return _build_demo_action_from_context(context)

    # Hackathon fast-mode: query the legal dossier agent first for quick actionable guidance.
    fast_mode = os.getenv("FETCH_AGENT_FAST_MODE", "1").strip().lower() in {"1", "true", "yes"}
    if fast_mode:
        timeout = float(os.getenv("FETCH_AGENT_FAST_TIMEOUT_SECONDS", "10"))
        return await asyncio.wait_for(asyncio.to_thread(_invoke_fast_legal_agent, context), timeout=timeout)

    timeout = float(os.getenv("FETCH_AGENT_PDF_BRIDGE_TIMEOUT_SECONDS", "20"))
    return await asyncio.wait_for(asyncio.to_thread(_invoke_pipeline_agent, context), timeout=timeout)


def _invoke_pipeline_agent(context: dict[str, Any]) -> dict[str, Any]:
    backend_path = Path(__file__).resolve().parents[4] / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from pipeline_agent import evaluate_incident  # lazy import; requires backend deps/env

    latitude = float(context["latitude"])
    longitude = float(context["longitude"])
    radius_miles = float(context.get("radius_miles", 50))
    port_country_code = context.get("port_country_code")
    mmsi = context.get("mmsi")

    output = evaluate_incident(
        latitude=latitude,
        longitude=longitude,
        radius_miles=radius_miles,
        port_country_code=port_country_code,
        mmsi=mmsi,
    )
    action_summary = _extract_action_summary(output)
    return {
        "message": f"[fetch] Legal action recommendations generated via existing PDF agent.\n{action_summary}",
        "detail": {
            "bridge": "pipeline_agent.evaluate_incident",
            "latitude": latitude,
            "longitude": longitude,
            "radius_miles": radius_miles,
            "port_country_code": port_country_code,
            "mmsi": mmsi,
            "action_summary": action_summary,
            "raw_output": output,
        },
    }


def _invoke_fast_legal_agent(context: dict[str, Any]) -> dict[str, Any]:
    """Fast legal-action mode using the existing regional legal dossier agent."""
    backend_path = Path(__file__).resolve().parents[4] / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from regional_agent import evaluate_point  # lazy import; existing legal/PDF stack dependency path

    latitude = float(context["latitude"])
    longitude = float(context["longitude"])
    port_country_code = context.get("port_country_code")
    vessel_flag = context.get("vessel_flag")
    gear = context.get("gear")
    species = context.get("species")

    output = evaluate_point(
        latitude=latitude,
        longitude=longitude,
        port_country_code=port_country_code,
        vessel_flag=vessel_flag,
        gear=gear,
        species=species,
    )
    verdict = _extract_verdict_label(output)
    action_summary = _derive_action_from_verdict(verdict)
    return {
        "message": f"[fetch] Fast legal-action recommendation generated.\n{action_summary}",
        "detail": {
            "bridge": "regional_agent.evaluate_point",
            "mode": "fast_legal",
            "latitude": latitude,
            "longitude": longitude,
            "port_country_code": port_country_code,
            "vessel_flag": vessel_flag,
            "gear": gear,
            "species": species,
            "verdict": verdict,
            "action_summary": action_summary,
            "raw_output": output,
        },
    }


def _extract_action_summary(output: str) -> str:
    lowered = output.lower()
    if "evidence_pdf_rendered" in lowered:
        return (
            "Recommended action: pursue enforcement package and serve notice/inspection order "
            "using the rendered evidence PDF artifact."
        )
    if "not rendered (insufficient evidence" in lowered or "insufficient evidence" in lowered:
        return (
            "Recommended action: hold prosecution, continue monitoring, and gather additional "
            "AIS/SAR/legal evidence before escalation."
        )
    if "verdict: high" in lowered or "verdict: medium" in lowered:
        return (
            "Recommended action: initiate legal review and prepare prosecution memo; "
            "evidence threshold appears actionable."
        )
    return (
        "Recommended action: route case to legal analyst queue with current dossier and "
        "request human review for next enforcement step."
    )


def _extract_verdict_label(output: str) -> str:
    text = output or ""
    for line in text.splitlines():
        if line.strip().upper().startswith("VERDICT:"):
            return line.split(":", 1)[1].strip().upper()
    lowered = text.lower()
    if "high_risk" in lowered:
        return "HIGH_RISK"
    if "permit_required" in lowered:
        return "PERMIT_REQUIRED"
    if "prohibited" in lowered:
        return "PROHIBITED"
    if "allowed" in lowered:
        return "ALLOWED"
    if "insufficient_data" in lowered:
        return "INSUFFICIENT_DATA"
    return "UNKNOWN"


def _derive_action_from_verdict(verdict: str) -> str:
    if verdict in {"PROHIBITED", "HIGH_RISK"}:
        return (
            "Action: FULL CASE. Escalate to enforcement and legal review immediately, "
            "prepare prosecution packet, and initiate notice/inspection workflow."
        )
    if verdict == "PERMIT_REQUIRED":
        return (
            "Action: ALERT. Require permit/licensing proof, issue compliance notice, "
            "and schedule follow-up verification."
        )
    if verdict == "ALLOWED":
        return (
            "Action: MONITOR. No immediate prosecution; continue surveillance and "
            "record vessel behavior for trend monitoring."
        )
    if verdict == "INSUFFICIENT_DATA":
        return (
            "Action: ALERT. Collect additional evidence (AIS/SAR/legal context) before "
            "making an enforcement decision."
        )
    return (
        "Action: ANALYST REVIEW. Route to legal analyst with current dossier to determine "
        "next enforcement step."
    )


def _build_demo_action_from_context(context: dict[str, Any]) -> dict[str, Any]:
    """Low-latency deterministic action selector for demos/hackathons."""
    risk_hint = str(context.get("risk_hint", "")).strip().upper()
    is_high_risk = bool(context.get("is_high_risk")) or risk_hint in {"HIGH", "HIGH_RISK"}
    potential_risk = bool(context.get("potential_risk")) or risk_hint in {"MEDIUM", "POTENTIAL"}
    near_protected = bool(context.get("near_protected_area", True))
    has_ais_gap = bool(context.get("ais_gap", True))

    if is_high_risk or (near_protected and has_ais_gap):
        action = "FULL CASE"
        rationale = (
            "Dark-vessel/protected-area risk indicators justify immediate legal escalation "
            "and evidence package preparation."
        )
    elif potential_risk:
        action = "ALERT"
        rationale = "Risk indicators are present; request permit proof and initiate compliance notice."
    else:
        action = "MONITOR"
        rationale = "Insufficient high-confidence risk indicators for prosecution; continue surveillance."

    summary = f"Action: {action}. {rationale}"
    return {
        "message": f"[fetch] Fast legal-action recommendation generated.\n{summary}",
        "detail": {
            "bridge": "deterministic_demo_policy",
            "mode": "fast_no_llm",
            "action_summary": summary,
            "inputs_used": {
                "is_high_risk": is_high_risk,
                "potential_risk": potential_risk,
                "near_protected_area": near_protected,
                "ais_gap": has_ais_gap,
                "risk_hint": risk_hint,
            },
        },
    }
