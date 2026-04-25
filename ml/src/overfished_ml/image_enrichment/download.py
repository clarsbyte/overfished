"""Bulk-download resolved vessel image URLs to disk and downsize.

The companion :mod:`enricher` module produces a ``vessel_image_cache.json``
that maps ``mmsi -> https://...`` URLs. This module turns those URLs into
local JPG bytes the frontend can serve statically (via the
``frontend/public/data`` symlink), so clicking a vessel never requires a
live remote call.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image, UnidentifiedImageError


@dataclass(frozen=True)
class DownloadSummary:
    """Operational summary for a download run."""

    requested: int
    downloaded: int
    skipped_existing: int
    failed: int
    image_dir: str
    error_report_path: str


@dataclass
class _DownloadResult:
    mmsi: str
    status: str  # "downloaded" | "skipped" | "failed"
    error: str = ""
    extras: dict[str, str] = field(default_factory=dict)


_DEFAULT_USER_AGENT = (
    "OverfishedVesselDownloader/1.0 "
    "(local research; https://github.com/) python-requests"
)


def _open_image(content: bytes) -> Image.Image:
    return Image.open(BytesIO(content))


def _resize_to_max(image: Image.Image, max_side: int) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image
    scale = max_side / float(longest)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return image.resize(new_size, Image.LANCZOS)


def _save_jpeg(image: Image.Image, dest: Path, *, quality: int) -> None:
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="JPEG", quality=quality, optimize=True)


def _download_one(
    *,
    mmsi: str,
    url: str,
    dest: Path,
    timeout_seconds: float,
    max_retries: int,
    backoff_seconds: float,
    max_side: int,
    quality: int,
    user_agent: str,
) -> _DownloadResult:
    headers = {"User-Agent": user_agent}
    last_error: str = ""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout_seconds, stream=False)
            if response.status_code >= 400:
                last_error = f"HTTP {response.status_code}"
                if response.status_code in (404, 410):
                    break
            else:
                try:
                    image = _open_image(response.content)
                    image = _resize_to_max(image, max_side)
                    _save_jpeg(image, dest, quality=quality)
                    return _DownloadResult(mmsi=mmsi, status="downloaded")
                except (UnidentifiedImageError, OSError) as exc:
                    last_error = f"decode_failed: {exc}"
                    break
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < max_retries:
            time.sleep(backoff_seconds * attempt)
    return _DownloadResult(mmsi=mmsi, status="failed", error=last_error or "unknown_error")


def download_vessel_images(
    *,
    cache_path: Path,
    image_dir: Path,
    error_report_path: Path,
    mmsi_allowlist: Iterable[str] | None = None,
    refresh: bool = False,
    max_workers: int = 8,
    timeout_seconds: float = 10.0,
    max_retries: int = 3,
    backoff_seconds: float = 1.5,
    max_side: int = 1024,
    quality: int = 85,
    user_agent: str = _DEFAULT_USER_AGENT,
) -> DownloadSummary:
    """Download all images referenced by ``cache_path`` to ``image_dir``.

    Parameters mirror the existing enricher's ergonomics. Skips already-present
    files unless ``refresh=True``. Failures are written to
    ``error_report_path`` as JSON for later inspection.
    """
    if not cache_path.exists():
        raise FileNotFoundError(
            f"vessel image cache not found at {cache_path}. "
            "Run `enrich_dataset_with_ship_image_urls` first."
        )
    cache: dict[str, str] = {}
    parsed = json.loads(cache_path.read_text(encoding="utf-8"))
    if isinstance(parsed, dict):
        cache = {str(k).strip(): str(v).strip() for k, v in parsed.items() if str(v).strip()}

    if mmsi_allowlist is not None:
        allow = {str(m).strip() for m in mmsi_allowlist if str(m).strip()}
        cache = {k: v for k, v in cache.items() if k in allow}

    image_dir.mkdir(parents=True, exist_ok=True)

    results: list[_DownloadResult] = []
    pending: list[tuple[str, str, Path]] = []
    for mmsi, url in cache.items():
        if not url.startswith(("http://", "https://")):
            results.append(_DownloadResult(mmsi=mmsi, status="failed", error="not_http_url"))
            continue
        dest = image_dir / f"{mmsi}.jpg"
        if dest.exists() and not refresh:
            results.append(_DownloadResult(mmsi=mmsi, status="skipped"))
            continue
        pending.append((mmsi, url, dest))

    if pending:
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            futures = {
                pool.submit(
                    _download_one,
                    mmsi=mmsi,
                    url=url,
                    dest=dest,
                    timeout_seconds=timeout_seconds,
                    max_retries=max_retries,
                    backoff_seconds=backoff_seconds,
                    max_side=max_side,
                    quality=quality,
                    user_agent=user_agent,
                ): mmsi
                for (mmsi, url, dest) in pending
            }
            for future in as_completed(futures):
                results.append(future.result())

    downloaded = sum(1 for r in results if r.status == "downloaded")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = [r for r in results if r.status == "failed"]

    error_report_path.parent.mkdir(parents=True, exist_ok=True)
    error_report_path.write_text(
        json.dumps([asdict(r) for r in failed], indent=2, sort_keys=True), encoding="utf-8"
    )

    return DownloadSummary(
        requested=len(cache),
        downloaded=downloaded,
        skipped_existing=skipped,
        failed=len(failed),
        image_dir=str(image_dir),
        error_report_path=str(error_report_path),
    )
