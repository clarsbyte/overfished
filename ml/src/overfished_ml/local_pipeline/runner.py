"""Execution runner for the local medallion pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from .config import PipelinePaths, SparkConfig
from .spark import create_spark_session
from .transformations import bronze_fishing_events, gold_fishing_features, silver_fishing_events


@dataclass(frozen=True)
class PipelineRunResult:
    """Outputs for a successful local pipeline run."""

    bronze_count: int
    silver_count: int
    gold_count: int
    gold_csv_path: str


def run_local_pipeline(
    *,
    paths: PipelinePaths | None = None,
    spark_config: SparkConfig | None = None,
) -> PipelineRunResult:
    """Run bronze -> silver -> gold locally and return row-count summary."""
    pipeline_paths = paths or PipelinePaths.default()
    cfg = spark_config or SparkConfig()

    pipeline_paths.bronze_output.parent.mkdir(parents=True, exist_ok=True)
    spark = create_spark_session(cfg)
    try:
        bronze_df = bronze_fishing_events(
            spark,
            input_path=str(pipeline_paths.fishing_events_csv),
            output_path=str(pipeline_paths.bronze_output),
        )
        silver_df = silver_fishing_events(
            spark,
            input_path=str(pipeline_paths.bronze_output),
            output_path=str(pipeline_paths.silver_output),
        )
        gold_df = gold_fishing_features(
            spark,
            input_path=str(pipeline_paths.silver_output),
            output_path=str(pipeline_paths.gold_output),
        )
        return PipelineRunResult(
            bronze_count=bronze_df.count(),
            silver_count=silver_df.count(),
            gold_count=gold_df.count(),
            gold_csv_path=f"{pipeline_paths.gold_output}_csv",
        )
    finally:
        spark.stop()
