"""Unit tests for local_pipeline configuration (no Spark)."""

from __future__ import annotations

from overfished_ml.local_pipeline.config import Gx10Config, PipelinePaths, SparkConfig, _repo_root


def test_repo_root_contains_ml() -> None:
    root = _repo_root()
    assert (root / "ml" / "pyproject.toml").is_file()


def test_spark_config_defaults() -> None:
    cfg = SparkConfig()
    assert cfg.master == "local[*]"
    assert cfg.shuffle_partitions == 8
    assert cfg.adaptive_enabled is True


def test_spark_config_from_env_shuffle(monkeypatch) -> None:
    monkeypatch.setenv("SPARK_SHUFFLE_PARTITIONS", "24")
    cfg = SparkConfig.from_env()
    assert cfg.shuffle_partitions == 24


def test_gx10_config_frozen() -> None:
    cfg = Gx10Config(host="h", user="u", remote_workdir="/w")
    assert cfg.port == 22


def test_pipeline_paths_default_paths_exist_under_data_dir() -> None:
    paths = PipelinePaths.default()
    assert paths.fishing_events_csv.name.endswith(".csv")
    assert "local_pipeline" in str(paths.fishing_events_csv)
    assert paths.bronze_output.parent == paths.silver_output.parent
