"""Load manual MMSI -> image URL overrides from CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_ship_image_overrides(path: Path) -> dict[str, str]:
    """Return MMSI -> URL map from a CSV with columns `mmsi` and `ship_image_url`."""
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    if "mmsi" not in frame.columns:
        return {}
    url_column = None
    for candidate in ("ship_image_url", "image_url", "url"):
        if candidate in frame.columns:
            url_column = candidate
            break
    if url_column is None:
        return {}
    result: dict[str, str] = {}
    for _, row in frame.iterrows():
        mmsi = str(row["mmsi"]).strip()
        raw = row.get(url_column)
        if mmsi == "" or mmsi.lower() == "nan" or pd.isna(raw):
            continue
        url = str(raw).strip()
        if url.startswith(("http://", "https://")):
            result[mmsi] = url
    return result
