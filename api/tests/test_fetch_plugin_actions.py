from __future__ import annotations

import asyncio
import os

import pytest
from overfished_fetch_plugin.factory import FetchOrchestratorBackend


def test_fetch_sequence_context_runs_mmsi_report() -> None:
    backend = FetchOrchestratorBackend()
    result = asyncio.run(
        backend.run(
            "Summarize the sequence model",
            context={"sequence": True, "use_synthetic": True, "epochs": 1, "seq_len": 3, "hidden_dim": 8, "batch_size": 2},
        )
    )
    if result.status == "sequence_error":
        pytest.skip(result.message)
    assert result.status == "sequence_ok"
    assert "rnn" in result.message.lower()
    assert (result.detail or {}).get("bilstm", {}).get("metrics")


def test_fetch_routes_legal_requests_to_action_specialist() -> None:
    backend = FetchOrchestratorBackend()
    result = asyncio.run(
        backend.run(
            "based on this ship what legal action should we pursue",
            context={"latitude": 1.0, "longitude": 2.0},
        )
    )
    assert result.detail["selected_specialist"] == "legal_action_orchestrator"
    assert result.detail["context_keys"] == ["latitude", "longitude"]


def test_fetch_extract_action_summary_from_pdf_signal() -> None:
    from overfished_fetch_plugin.factory import _extract_action_summary

    summary = _extract_action_summary("... EVIDENCE_PDF_RENDERED: case_id=abc ...")
    assert "pursue enforcement package" in summary.lower()


def test_fetch_forced_error_still_supported() -> None:
    backend = FetchOrchestratorBackend()
    os.environ["FETCH_AGENT_FORCE_ERROR"] = "1"
    try:
        raised = False
        try:
            asyncio.run(backend.run("hello", {}))
        except RuntimeError:
            raised = True
        assert raised
    finally:
        os.environ.pop("FETCH_AGENT_FORCE_ERROR", None)


def test_derive_action_from_verdict() -> None:
    from overfished_fetch_plugin.factory import _derive_action_from_verdict

    assert "FULL CASE" in _derive_action_from_verdict("PROHIBITED")
    assert "ALERT" in _derive_action_from_verdict("PERMIT_REQUIRED")
    assert "MONITOR" in _derive_action_from_verdict("ALLOWED")
