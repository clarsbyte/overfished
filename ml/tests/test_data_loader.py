"""Smoke tests for Databricks golden dataset loader."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from overfished_ml.sequence.data_loader import DatabricksConnectionConfig, load_golden_dataset


def test_from_env_raises_on_missing_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABRICKS_HOST", " ")
    monkeypatch.setenv("DATABRICKS_TOKEN", " ")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", " ")

    with pytest.raises(ValueError, match="DATABRICKS_HOST"):
        DatabricksConnectionConfig.from_env()


def test_load_golden_dataset_raises_for_missing_required_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    dataframe = pd.DataFrame({"mmsi": [123], "lat": [1.0]})
    _install_fake_databricks_sql(monkeypatch, dataframe)

    config = DatabricksConnectionConfig(
        host="https://example.cloud.databricks.com",
        token="token",
        warehouse_id="warehouse",
    )
    with pytest.raises(ValueError, match="missing required columns"):
        load_golden_dataset(config, required_columns=["mmsi", "lon"])


def test_load_golden_dataset_returns_dataframe(monkeypatch: pytest.MonkeyPatch) -> None:
    dataframe = pd.DataFrame({"mmsi": [123], "lat": [1.0], "lon": [2.0]})
    _install_fake_databricks_sql(monkeypatch, dataframe)

    config = DatabricksConnectionConfig(
        host="https://example.cloud.databricks.com",
        token="token",
        warehouse_id="warehouse",
    )
    result = load_golden_dataset(config, required_columns=["mmsi", "lat", "lon"])
    assert list(result.columns) == ["mmsi", "lat", "lon"]
    assert len(result) == 1


def _install_fake_databricks_sql(monkeypatch: pytest.MonkeyPatch, dataframe: pd.DataFrame) -> None:
    class _FakeArrowResult:
        def __init__(self, df: pd.DataFrame) -> None:
            self._df = df

        def to_pandas(self) -> pd.DataFrame:
            return self._df

    class _FakeCursor:
        def execute(self, _query: str) -> None:
            return None

        def fetchall_arrow(self) -> _FakeArrowResult:
            return _FakeArrowResult(dataframe)

        def close(self) -> None:
            return None

    class _FakeConnection:
        def cursor(self) -> _FakeCursor:
            return _FakeCursor()

        def close(self) -> None:
            return None

    fake_sql = types.SimpleNamespace(connect=lambda **_: _FakeConnection())
    fake_databricks = types.SimpleNamespace(sql=fake_sql)
    monkeypatch.setitem(sys.modules, "databricks", fake_databricks)
