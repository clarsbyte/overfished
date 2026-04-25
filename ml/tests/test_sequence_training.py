"""Smoke tests for sequence dataset prep and training."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from overfished_ml.sequence import (  # noqa: E402
    TrainingConfig,
    build_mmsi_class_map,
    prepare_sequence_datasets,
    train_and_compare_models,
    train_sequence_model,
)


def test_build_mmsi_class_map_is_deterministic() -> None:
    dataframe = _synthetic_training_frame()
    map_a, inverse_a = build_mmsi_class_map(dataframe)
    map_b, inverse_b = build_mmsi_class_map(dataframe.sample(frac=1.0, random_state=7))

    assert map_a == map_b
    assert inverse_a == inverse_b


def test_prepare_sequence_datasets_creates_windows() -> None:
    dataframe = _synthetic_training_frame()
    bundle = prepare_sequence_datasets(dataframe, seq_len=3, stride=1, val_fraction=0.25)

    assert bundle.input_dim > 0
    assert len(bundle.mmsi_to_class) == 3
    assert len(bundle.train_dataset) > 0


def test_train_one_epoch_for_rnn_and_bilstm() -> None:
    dataframe = _synthetic_training_frame()
    config = TrainingConfig(
        seq_len=3,
        stride=1,
        val_fraction=0.34,
        batch_size=2,
        epochs=1,
        hidden_dim=8,
        top_k=2,
    )
    comparison = train_and_compare_models(dataframe, config=config)

    assert comparison.rnn_result.metrics["top1_accuracy"] >= 0.0
    assert comparison.bilstm_result.metrics["top1_accuracy"] >= 0.0
    assert comparison.selected_model_type in {"rnn", "bilstm", "ensemble"}

    # Also ensure direct trainer path works for both model types.
    bundle = prepare_sequence_datasets(dataframe, seq_len=3, stride=1, val_fraction=0.34)
    rnn_result = train_sequence_model("rnn", bundle, config=config)
    bilstm_result = train_sequence_model("bilstm", bundle, config=config)
    assert rnn_result.val_logits.shape[1] == len(bundle.class_to_mmsi)
    assert bilstm_result.val_logits.shape[1] == len(bundle.class_to_mmsi)


def _synthetic_training_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    base_time = pd.Timestamp("2025-01-01T00:00:00Z")
    vessels = ["100001111", "200002222", "300003333"]
    for vessel_idx, mmsi in enumerate(vessels):
        for step in range(6):
            rows.append(
                {
                    "mmsi": mmsi,
                    "event_start": base_time + pd.Timedelta(hours=step + vessel_idx * 24),
                    "detection_confidence": 0.6 + 0.01 * step + 0.05 * vessel_idx,
                    "distance_from_shore_km": 5 + vessel_idx * 10 + step,
                    "event_duration_hours": 1.0 + 0.2 * step,
                    "vessel_type": "fishing" if vessel_idx != 1 else "cargo",
                    "vessel_flag": "CHN" if vessel_idx == 0 else "USA",
                    "event_type": "fishing" if step % 2 == 0 else "transit",
                    "detection_source": "SAR",
                }
            )
    return pd.DataFrame(rows)
