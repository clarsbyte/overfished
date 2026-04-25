"""Configuration types for local medallion pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    # overfished/ml/src/overfished_ml/local_pipeline/config.py -> repo root
    return Path(__file__).resolve().parents[5]


@dataclass(frozen=True)
class SparkConfig:
    """Spark session tuning options for local execution."""

    app_name: str = "Overfishing Detection Pipeline"
    master: str = "local[*]"
    driver_memory: str = "4g"
    shuffle_partitions: int = 8
    adaptive_enabled: bool = True
    log_level: str = "WARN"


@dataclass(frozen=True)
class PipelinePaths:
    """Input and output locations for a medallion pipeline run."""

    fishing_events_csv: Path
    bronze_output: Path
    silver_output: Path
    gold_output: Path

    @classmethod
    def default(cls) -> "PipelinePaths":
        root = _repo_root()
        data_root = root / "data" / "local_pipeline"
        output_root = data_root / "output"
        return cls(
            fishing_events_csv=data_root / "sample_fishing_events.csv",
            bronze_output=output_root / "bronze_fishing_events",
            silver_output=output_root / "silver_fishing_events",
            gold_output=output_root / "gold_fishing_features",
        )


@dataclass(frozen=True)
class Gx10Config:
    """Remote execution settings for ASUS Ascent GX10 over SSH."""

    host: str
    user: str
    remote_workdir: str
    ssh_key_path: str | None = None
    port: int = 22
