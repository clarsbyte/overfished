"""Train RNN + BiLSTM, ensemble soft probabilities, and JSON-friendly summaries."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
import torch

from .metrics import classification_metrics, ensemble_probabilities
from .train import (
    ModelTrainingResult,
    TrainingComparisonResult,
    TrainingConfig,
    train_and_compare_models,
)


def resolve_allowed_csv_path(user_path: str, *, repo_root: Path) -> Path:
    """Allow only CSV/TSV files under `repo_root` (reduces path traversal from API inputs)."""
    root = repo_root.resolve()
    raw = Path(user_path)
    path = (root / raw).resolve() if not raw.is_absolute() else raw.resolve()
    if path != root:
        _ = path.relative_to(root)  # raises if outside root
    if path.suffix.lower() not in {".csv", ".tsv"}:
        raise ValueError("Only .csv or .tsv data files are allowed.")
    if not path.is_file():
        raise FileNotFoundError(f"Data file not found: {path}")
    return path


def synthetic_events_dataframe() -> pd.DataFrame:
    """Same shape as ml/tests `test_synthetic_training_frame` — for demos without a CSV."""
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


def normalize_fishing_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Map common GFW / export column names to sequence pipeline expectations."""
    df = dataframe.copy()
    if "mmsi" not in df.columns and "vessel.ssvid" in df.columns:
        df["mmsi"] = df["vessel.ssvid"].astype(str)
    if "mmsi" not in df.columns and "vessel_id" in df.columns:
        df["mmsi"] = df["vessel_id"].astype(str)
    if "event_start" not in df.columns and "start" in df.columns:
        df["event_start"] = df["start"]
    if "event_start" not in df.columns and "event_end" in df.columns and "end" in df.columns:
        df["event_start"] = df.get("end", df["event_end"])
    return df


def _probs_to_topk_rows(
    probabilities: torch.Tensor,
    targets: torch.Tensor,
    class_to_mmsi: dict[int, str],
    top_k: int,
) -> list[dict[str, Any]]:
    if not probabilities.numel():
        return []
    k = min(top_k, probabilities.shape[1])
    values, indices = torch.topk(probabilities, k=k, dim=1)
    rows: list[dict[str, object]] = []
    for row_i in range(probabilities.shape[0]):
        true_c = int(targets[row_i].item())
        pred_items = []
        for j in range(k):
            cid = int(indices[row_i, j].item())
            p = float(values[row_i, j].item())
            if math.isnan(p) or p < 0.0:
                p = 0.0
            pred_items.append(
                {
                    "mmsi": class_to_mmsi.get(cid, str(cid)),
                    "class_id": cid,
                    "probability": p,
                }
            )
        rows.append(
            {
                "row_index": row_i,
                "true_mmsi": class_to_mmsi.get(true_c, str(true_c)),
                "true_class_id": true_c,
                "topk_predictions": pred_items,
            }
        )
    return rows  # type: ignore[return-value]


def _model_result_to_summary(
    result: ModelTrainingResult,
    comparison: TrainingComparisonResult,
    *,
    top_k: int,
    max_val_rows: int,
) -> dict[str, Any]:
    class_to_mmsi = comparison.dataset_bundle.class_to_mmsi
    rows = _probs_to_topk_rows(
        result.val_probabilities,
        result.val_targets,
        class_to_mmsi,
        top_k,
    )[:max_val_rows]
    return {
        "model_type": result.model_type,
        "metrics": dict(result.metrics),
        "n_val_rows": int(result.val_probabilities.shape[0]) if result.val_probabilities.numel() else 0,
        "n_classes": len(class_to_mmsi),
        "val_rows_sample": rows,
    }


def build_sequence_report(
    *,
    dataframe: pd.DataFrame | None = None,
    csv_path: Path | str | None = None,
    config: TrainingConfig | None = None,
    top_k: int = 3,
    max_val_rows: int = 20,
) -> dict[str, Any]:
    """
    Run `train_and_compare_models` and return a JSON-serializable report including
    soft per-class probabilities (summarized as top-k per validation row) for
    RNN, BiLSTM, and a simple average ensemble.
    """
    if dataframe is not None:
        working = normalize_fishing_dataframe(dataframe)
    elif csv_path is not None:
        working = normalize_fishing_dataframe(pd.read_csv(Path(csv_path)))
    else:
        raise ValueError("Provide `dataframe` or `csv_path`, or use synthetic data helper.")

    cfg = config or TrainingConfig(
        seq_len=4,
        stride=1,
        val_fraction=0.25,
        batch_size=4,
        epochs=1,
        hidden_dim=32,
        num_layers=1,
        top_k=top_k,
    )

    comparison: TrainingComparisonResult = train_and_compare_models(working, config=cfg)

    rnn_sum = _model_result_to_summary(comparison.rnn_result, comparison, top_k=top_k, max_val_rows=max_val_rows)
    lstm_sum = _model_result_to_summary(
        comparison.bilstm_result, comparison, top_k=top_k, max_val_rows=max_val_rows
    )

    ensemble_val_summary: list[dict[str, Any]] | None = None
    ensemble_row_metrics: dict[str, float] | None = None
    r = comparison.rnn_result
    b = comparison.bilstm_result
    if r.val_probabilities.numel() and b.val_probabilities.numel() and r.val_probabilities.shape == b.val_probabilities.shape:
        ens = ensemble_probabilities([r.val_probabilities, b.val_probabilities])
        ens_logits = torch.log(ens.clamp(min=1e-12))
        ensemble_row_metrics = classification_metrics(ens_logits, r.val_targets, top_k=cfg.top_k)
        ensemble_val_summary = _probs_to_topk_rows(ens, r.val_targets, comparison.dataset_bundle.class_to_mmsi, top_k)[
            :max_val_rows
        ]

    ens_block: dict[str, Any] | None = (
        {
            "metrics": ensemble_row_metrics,
            "n_val_rows": rnn_sum["n_val_rows"],
            "val_rows_sample": ensemble_val_summary,
        }
        if ensemble_val_summary is not None
        else None
    )
    return {
        "class_to_mmsi": {str(k): v for k, v in comparison.dataset_bundle.class_to_mmsi.items()},
        "feature_columns": list(comparison.dataset_bundle.feature_columns),
        "selected_model_type": comparison.selected_model_type,
        "ensemble_val_metrics": ensemble_row_metrics,
        "rnn": rnn_sum,
        "bilstm": lstm_sum,
        "ensemble": ens_block,
        "suspect_readout": _suspect_readout_from_ensemble(ens_block, rnn_sum),
    }


def _suspect_readout_from_ensemble(
    ensemble_block: dict[str, Any] | None,
    rnn_block: dict[str, Any],
) -> dict[str, Any]:
    """
    Heuristic "sus" list: windows where the ensemble top-1 MMSI disagrees with the label,
    or confidence is very low (demo / triage only — not ground truth IUU).
    """
    rows = (ensemble_block or {}).get("val_rows_sample") or rnn_block.get("val_rows_sample") or []
    low_conf = float(0.4)
    suspects: list[dict[str, Any]] = []
    for row in rows:
        preds = row.get("topk_predictions") or []
        if not preds:
            continue
        top = preds[0]
        p = float(top.get("probability", 0.0))
        true_m = str(row.get("true_mmsi", ""))
        guess = str(top.get("mmsi", ""))
        if guess != true_m:
            suspects.append(
                {
                    "true_mmsi": true_m,
                    "model_top_mmsi": guess,
                    "confidence": p,
                    "note": "top-1 guess disagrees with sequence label (worth review / more features).",
                }
            )
        elif p < low_conf:
            suspects.append(
                {
                    "true_mmsi": true_m,
                    "model_top_mmsi": guess,
                    "confidence": p,
                    "note": f"low confidence (P < {low_conf:.0%}) on identity; treat as uncertain.",
                }
            )
    return {
        "suspect_windows": suspects,
        "count": len(suspects),
    }


def format_sequence_narration(report: dict[str, Any]) -> str:
    """Short human-readable summary for agent `message` fields (not LLM)."""
    pick = str(report.get("selected_model_type", "unknown"))
    rnn = report.get("rnn") or {}
    bilstm = report.get("bilstm") or {}
    r_m = rnn.get("metrics") or {}
    b_m = bilstm.get("metrics") or {}
    ens = report.get("ensemble_val_metrics") or (report.get("ensemble") or {}).get("metrics")
    rnn_acc = r_m.get("top1_accuracy", 0.0)
    b_acc = b_m.get("top1_accuracy", 0.0)
    e_acc = ens.get("top1_accuracy", 0.0) if isinstance(ens, dict) else 0.0
    n_classes = rnn.get("n_classes", 0)
    n_val = rnn.get("n_val_rows", 0)
    lines = [
        "Vessel-sequence (MMSI identity) model summary from RNN, BiLSTM, and a probability ensemble.",
        f"Validation windows: {n_val}; vessels (classes): {n_classes}.",
        f"RNN validation top-1 accuracy: {rnn_acc:.1%}. BiLSTM: {b_acc:.1%}.",
    ]
    if e_acc > 0.0 or isinstance(ens, dict):
        lines.append(f"Ensemble (soft average of RNN+BiLSTM) top-1: {e_acc:.1%}.")
    lines.append(f"Best single / tie-breaker selection in training compare: {pick}.")
    sample = rnn.get("val_rows_sample") or []
    if sample:
        first = sample[0]
        true_m = first.get("true_mmsi", "?")
        top0 = (first.get("topk_predictions") or [{}])[0] if first.get("topk_predictions") else {}
        mmsi_guess = top0.get("mmsi", "?")
        p = top0.get("probability", 0.0)
        lines.append(
            f"Example val row: true MMSI {true_m}; RNN top guess {mmsi_guess} (P≈{float(p):.2f})."
        )
    sus = report.get("suspect_readout") or {}
    win = sus.get("suspect_windows") or []
    if win:
        bits = [
            f"MMSI {w.get('true_mmsi')}: model leans {w.get('model_top_mmsi')} (P≈{float(w.get('confidence', 0)):.2f})"
            for w in win[:5]
        ]
        lines.append(
            "Most “sus” or uncertain for triage (ensemble soft scores; not a legal verdict): " + "; ".join(bits) + "."
        )
    elif n_val:
        lines.append("No high-uncertainty windows in the sampled val rows (for this tiny run).")
    return " ".join(lines)
