"""Wikimedia Commons image search fallback (no API key; rate-limit friendly)."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib import parse, request

# https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy
_COMMONS_USER_AGENT = (
    "OverfishedVesselEnrichment/1.0 (local research; https://github.com/) "
    "python-urllib"
)
_COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def commons_thumbnail_url_for_vessel(
    vessel_name: str,
    *,
    mmsi: str | None = None,
    timeout_seconds: float = 12.0,
) -> str | None:
    """
    Return a thumbnail or full image URL from Wikimedia Commons search.

    Results are best-effort and may not depict the exact vessel; prefer MarineTraffic
    or manual overrides when accuracy matters.
    """
    name = (vessel_name or "").strip()
    if not name and not mmsi:
        return None
    query_parts = [name] if name else []
    query_parts.append("ship")
    if mmsi:
        query_parts.append(str(mmsi))
    query = " ".join(part for part in query_parts if part)
    if not query.strip():
        return None

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": "3",
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": "800",
    }
    url = f"{_COMMONS_API}?{parse.urlencode(params)}"
    req = request.Request(url, headers={"User-Agent": _COMMONS_USER_AGENT})
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            payload: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None

    pages = (payload.get("query") or {}).get("pages") or {}
    for _page_id, page in pages.items():
        if not isinstance(page, dict):
            continue
        infos = page.get("imageinfo")
        if not isinstance(infos, list) or not infos:
            continue
        first = infos[0]
        if not isinstance(first, dict):
            continue
        thumb = first.get("thumburl")
        if isinstance(thumb, str) and thumb.startswith("http"):
            return thumb
        full_url = first.get("url")
        if isinstance(full_url, str) and full_url.startswith("http"):
            return full_url
    return None


def sleep_between_commons_requests(seconds: float) -> None:
    """Polite delay between Commons requests."""
    if seconds > 0:
        time.sleep(seconds)
