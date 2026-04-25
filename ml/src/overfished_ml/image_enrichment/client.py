"""MarineTraffic vessel photo lookup client with retries."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


@dataclass(frozen=True)
class PhotoLookupResult:
    """Normalized vessel photo lookup result."""

    vessel_id: str
    image_url: str | None
    status: str
    error: str | None = None


class MarineTrafficClient:
    """Lightweight HTTP client for MarineTraffic photo endpoint."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://services.marinetraffic.com/api",
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.5,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        if not self.api_key:
            raise ValueError("MarineTraffic API key cannot be empty")

    def fetch_vessel_photo_url(self, vessel_id: str) -> PhotoLookupResult:
        """Fetch a vessel photo URL by MMSI/IMO-like vessel identifier."""
        clean_id = str(vessel_id).strip()
        if not clean_id:
            return PhotoLookupResult(vessel_id=clean_id, image_url=None, status="invalid_id")

        endpoint = f"{self.base_url}/exportvesselphoto/{self.api_key}"
        query = parse.urlencode({"vessel_id": clean_id, "protocol": "jsono"})
        url = f"{endpoint}?{query}"

        for attempt in range(1, self.max_retries + 1):
            try:
                req = request.Request(url, method="GET")
                with request.urlopen(req, timeout=self.timeout_seconds) as response:
                    body = response.read()
                parsed = self._parse_image_url(body)
                if parsed:
                    return PhotoLookupResult(vessel_id=clean_id, image_url=parsed, status="resolved")
                return PhotoLookupResult(vessel_id=clean_id, image_url=None, status="not_found")
            except error.HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    time.sleep(self.retry_backoff_seconds * attempt)
                    continue
                return PhotoLookupResult(
                    vessel_id=clean_id,
                    image_url=None,
                    status="http_error",
                    error=f"HTTP {exc.code}",
                )
            except error.URLError as exc:
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_seconds * attempt)
                    continue
                return PhotoLookupResult(
                    vessel_id=clean_id,
                    image_url=None,
                    status="network_error",
                    error=str(exc.reason),
                )
            except Exception as exc:  # pragma: no cover - safety net
                return PhotoLookupResult(
                    vessel_id=clean_id,
                    image_url=None,
                    status="parse_error",
                    error=str(exc),
                )
        return PhotoLookupResult(vessel_id=clean_id, image_url=None, status="retry_exhausted")

    def _parse_image_url(self, payload: bytes) -> str | None:
        text = payload.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        try:
            decoded: Any = json.loads(text)
        except json.JSONDecodeError:
            return text if text.startswith(("http://", "https://")) else None
        return self._extract_url(decoded)

    def _extract_url(self, value: Any) -> str | None:
        if isinstance(value, str):
            return value if value.startswith(("http://", "https://")) else None
        if isinstance(value, list):
            for item in value:
                found = self._extract_url(item)
                if found:
                    return found
            return None
        if isinstance(value, dict):
            for key in ("PHOTO_URL", "photo_url", "url", "URL", "photo", "image", "image_url"):
                candidate = value.get(key)
                found = self._extract_url(candidate)
                if found:
                    return found
            for candidate in value.values():
                found = self._extract_url(candidate)
                if found:
                    return found
            return None
        return None
