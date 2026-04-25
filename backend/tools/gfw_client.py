"""Thin async HTTP client for the Global Fishing Watch v3 API.

Pure HTTP — no SDK dependency. We only call two endpoints:

  POST /v3/4wings/report   — paginated tabular report; for our use case
                              (HOURLY × VESSEL_ID grouping + custom polygon)
                              it returns vessel-presence rows we can sort
                              into per-vessel tracks.

  GET  /v3/4wings/last-report  — recovery endpoint; returns the result of
                                  the most recent report request from this
                                  token within 30 minutes. Used when /report
                                  hits the 100s server timeout (524).

Auth: Authorization: Bearer <token>. Token comes from the
``GFW_API_ACCESS_TOKEN`` environment variable, matching the official
gfw-api-python-client SDK convention.

Constraints we respect:
  * Max 1 concurrent report per token (else 429). Caller serializes.
  * 100 s server timeout (else 524). We retry once via /last-report.
  * Max date-range = 366 days. We use 24h windows; not relevant.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

GFW_BASE = "https://gateway.api.globalfishingwatch.org/v3"


class GFWError(RuntimeError):
    """Wraps a non-recoverable GFW API failure."""


class GFWClient:
    def __init__(self, token: str | None = None, timeout: float = 120.0):
        token = token or os.environ.get("GFW_API_ACCESS_TOKEN")
        if not token:
            raise GFWError(
                "GFW_API_ACCESS_TOKEN not set. Add it to backend/.env "
                "(see .env.example) or pass token=... explicitly."
            )
        self._client = httpx.AsyncClient(
            base_url=GFW_BASE,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout),
        )

    async def __aenter__(self) -> "GFWClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._client.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def vessel_presence_report(
        self,
        polygon: dict[str, Any],
        start_date: str,
        end_date: str,
        *,
        spatial_resolution: str = "LOW",
        temporal_resolution: str = "HOURLY",
        group_by: str = "VESSEL_ID",
    ) -> dict[str, Any]:
        """Run a 4Wings vessel-presence report over a custom polygon.

        Returns the parsed JSON response. Each entry in ``response["entries"]``
        is keyed by dataset version and holds a list of rows shaped roughly:

            {date, vessel_id, mmsi, shipName, flag, geartype, vessel_type,
             lat, lon, hours, entryTimestamp, exitTimestamp}

        ``date`` granularity matches ``temporal_resolution`` ("YYYY-MM-DD HH:00"
        for HOURLY).
        """
        params = {
            "spatial-resolution": spatial_resolution,
            "temporal-resolution": temporal_resolution,
            "group-by": group_by,
            "datasets[0]": "public-global-presence:latest",
            "date-range": f"{start_date},{end_date}",
            "format": "JSON",
        }
        body = {"geojson": polygon}

        try:
            r = await self._client.post("/4wings/report", params=params, json=body)
        except httpx.RequestError as e:
            raise GFWError(f"network error contacting GFW: {e}") from e

        # 524 = server-side report exceeded its 100s budget. Recover via the
        # last-report cache (30-min retention, returns the same result once
        # the worker finishes).
        if r.status_code == 524:
            await asyncio.sleep(2.0)
            r = await self._wait_for_last_report()

        if r.status_code == 429:
            # Concurrent-report cap. Caller is supposed to serialize, so this
            # generally shouldn't fire; surface it loudly if it does.
            raise GFWError(
                "GFW returned 429 (concurrent-report cap). Serialize prefetch calls "
                "or wait ~30s for the previous report to complete."
            )

        if r.status_code >= 400:
            raise GFWError(
                f"GFW report failed: {r.status_code} {r.reason_phrase} — {r.text[:300]}"
            )

        return r.json()

    async def _wait_for_last_report(self, max_polls: int = 30) -> httpx.Response:
        """Poll /4wings/last-report until it returns a finished result."""
        for _ in range(max_polls):
            r = await self._client.get("/4wings/last-report")
            if r.status_code == 404:
                raise GFWError("/last-report 404 — report not retained or never ran")
            try:
                payload = r.json()
            except ValueError:
                # Not JSON yet — possibly a zip/blob; treat as final.
                return r
            if isinstance(payload, dict) and payload.get("status") == "running":
                await asyncio.sleep(2.0)
                continue
            return r
        raise GFWError("/last-report still 'running' after 30 polls (~60s)")
