"""JSON cache for vessel image URL lookups."""

from __future__ import annotations

import json
from pathlib import Path


class VesselImageCache:
    """Persistent MMSI/IMO -> image URL mapping cache."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {str(k): str(v) for k, v in parsed.items() if isinstance(v, str) and v}

    def get(self, vessel_id: str) -> str | None:
        return self._data.get(str(vessel_id))

    def set(self, vessel_id: str, image_url: str) -> None:
        self._data[str(vessel_id)] = image_url

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
