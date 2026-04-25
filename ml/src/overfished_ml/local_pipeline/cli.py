"""CLI for local and GX10 pipeline execution."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import Gx10Config, PipelinePaths, SparkConfig
from .remote import run_pipeline_on_gx10, sync_project_subset_to_gx10
from .runner import run_local_pipeline


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run overfished local medallion pipeline")
    parser.add_argument("--runtime", choices=["local", "gx10"], default="local")
    parser.add_argument("--input-path", type=Path, default=PipelinePaths.default().fishing_events_csv)
    parser.add_argument("--bronze-output", type=Path, default=PipelinePaths.default().bronze_output)
    parser.add_argument("--silver-output", type=Path, default=PipelinePaths.default().silver_output)
    parser.add_argument("--gold-output", type=Path, default=PipelinePaths.default().gold_output)
    parser.add_argument("--spark-driver-memory", default="4g")
    parser.add_argument("--spark-shuffle-partitions", type=int, default=8)
    parser.add_argument("--spark-master", default="local[*]")
    parser.add_argument("--sync-gx10", action="store_true", help="rsync required subset before remote run")
    parser.add_argument("--gx10-remote-python", default="python3")
    return parser


def _gx10_config_from_env() -> Gx10Config:
    required = {
        "GX10_HOST": os.getenv("GX10_HOST"),
        "GX10_USER": os.getenv("GX10_USER"),
        "GX10_REMOTE_WORKDIR": os.getenv("GX10_REMOTE_WORKDIR"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Missing GX10 environment variables: {joined}")
    return Gx10Config(
        host=required["GX10_HOST"] or "",
        user=required["GX10_USER"] or "",
        remote_workdir=required["GX10_REMOTE_WORKDIR"] or "",
        ssh_key_path=os.getenv("GX10_SSH_KEY_PATH"),
        port=int(os.getenv("GX10_SSH_PORT", "22")),
    )


def _as_paths(args: argparse.Namespace) -> PipelinePaths:
    return PipelinePaths(
        fishing_events_csv=args.input_path,
        bronze_output=args.bronze_output,
        silver_output=args.silver_output,
        gold_output=args.gold_output,
    )


def main() -> int:
    args = _build_parser().parse_args()
    paths = _as_paths(args)

    if args.runtime == "local":
        result = run_local_pipeline(
            paths=paths,
            spark_config=SparkConfig(
                master=args.spark_master,
                driver_memory=args.spark_driver_memory,
                shuffle_partitions=args.spark_shuffle_partitions,
            ),
        )
        print(
            "Pipeline completed. "
            f"bronze={result.bronze_count}, silver={result.silver_count}, "
            f"gold={result.gold_count}, gold_csv={result.gold_csv_path}"
        )
        return 0

    gx10 = _gx10_config_from_env()
    if args.sync_gx10:
        sync_project_subset_to_gx10(gx10, _repo_root())

    remote_paths = PipelinePaths(
        fishing_events_csv=Path("data/local_pipeline/sample_fishing_events.csv"),
        bronze_output=Path("data/local_pipeline/output/bronze_fishing_events"),
        silver_output=Path("data/local_pipeline/output/silver_fishing_events"),
        gold_output=Path("data/local_pipeline/output/gold_fishing_features"),
    )
    exit_code = run_pipeline_on_gx10(gx10, remote_python=args.gx10_remote_python, paths=remote_paths)
    if exit_code != 0:
        print(f"GX10 run failed with exit code {exit_code}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
