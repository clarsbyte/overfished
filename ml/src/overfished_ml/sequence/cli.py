"""CLI: print JSON sequence model report (RNN / BiLSTM / ensemble soft scores)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .report import build_sequence_report, format_sequence_narration, synthetic_events_dataframe
from .train import TrainingConfig


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train RNN + BiLSTM on vessel event sequences; output JSON soft-probability report."
    )
    parser.add_argument(
        "csv",
        nargs="?",
        type=str,
        help="Path to events CSV (columns mmsi+event_start or vessel.ssvid+start).",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use built-in tiny synthetic data instead of a file.",
    )
    parser.add_argument(
        "--epochs", type=int, default=1, help="Training epochs (default: 1 for quick runs)."
    )
    parser.add_argument(
        "--seq-len", type=int, default=4, help="Window length for sequences (default: 4).",
    )
    parser.add_argument(
        "--hidden", type=int, default=32, help="RNN/LSTM hidden size (default: 32).",
    )
    parser.add_argument(
        "--narration", action="store_true", help="Print a one-line text summary to stderr after JSON.",
    )
    args = parser.parse_args()

    cfg = TrainingConfig(
        seq_len=args.seq_len,
        batch_size=4,
        epochs=args.epochs,
        hidden_dim=args.hidden,
        val_fraction=0.25,
        top_k=3,
    )
    if args.synthetic:
        report = build_sequence_report(dataframe=synthetic_events_dataframe(), config=cfg)
    elif args.csv:
        path = Path(args.csv)
        if not path.is_file():
            print(json.dumps({"error": f"not a file: {path}"}, indent=2), file=sys.stderr)
            raise SystemExit(1)
        report = build_sequence_report(csv_path=path, config=cfg)
    else:
        parser.error("Provide a CSV path or --synthetic")

    print(json.dumps(report, indent=2))
    if args.narration:
        print(format_sequence_narration(report), file=sys.stderr)


if __name__ == "__main__":
    main()
