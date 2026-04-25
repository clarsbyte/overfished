"""CLI for local and GX10 pipeline execution."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path

from .config import Gx10Config, PipelinePaths, SparkConfig
from .config import _repo_root
from .remote import run_pipeline_on_gx10, sync_project_subset_to_gx10
from .runner import run_local_pipeline


def _build_parser() -> argparse.ArgumentParser:
    e = SparkConfig.from_env()
    parser = argparse.ArgumentParser(description="Run overfished local medallion pipeline")
    parser.add_argument("--runtime", choices=["local", "gx10"], default="local")
    p_default = PipelinePaths.default()
    parser.add_argument("--input-path", type=Path, default=p_default.fishing_events_csv)
    parser.add_argument("--bronze-output", type=Path, default=p_default.bronze_output)
    parser.add_argument("--silver-output", type=Path, default=p_default.silver_output)
    parser.add_argument("--gold-output", type=Path, default=p_default.gold_output)
    parser.add_argument("--spark-master", default=None, help=f"default: env or {e.master!r}")
    parser.add_argument("--spark-driver-memory", default=None, help=f"default: env or {e.driver_memory!r}")
    parser.add_argument("--spark-shuffle-partitions", type=int, default=None, help=f"default: env or {e.shuffle_partitions}")
    parser.add_argument(
        "--sync-gx10",
        action="store_true",
        help="rsync ml/ + data/ to GX10 (see also --gx10-minimal-data-sync)",
    )
    parser.add_argument(
        "--gx10-minimal-data-sync",
        action="store_true",
        help="Sync only data/local_pipeline instead of full data/ (smaller, excludes top-level data/*.csv).",
    )
    parser.add_argument("--gx10-remote-python", default=os.getenv("GX10_REMOTE_PYTHON", "python3"))
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


def _merged_spark_config(args: argparse.Namespace) -> SparkConfig:
    b = SparkConfig.from_env()
    shuf = (
        b.shuffle_partitions
        if args.spark_shuffle_partitions is None
        else int(args.spark_shuffle_partitions)
    )
    return SparkConfig(
        app_name=b.app_name,
        master=args.spark_master or b.master,
        driver_memory=args.spark_driver_memory or b.driver_memory,
        executor_memory=b.executor_memory,
        shuffle_partitions=shuf,
        adaptive_enabled=b.adaptive_enabled,
        log_level=b.log_level,
    )


def _spark_args_for_remote(sc: SparkConfig) -> str:
    return " ".join(
        [
            "--spark-master",
            shlex.quote(sc.master),
            "--spark-driver-memory",
            shlex.quote(sc.driver_memory),
            "--spark-shuffle-partitions",
            str(sc.shuffle_partitions),
        ]
    )


def main() -> int:
    args = _build_parser().parse_args()
    paths = _as_paths(args)
    sc = _merged_spark_config(args)

    if args.runtime == "local":
        result = run_local_pipeline(paths=paths, spark_config=sc)
        print(
            "Pipeline completed. "
            f"bronze={result.bronze_count}, silver={result.silver_count}, "
            f"gold={result.gold_count}, gold_csv={result.gold_csv_path}"
        )
        return 0

    gx10 = _gx10_config_from_env()
    if args.sync_gx10:
        sync_project_subset_to_gx10(
            gx10,
            _repo_root(),
            include_data_tree=not args.gx10_minimal_data_sync,
        )

    exit_code = run_pipeline_on_gx10(
        gx10,
        remote_python=args.gx10_remote_python,
        paths=paths,
        repo_root=_repo_root(),
        extra_pipeline_args=_spark_args_for_remote(sc),
    )
    if exit_code != 0:
        print(f"GX10 run failed with exit code {exit_code}", file=sys.stderr)
    return exit_code
