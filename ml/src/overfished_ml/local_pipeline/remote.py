"""Remote execution helpers for ASUS Ascent GX10 over SSH."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import Gx10Config, PipelinePaths, _repo_root


def _ssh_target(config: Gx10Config) -> str:
    return f"{config.user}@{config.host}"


def _ssh_base_command(config: Gx10Config) -> list[str]:
    cmd = ["ssh", "-p", str(config.port)]
    if config.ssh_key_path:
        cmd.extend(["-i", config.ssh_key_path])
    cmd.append(_ssh_target(config))
    return cmd


def _rsync_ssh_e(config: Gx10Config) -> str:
    if config.ssh_key_path:
        return f"ssh -i {config.ssh_key_path} -p {config.port}"
    return f"ssh -p {config.port}"


def _repo_relative_path(repo_root: Path, p: Path) -> str:
    return p.resolve().relative_to(repo_root.resolve()).as_posix()


def sync_project_subset_to_gx10(
    config: Gx10Config,
    repo_root: Path,
    *,
    include_data_tree: bool = True,
) -> None:
    """Sync `ml/`, and optionally the full `data/` tree, to `GX10_REMOTE_WORKDIR` (layout mirrors repo).

    Set `include_data_tree=False` to only sync `data/local_pipeline/`.
    Use env `GX10_SYNC_EXTRA` as comma-separated **repo-relative** extra paths to rsync
    (files or directories) after the main sync.
    """
    work = config.remote_workdir.rstrip("/")
    remote_dir = f"{_ssh_target(config)}:{work}/"
    for name in ("ml",):
        local = repo_root / name
        if not local.is_dir():
            continue
        subprocess.run(
            [
                "rsync",
                "-az",
                "--delete",
                "-e",
                _rsync_ssh_e(config),
                str(local) + "/",
                f"{_ssh_target(config)}:{work}/{name}/",
            ],
            check=True,
        )

    if include_data_tree and (repo_root / "data").is_dir():
        subprocess.run(
            [
                "rsync",
                "-az",
                "--delete",
                "-e",
                _rsync_ssh_e(config),
                str(repo_root / "data") + "/",
                f"{_ssh_target(config)}:{work}/data/",
            ],
            check=True,
        )
    else:
        lp = repo_root / "data" / "local_pipeline"
        if lp.is_dir():
            subprocess.run(
                [
                    "rsync",
                    "-az",
                    "--delete",
                    "-e",
                    _rsync_ssh_e(config),
                    str(lp) + "/",
                    f"{_ssh_target(config)}:{work}/data/local_pipeline/",
                ],
                check=True,
            )

    extra = (os.getenv("GX10_SYNC_EXTRA", "") or "").strip()
    if not extra:
        return
    for part in (x.strip() for x in extra.split(",") if x.strip()):
        src = (repo_root / part).resolve()
        if not src.exists():
            continue
        rdest = f"{_ssh_target(config)}:{work}/{Path(part).parent.as_posix()}/"
        subprocess.run(
            [
                "rsync",
                "-az",
                "-e",
                _rsync_ssh_e(config),
                str(src) if src.is_file() else str(src) + "/",
                rdest,
            ],
            check=True,
        )


def run_pipeline_on_gx10(
    config: Gx10Config,
    *,
    remote_python: str = "python3",
    paths: PipelinePaths | None = None,
    repo_root: Path | None = None,
    extra_pipeline_args: str = "",
) -> int:
    """Run the pipeline on the remote with CWD = repo root; paths are repo-relative."""
    pipeline_paths = paths or PipelinePaths.default()
    root = repo_root or _repo_root()
    p = pipeline_paths
    in_path = _repo_relative_path(root, p.fishing_events_csv)
    b_path = _repo_relative_path(root, p.bronze_output)
    s_path = _repo_relative_path(root, p.silver_output)
    g_path = _repo_relative_path(root, p.gold_output)
    work = config.remote_workdir.rstrip("/")
    remote_cmd = (
        f"cd {work} && {remote_python} -m overfished_ml.local_pipeline.cli "
        f"--runtime local --input-path {in_path} --bronze-output {b_path} "
        f"--silver-output {s_path} --gold-output {g_path} {extra_pipeline_args}"
    )
    return subprocess.run([*_ssh_base_command(config), remote_cmd], check=False).returncode


def run_enrich_images_on_gx10(
    config: Gx10Config,
    *,
    remote_python: str = "python3",
    input_csv: str = "data/gold_vessel_detections_enriched.csv",
    output_csv: str = "data/gold_vessel_detections_enriched.csv",
    cache_path: str = "data/local_pipeline/vessel_image_cache.json",
    miss_path: str = "data/local_pipeline/vessel_image_misses.json",
    extra_args: str = "",
) -> int:
    """Run `overfished-enrich-images` on the remote; paths are repo-relative to repo root on GX10."""
    work = config.remote_workdir.rstrip("/")
    cmd = (
        f"cd {work} && {remote_python} -m overfished_ml.image_enrichment.cli "
        f"--input-csv {input_csv} --output-csv {output_csv} --cache-path {cache_path} "
        f"--miss-report-path {miss_path} {extra_args}"
    )
    return subprocess.run([*_ssh_base_command(config), cmd], check=False).returncode


def pull_gx10_artifacts(
    config: Gx10Config,
    repo_root: Path,
    *,
    relpaths: list[str] | None = None,
) -> None:
    """Rsync paths from the remote workdir (repo layout) to this machine."""
    default = [
        "data/local_pipeline/output",
        "data/local_pipeline/vessel_image_cache.json",
        "data/local_pipeline/vessel_image_misses.json",
        "data/gold_vessel_detections_enriched.csv",
    ]
    to_pull = relpaths or default
    work = config.remote_workdir.rstrip("/")
    r0 = f"{_ssh_target(config)}:{work}"
    ssh = _rsync_ssh_e(config)
    for rel in to_pull:
        relp = rel.rstrip("/")
        local = (repo_root / relp).resolve()
        local.parent.mkdir(parents=True, exist_ok=True)
        rsrc = f"{r0}/{relp}"
        is_file = Path(relp).suffix in {".csv", ".json", ".parquet", ".tsv", ".txt"}
        if is_file:
            subprocess.run(
                ["rsync", "-az", "-e", ssh, rsrc, str(local)],
                check=True,
            )
        else:
            subprocess.run(
                ["rsync", "-az", "-e", ssh, f"{rsrc}/", f"{str(local)}/"],
                check=True,
            )
