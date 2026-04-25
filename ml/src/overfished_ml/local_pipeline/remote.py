"""Remote execution helpers for ASUS Ascent GX10 over SSH."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Gx10Config, PipelinePaths


def _ssh_target(config: Gx10Config) -> str:
    return f"{config.user}@{config.host}"


def _ssh_base_command(config: Gx10Config) -> list[str]:
    cmd = ["ssh", "-p", str(config.port)]
    if config.ssh_key_path:
        cmd.extend(["-i", config.ssh_key_path])
    cmd.append(_ssh_target(config))
    return cmd


def sync_project_subset_to_gx10(config: Gx10Config, repo_root: Path) -> None:
    """Sync only required folders for pipeline execution to remote host."""
    rsync_cmd = ["rsync", "-az", "--delete", "-e", f"ssh -p {config.port}"]
    if config.ssh_key_path:
        rsync_cmd = ["rsync", "-az", "--delete", "-e", f"ssh -i {config.ssh_key_path} -p {config.port}"]
    rsync_cmd.extend(
        [
            str(repo_root / "ml"),
            str(repo_root / "data" / "local_pipeline"),
            f"{_ssh_target(config)}:{config.remote_workdir}",
        ]
    )
    subprocess.run(rsync_cmd, check=True)


def run_pipeline_on_gx10(
    config: Gx10Config,
    *,
    remote_python: str = "python3",
    paths: PipelinePaths | None = None,
) -> int:
    """Execute the local runtime command remotely over SSH."""
    pipeline_paths = paths or PipelinePaths.default()

    remote_cmd = (
        f"cd {config.remote_workdir}/ml && "
        f"{remote_python} -m overfished_ml.local_pipeline.cli "
        f"--runtime local "
        f"--input-path {pipeline_paths.fishing_events_csv} "
        f"--bronze-output {pipeline_paths.bronze_output} "
        f"--silver-output {pipeline_paths.silver_output} "
        f"--gold-output {pipeline_paths.gold_output}"
    )
    completed = subprocess.run([*_ssh_base_command(config), remote_cmd], check=False)
    return completed.returncode
