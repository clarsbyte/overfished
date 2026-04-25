"""Spark session helpers for local pipeline runs."""

from __future__ import annotations

import re
import subprocess

from pyspark.sql import SparkSession

from .config import SparkConfig


def _java_major_version() -> int | None:
    try:
        completed = subprocess.run(
            ["java", "-version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    text = (completed.stderr or completed.stdout).splitlines()
    if not text:
        return None
    match = re.search(r'version "(\d+)(?:\.(\d+))?', text[0])
    if not match:
        return None
    major = int(match.group(1))
    if major == 1 and match.group(2):
        return int(match.group(2))
    return major


def assert_java_compatibility(min_major: int = 17) -> None:
    """Fail fast with clear guidance when Java is missing/incompatible."""
    java_major = _java_major_version()
    if java_major is None:
        raise RuntimeError("Java runtime not found. Install JDK 17+ to run the local Spark pipeline.")
    if java_major < min_major:
        raise RuntimeError(
            f"Detected Java {java_major}. Install JDK {min_major}+ for this pipeline configuration."
        )


def create_spark_session(config: SparkConfig) -> SparkSession:
    """Create and return a Spark session using local defaults."""
    assert_java_compatibility()
    builder = (
        SparkSession.builder.appName(config.app_name)
        .master(config.master)
        .config("spark.driver.memory", config.driver_memory)
        .config("spark.executor.memory", config.executor_memory)
        .config("spark.sql.shuffle.partitions", str(config.shuffle_partitions))
        .config("spark.sql.adaptive.enabled", str(config.adaptive_enabled).lower())
    )
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel(config.log_level)
    return spark
