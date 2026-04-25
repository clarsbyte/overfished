"""Tests for JSON report and path resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from overfished_ml.sequence.report import (  # noqa: E402
    build_sequence_report,
    format_sequence_narration,
    resolve_allowed_csv_path,
    synthetic_events_dataframe,
)
from overfished_ml.sequence.train import TrainingConfig  # noqa: E402


def test_build_sequence_report_synthetic() -> None:
    df = synthetic_events_dataframe()
    r = build_sequence_report(
        dataframe=df,
        config=TrainingConfig(
            seq_len=3,
            batch_size=2,
            val_fraction=0.34,
            epochs=1,
            hidden_dim=8,
            top_k=2,
        ),
        top_k=2,
        max_val_rows=4,
    )
    assert "rnn" in r and "bilstm" in r
    assert r["rnn"]["n_val_rows"] >= 0
    assert "selected_model_type" in r
    assert "suspect_readout" in r
    text = format_sequence_narration(r)
    assert "RNN" in text or "rnn" in text.lower()
    assert "sus" in text.lower() or "uncertain" in text.lower() or "No high-uncertainty" in text


def test_resolve_allowed_rejects_parent_escape() -> None:
    root = Path(__file__).resolve().parent
    with pytest.raises(ValueError):
        resolve_allowed_csv_path("../../../etc/passwd", repo_root=root)
