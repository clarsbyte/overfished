"""Live client for the ProtectedSeas Global Maximum Level of Fishing Protection layer.

Backed by the public ArcGIS FeatureServer at:
  https://services9.arcgis.com/lm7wE8a9YA9rKfzy/arcgis/rest/services/
  Global_Maximum_Level_of_Fishing_Protection/FeatureServer/0

The layer carries one numeric indicator per polygon:
  LFP (1–5)     — Level of Fishing Protection (1 = least restrictive, 5 = no-take)
  AREA_SQKM     — area of the polygon
  LAST_UPDAT    — date the polygon was last updated upstream

This is the geospatial-overlay component of the regional-law pipeline. It does
not provide MPA names or governing legislation — that lives in the curated
FISHLEX/PORTLEX/FAOLEX cache.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

LFP_QUERY_URL = (
    "https://services9.arcgis.com/lm7wE8a9YA9rKfzy/arcgis/rest/services/"
    "Global_Maximum_Level_of_Fishing_Protection/FeatureServer/0/query"
)

LFP_INTERPRETATION: dict[int, str] = {
    1: "Least restrictive — limited or no fishing regulations beyond baseline.",
    2: "Lightly regulated — some gear, species, or seasonal restrictions.",
    3: "Moderately regulated — multiple overlapping restrictions.",
    4: "Highly regulated — significant fishing restrictions.",
    5: "No-take — all extractive fishing prohibited.",
}


def query_lfp_at_point(
    latitude: float,
    longitude: float,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Return the maximum LFP score at the given coordinate, with provenance.

    Response shape:
      {
        "lfp": int | None,
        "lfp_interpretation": str | None,
        "area_sqkm": float | None,
        "feature_last_update": "YYYY-MM-DD" | None,
        "matched": bool,
        "provenance": {
            "database": "ProtectedSeas Navigator",
            "layer": "Global_Maximum_Level_of_Fishing_Protection / 0",
            "source_url": <query URL>,
            "checked_at": <ISO 8601 UTC>,
            "confidence": "live"
        }
      }
    """
    params = {
        "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "LFP,AREA_SQKM,LAST_UPDAT,OBJECTID",
        "returnGeometry": "false",
        "f": "json",
    }
    resp = requests.get(LFP_QUERY_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    features = payload.get("features", []) or []

    checked_at = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {
        "lfp": None,
        "lfp_interpretation": None,
        "area_sqkm": None,
        "feature_last_update": None,
        "matched": bool(features),
        "provenance": {
            "database": "ProtectedSeas Navigator",
            "layer": "Global_Maximum_Level_of_Fishing_Protection / 0",
            "source_url": LFP_QUERY_URL,
            "checked_at": checked_at,
            "confidence": "live",
        },
    }
    if not features:
        return result

    best = max(
        features,
        key=lambda f: (f.get("attributes", {}) or {}).get("LFP") or 0,
    )
    attrs = best.get("attributes", {}) or {}
    lfp_raw = attrs.get("LFP")
    last_update_ms = attrs.get("LAST_UPDAT")
    last_update_iso: str | None = None
    if isinstance(last_update_ms, (int, float)):
        last_update_iso = (
            datetime.fromtimestamp(last_update_ms / 1000, timezone.utc).date().isoformat()
        )

    lfp_int = int(lfp_raw) if isinstance(lfp_raw, (int, float)) else None
    result["lfp"] = lfp_int
    result["lfp_interpretation"] = LFP_INTERPRETATION.get(lfp_int) if lfp_int else None
    result["area_sqkm"] = attrs.get("AREA_SQKM")
    result["feature_last_update"] = last_update_iso
    return result
