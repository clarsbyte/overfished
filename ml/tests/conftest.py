"""Pytest hooks: stub optional heavy deps so ``import overfished_ml`` works without Spark."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


def _ensure_pyspark_stub() -> None:
    try:
        import pyspark  # noqa: F401
    except ModuleNotFoundError:
        root = MagicMock(name="pyspark")
        sys.modules.setdefault("pyspark", root)
        sql = MagicMock(name="pyspark.sql")
        sys.modules.setdefault("pyspark.sql", sql)
        sql.SparkSession = MagicMock(name="SparkSession")


_ensure_pyspark_stub()
