"""Bronze/Silver/Gold transformations for fishing events."""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


def bronze_fishing_events(spark: SparkSession, input_path: str, output_path: str) -> DataFrame:
    """Load raw fishing events as bronze layer without data mutation."""
    df = (
        spark.read.format("csv")
        .option("header", "true")
        .option("inferSchema", "true")
        .load(input_path)
    )
    df.write.mode("overwrite").parquet(output_path)
    return df


def silver_fishing_events(spark: SparkSession, input_path: str, output_path: str) -> DataFrame:
    """Clean and standardize bronze records into silver schema."""
    bronze_df = spark.read.parquet(input_path)

    df = (
        bronze_df.filter(F.col("`vessel.ssvid`").isNotNull())
        .filter((F.col("`position.lat`") >= -90) & (F.col("`position.lat`") <= 90))
        .filter((F.col("`position.lon`") >= -180) & (F.col("`position.lon`") <= 180))
        .filter(F.col("start").isNotNull() & F.col("end").isNotNull())
        .filter(F.col("start") <= F.col("end"))
        .dropDuplicates(["id"])
        .withColumnRenamed("id", "event_id")
        .withColumnRenamed("type", "event_type")
        .withColumnRenamed("start", "start_time")
        .withColumnRenamed("end", "end_time")
        .withColumnRenamed("vessel.id", "vessel_id")
        .withColumnRenamed("vessel.name", "vessel_name")
        .withColumnRenamed("vessel.ssvid", "vessel_mmsi")
        .withColumnRenamed("vessel.flag", "vessel_flag")
        .withColumnRenamed("vessel.type", "vessel_type")
        .withColumnRenamed("vessel.public_authorizations", "vessel_authorizations")
        .withColumnRenamed("fishing.vessel_public_authorization_status", "authorization_status")
        .withColumnRenamed("position.lat", "latitude")
        .withColumnRenamed("position.lon", "longitude")
        .withColumnRenamed("fishing.total_distance_km", "total_distance_km")
        .withColumnRenamed("fishing.average_speed_knots", "average_speed_knots")
        .withColumnRenamed("fishing.potential_risk", "potential_risk")
        .withColumnRenamed("distances.start_distance_from_shore_km", "distance_from_shore_km")
        .withColumnRenamed("distances.start_distance_from_port_km", "distance_from_port_km")
        .withColumnRenamed("regions.eez", "eez_regions")
        .withColumnRenamed("regions.rfmo", "rfmo_regions")
        .withColumnRenamed("regions.fao", "fao_regions")
        .withColumnRenamed("regions.mpa", "mpa_regions")
        .withColumn("processed_at", F.current_timestamp())
        .withColumn(
            "event_duration_hours",
            F.round((F.unix_timestamp("end_time") - F.unix_timestamp("start_time")) / 3600, 2),
        )
        .withColumn(
            "is_high_risk",
            F.when((F.col("potential_risk") == True) & (F.col("distance_from_shore_km") > 200), True)
            .otherwise(False),
        )
    )
    df.write.mode("overwrite").parquet(output_path)
    return df


def gold_fishing_features(spark: SparkSession, input_path: str, output_path: str) -> DataFrame:
    """Aggregate silver records into vessel-level gold features."""
    silver_df = spark.read.parquet(input_path)
    df = (
        silver_df.groupBy("vessel_mmsi", "vessel_name", "vessel_flag", "vessel_type")
        .agg(
            F.count("event_id").alias("total_events"),
            F.countDistinct("event_id").alias("unique_events"),
            F.sum("total_distance_km").alias("total_distance_km"),
            F.avg("average_speed_knots").alias("avg_speed_knots"),
            F.avg("event_duration_hours").alias("avg_event_duration_hours"),
            F.max("event_duration_hours").alias("max_event_duration_hours"),
            F.min("start_time").alias("first_seen"),
            F.max("end_time").alias("last_seen"),
            F.datediff(F.max("end_time"), F.min("start_time")).alias("days_active"),
            F.countDistinct("latitude", "longitude").alias("unique_locations"),
            F.avg("distance_from_shore_km").alias("avg_distance_from_shore_km"),
            F.min("distance_from_shore_km").alias("min_distance_from_shore_km"),
            F.max("distance_from_shore_km").alias("max_distance_from_shore_km"),
            F.avg("distance_from_port_km").alias("avg_distance_from_port_km"),
            F.sum(F.when(F.col("potential_risk") == True, 1).otherwise(0)).alias(
                "potential_risk_events"
            ),
            F.sum(F.when(F.col("is_high_risk") == True, 1).otherwise(0)).alias("high_risk_events"),
            F.max(F.col("is_high_risk").cast("int")).alias("has_high_risk_flag"),
            F.collect_set("eez_regions").alias("eez_regions_visited"),
            F.collect_set("rfmo_regions").alias("rfmo_regions_visited"),
            F.collect_set("fao_regions").alias("fao_regions_visited"),
            F.last("latitude").alias("last_known_lat"),
            F.last("longitude").alias("last_known_lon"),
            F.last("start_time").alias("last_event_time"),
        )
        .filter(F.col("total_events") > 0)
    )
    df.write.mode("overwrite").parquet(output_path)
    df.coalesce(1).write.mode("overwrite").option("header", "true").csv(f"{output_path}_csv")
    return df
