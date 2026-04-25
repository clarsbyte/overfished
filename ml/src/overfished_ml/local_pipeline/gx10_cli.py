"""GX10 helpers: sync, remote image enrich, pull artifacts. Env: GX10_HOST, GX10_USER, GX10_REMOTE_WORKDIR.

Aerial ship JPEGs (from ``archive.zip`` → ``data/datasets/ships-aerial-images/``) are assigned
with ``overfished-assign-aerial`` (see ``overfished_ml.image_enrichment.assign_aerial_pool``).
Rsync a zip or extracted tree via ``GX10_SYNC_EXTRA=archive.zip`` (comma-separated paths) on sync.
``pull`` includes ``vessel_images/`` and ``vessel_cards.json`` by default.
"""

from __future__ import annotations

import argparse
import os
import sys

from .config import Gx10Config, _repo_root
from .remote import (
    pull_gx10_artifacts,
    run_enrich_images_on_gx10,
    sync_project_subset_to_gx10,
)


def _gx10_config_from_env() -> Gx10Config:
    required = {
        "GX10_HOST": os.getenv("GX10_HOST"),
        "GX10_USER": os.getenv("GX10_USER"),
        "GX10_REMOTE_WORKDIR": os.getenv("GX10_REMOTE_WORKDIR"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"Missing GX10 environment variables: {', '.join(missing)}")
    return Gx10Config(
        host=required["GX10_HOST"] or "",
        user=required["GX10_USER"] or "",
        remote_workdir=required["GX10_REMOTE_WORKDIR"] or "",
        ssh_key_path=os.getenv("GX10_SSH_KEY_PATH"),
        port=int(os.getenv("GX10_SSH_PORT", "22")),
    )


def main() -> int:
    repo = _repo_root()
    p = argparse.ArgumentParser(prog="overfished-gx10", description="ASUS GX10: rsync, enrich, pull")
    p.add_argument(
        "command",
        choices=["sync", "enrich", "pull"],
        help="sync: push ml+data; enrich: run overfished-enrich-images on host; pull: rsync outputs/cache/images/cards back",
    )
    p.add_argument(
        "--minimal-data",
        action="store_true",
        help="sync: only data/local_pipeline (not full data/)",
    )
    p.add_argument("--input-csv", default="data/gold_vessel_detections_enriched.csv", help="enrich: repo-relative")
    p.add_argument("--output-csv", default="data/gold_vessel_detections_enriched.csv")
    p.add_argument(
        "--extra-enrich-args",
        default="",
        help="Extra args passed to overfished-enrich-images (quote for spaces).",
    )
    args = p.parse_args()
    try:
        cfg = _gx10_config_from_env()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.command == "sync":
        sync_project_subset_to_gx10(
            cfg,
            repo,
            include_data_tree=not args.minimal_data,
        )
        return 0
    if args.command == "enrich":
        code = run_enrich_images_on_gx10(
            cfg,
            input_csv=args.input_csv,
            output_csv=args.output_csv,
            extra_args=args.extra_enrich_args,
        )
        if code != 0:
            print(f"Remote enrich failed (exit {code})", file=sys.stderr)
        return code
    if args.command == "pull":
        pull_gx10_artifacts(cfg, repo)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
