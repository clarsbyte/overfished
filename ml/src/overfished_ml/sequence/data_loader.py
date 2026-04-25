"""Databricks SQL loader for the golden vessel dataset."""

from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd
from dotenv import load_dotenv

DEFAULT_GOLD_TABLE = "workspace.default.gold_vessel_detections_enriched"


@dataclass(frozen=True)
class DatabricksConnectionConfig:
    """Connection settings used to query Databricks SQL Warehouse."""

    host: str
    token: str
    warehouse_id: str
    table_name: str = DEFAULT_GOLD_TABLE

    @property
    def server_hostname(self) -> str:
        """Host with protocol removed for Databricks SQL connector."""
        normalized = self.host.strip()
        normalized = normalized.removeprefix("https://")
        normalized = normalized.removeprefix("http://")
        return normalized.strip("/")

    @property
    def http_path(self) -> str:
        """HTTP path for Databricks SQL warehouse endpoint."""
        return f"/sql/1.0/warehouses/{self.warehouse_id}"

    @classmethod
    def from_env(cls) -> "DatabricksConnectionConfig":
        """Build config from environment variables."""
        load_dotenv()
        host = _required_env("DATABRICKS_HOST")
        token = _required_env("DATABRICKS_TOKEN")
        warehouse_id = _required_env("DATABRICKS_WAREHOUSE_ID")
        table_name = os.getenv("DATABRICKS_GOLD_TABLE", DEFAULT_GOLD_TABLE).strip()
        if not table_name:
            raise ValueError("DATABRICKS_GOLD_TABLE cannot be empty")
        return cls(host=host, token=token, warehouse_id=warehouse_id, table_name=table_name)


def load_golden_dataset(
    config: DatabricksConnectionConfig,
    required_columns: list[str],
) -> pd.DataFrame:
    """Load and validate the Databricks golden dataset."""
    if not required_columns:
        raise ValueError("required_columns must contain at least one column name")

    try:
        from databricks import sql
    except ImportError as exc:  # pragma: no cover - dependency issue
        raise ImportError(
            "databricks-sql-connector is required. Install ML dependencies first."
        ) from exc

    query = f"SELECT * FROM {config.table_name}"
    connection = None
    cursor = None
    try:
        connection = sql.connect(
            server_hostname=config.server_hostname,
            http_path=config.http_path,
            access_token=config.token,
        )
        cursor = connection.cursor()
        cursor.execute(query)
        dataframe = cursor.fetchall_arrow().to_pandas()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    _validate_required_columns(dataframe, required_columns)
    return dataframe


def _required_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {key}")
    return value.strip()


def _validate_required_columns(dataframe: pd.DataFrame, required_columns: list[str]) -> None:
    missing = sorted(col for col in required_columns if col not in dataframe.columns)
    if missing:
        raise ValueError(f"Golden dataset is missing required columns: {missing}")
