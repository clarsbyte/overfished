"""Configuration types for local medallion pipeline execution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    # overfished/ml/src/overfished_ml/local_pipeline/config.py -> repo root
    return Path(__file__).resolve().parents[4]


def _env_bool(name: str, default: bool) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class SparkConfig:
    """Spark session tuning options for local execution."""

    app_name: str = "Overfishing Detection Pipeline"
    master: str = "local[*]"
    driver_memory: str = "4g"
    executor_memory: str = "1g"
    shuffle_partitions: int = 8
    adaptive_enabled: bool = True
    log_level: str = "WARN"

    @classmethod
    def from_env(cls) -> "SparkConfig":
        """Override defaults with env (GX10 / large-CSV runs). See local_pipeline README."""
        shuf = os.getenv("SPARK_SHUFFLE_PARTITIONS") or os.getenv("OVERFISH_SPARK_SHUFFLE_PARTITIONS", "8")
        shuf_n = int(shuf) if str(shuf).isdigit() else 8
        return cls(
            app_name=os.getenv("SPARK_APP_NAME", "Overfishing Detection Pipeline"),
            master=os.getenv("SPARK_MASTER", "local[*]"),
            driver_memory=os.getenv("SPARK_DRIVER_MEMORY", "4g"),
            executor_memory=os.getenv("SPARK_EXECUTOR_MEMORY", "1g"),
            shuffle_partitions=shuf_n,
            adaptive_enabled=_env_bool("SPARK_ADAPTIVE", True),
            log_level=os.getenv("SPARK_LOG_LEVEL", "WARN"),
        )


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
        # Bulk / warehouse extract: GFW- or Databricks-style CSV (same schema as sample)
        raw_bulk = data_root / "raw" / "bulk_fishing_events.csv"
        env_in = (os.getenv("FISHING_EVENTS_CSV", "") or "").strip()
        if env_in:
            p = Path(env_in)
            fishing = (root / env_in).resolve() if not p.is_absolute() else p.resolve()
        elif raw_bulk.is_file():
            fishing = raw_bulk
        else:
            fishing = data_root / "sample_fishing_events.csv"
        return cls(
            fishing_events_csv=fishing,
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
