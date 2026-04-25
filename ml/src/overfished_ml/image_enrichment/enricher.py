"""CSV enrichment workflow for adding vessel image URLs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from .cache import VesselImageCache
from .client import MarineTrafficClient
from .commons_fallback import commons_thumbnail_url_for_vessel, sleep_between_commons_requests
from .overrides import load_ship_image_overrides


@dataclass(frozen=True)
class EnrichmentSummary:
    """Operational summary for image enrichment runs."""

    rows_total: int
    unique_vessels: int
    resolved_count: int
    override_hits: int
    cache_hits: int
    marine_traffic_hits: int
    commons_hits: int
    misses: int
    api_errors: int
    output_path: str
    miss_report_path: str


def _default_use_commons_fallback(api_key: str | None) -> bool:
    """When no MarineTraffic key is set, enable Commons by default (free tier)."""
    if api_key and api_key.strip():
        return os.getenv("VESSEL_IMAGE_COMMONS_FALLBACK", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
    return os.getenv("VESSEL_IMAGE_COMMONS_FALLBACK", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def enrich_dataset_with_ship_image_urls(
    *,
    input_csv: Path,
    output_csv: Path,
    cache_path: Path,
    miss_report_path: Path,
    api_key: str | None,
    base_url: str,
    timeout_seconds: float,
    refresh: bool = False,
    dry_run: bool = False,
    offline: bool = False,
    override_csv_path: Path | None = None,
    use_commons_fallback: bool | None = None,
    commons_delay_seconds: float = 0.35,
) -> EnrichmentSummary:
    """Enrich dataset with `ship_image_url` by resolving unique MMSI values."""
    load_dotenv()
    offline = offline or os.getenv("VESSEL_IMAGE_OFFLINE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    dataframe = pd.read_csv(input_csv)
    if "mmsi" not in dataframe.columns:
        raise ValueError("Input dataset must include `mmsi` column")
    if "ship_image_url" not in dataframe.columns:
        dataframe["ship_image_url"] = ""

    commons_enabled = (
        False
        if offline
        else (
            use_commons_fallback
            if use_commons_fallback is not None
            else _default_use_commons_fallback(api_key)
        )
    )

    if override_csv_path is None:
        override_csv_path = input_csv.resolve().parent / "local_pipeline" / "ship_image_overrides.csv"
    overrides = load_ship_image_overrides(override_csv_path)

    cache = VesselImageCache(cache_path)
    misses: list[dict[str, str]] = []
    override_hits = 0
    cache_hits = 0
    marine_traffic_hits = 0
    commons_hit_count = 0
    api_errors = 0

    vessel_ids = sorted({str(v).strip() for v in dataframe["mmsi"].dropna().unique() if str(v).strip()})

    mmsi_to_name: dict[str, str] = {}
    if "vessel_name" in dataframe.columns:
        for mmsi, group in dataframe.groupby(dataframe["mmsi"].astype(str)):
            names = group["vessel_name"].dropna().astype(str).str.strip()
            names = names[names != ""]
            if not names.empty:
                mmsi_to_name[str(mmsi).strip()] = str(names.iloc[0])

    client: MarineTrafficClient | None = None
    if not dry_run and not offline and api_key and api_key.strip():
        client = MarineTrafficClient(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)

    if not dry_run and not offline and client is None and not commons_enabled and not overrides:
        raise ValueError(
            "No image sources configured: set MARINETRAFFIC_API_KEY, add "
            "data/local_pipeline/ship_image_overrides.csv, pass --use-commons-fallback, "
            "or use --dry-run."
        )

    lookup_by_vessel: dict[str, str] = {}

    if not refresh:
        for mmsi_str, group in dataframe.groupby(dataframe["mmsi"].astype(str)):
            urls = group["ship_image_url"].dropna().astype(str).str.strip()
            for val in urls:
                if val.startswith(("http://", "https://")):
                    lookup_by_vessel[str(mmsi_str).strip()] = val
                    break

    for mmsi in vessel_ids:
        if mmsi in overrides:
            lookup_by_vessel[mmsi] = overrides[mmsi]
            cache.set(mmsi, overrides[mmsi])
            override_hits += 1
            continue

        if not refresh and mmsi in lookup_by_vessel:
            continue

        if not refresh:
            cached = cache.get(mmsi)
            if cached:
                lookup_by_vessel[mmsi] = cached
                cache_hits += 1
                continue

        if dry_run:
            misses.append({"mmsi": mmsi, "status": "dry_run", "error": ""})
            continue

        resolved_url: str | None = None
        miss_status = "offline_unresolved" if offline else "not_found"
        miss_error = ""

        if client is not None:
            result = client.fetch_vessel_photo_url(mmsi)
            if result.image_url:
                resolved_url = result.image_url
                marine_traffic_hits += 1
            elif result.status not in {"not_found", "invalid_id"}:
                api_errors += 1
                miss_status = result.status
                miss_error = result.error or ""

        if resolved_url is None and commons_enabled:
            vessel_name = mmsi_to_name.get(mmsi, "")
            url = commons_thumbnail_url_for_vessel(vessel_name, mmsi=mmsi, timeout_seconds=timeout_seconds)
            sleep_between_commons_requests(commons_delay_seconds)
            if url:
                resolved_url = url
                commons_hit_count += 1
            elif not client:
                miss_status = "commons_miss" if vessel_name else "commons_no_vessel_name"
            elif miss_status == "not_found":
                miss_status = "commons_miss" if vessel_name else "commons_no_vessel_name"

        if resolved_url:
            lookup_by_vessel[mmsi] = resolved_url
            cache.set(mmsi, resolved_url)
        else:
            misses.append({"mmsi": mmsi, "status": miss_status, "error": miss_error})

    merged = dataframe["mmsi"].astype(str).map(lookup_by_vessel)
    dataframe["ship_image_url"] = merged.fillna(dataframe["ship_image_url"].fillna("").astype(str))

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(output_csv, index=False)

    cache.save()
    miss_report_path.parent.mkdir(parents=True, exist_ok=True)
    miss_report_path.write_text(json.dumps(misses, indent=2), encoding="utf-8")

    resolved_count = sum(1 for m in vessel_ids if lookup_by_vessel.get(m, "").startswith("http"))

    return EnrichmentSummary(
        rows_total=len(dataframe),
        unique_vessels=len(vessel_ids),
        resolved_count=resolved_count,
        override_hits=override_hits,
        cache_hits=cache_hits,
        marine_traffic_hits=marine_traffic_hits,
        commons_hits=commons_hit_count,
        misses=len(misses),
        api_errors=api_errors,
        output_path=str(output_csv),
        miss_report_path=str(miss_report_path),
    )


def api_key_from_env() -> str | None:
    """Read MarineTraffic API key from environment or .env."""
    load_dotenv()
    key = os.getenv("MARINETRAFFIC_API_KEY")
    if key is None:
        return None
    return key.strip() or None
