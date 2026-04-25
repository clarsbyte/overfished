"""Build per-vessel "cards" the frontend can render without live API calls.

A card collapses everything the right-side ``VesselDetailPanel`` needs into
a single static JSON file at ``data/local_pipeline/vessel_cards.json``:
identity (mmsi/name/flag/type), risk, a local image path (preferred) and the
remote source URL as a fallback, plus an optional one-line LLM summary when
``ANTHROPIC_API_KEY`` is configured.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv


@dataclass
class VesselCard:
    """Static, frontend-ready summary of one vessel."""

    mmsi: str
    name: str | None = None
    flag: str | None = None
    vessel_type: str | None = None
    risk: str | None = None
    is_high_risk: bool | None = None
    duration_hours: float | None = None
    image_path: str | None = None  # served by frontend at /data/...
    image_source_url: str | None = None
    summary: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"mmsi": self.mmsi}
        for key in (
            "name",
            "flag",
            "vessel_type",
            "risk",
            "is_high_risk",
            "duration_hours",
            "image_path",
            "image_source_url",
            "summary",
        ):
            value = getattr(self, key)
            if value is None:
                continue
            out[key] = value
        if self.extras:
            out.update(self.extras)
        return out


@dataclass(frozen=True)
class CardsSummary:
    """Operational summary for a card-building run."""

    rows_total: int
    unique_vessels: int
    cards_written: int
    with_local_image: int
    with_remote_image: int
    with_summary: int
    output_path: str


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _coerce_bool(value: Any) -> bool | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().lower()
    if text in ("1", "true", "t", "yes", "y"):
        return True
    if text in ("0", "false", "f", "no", "n"):
        return False
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _risk_for(row: dict[str, Any]) -> str | None:
    """Map the few ways the CSV expresses risk to a single bucket."""
    risk = _coerce_str(row.get("risk"))
    if risk:
        return risk
    high = _coerce_bool(row.get("is_high_risk"))
    if high is True:
        return "high_risk"
    potential = _coerce_str(row.get("potential_risk"))
    if potential and potential.lower() not in {"false", "no", "0"}:
        return "suspect"
    if high is False:
        return "safe"
    return None


def build_card_from_row(
    row: dict[str, Any],
    *,
    image_url: str | None = None,
    image_path: str | None = None,
) -> VesselCard:
    """Build a :class:`VesselCard` from a single CSV row + optional image refs."""
    mmsi = _coerce_str(row.get("mmsi")) or ""
    return VesselCard(
        mmsi=mmsi,
        name=_coerce_str(row.get("vessel_name")) or _coerce_str(row.get("name")),
        flag=_coerce_str(row.get("vessel_flag")) or _coerce_str(row.get("flag")),
        vessel_type=_coerce_str(row.get("vessel_type")) or _coerce_str(row.get("gear_type")),
        risk=_risk_for(row),
        is_high_risk=_coerce_bool(row.get("is_high_risk")),
        duration_hours=_coerce_float(row.get("event_duration_hours"))
        or _coerce_float(row.get("duration_hours")),
        image_path=image_path,
        image_source_url=image_url,
    )


def _select_first_row_per_mmsi(dataframe: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Pick the most informative row per MMSI (high_risk wins, then non-null name)."""
    if "mmsi" not in dataframe.columns:
        raise ValueError("Input dataset must include `mmsi` column")
    df = dataframe.copy()
    df["_mmsi_key"] = df["mmsi"].astype(str).str.strip()
    df = df[df["_mmsi_key"] != ""]
    if "is_high_risk" in df.columns:
        df["_risk_rank"] = df["is_high_risk"].apply(lambda v: 1 if _coerce_bool(v) else 0)
    else:
        df["_risk_rank"] = 0
    if "vessel_name" in df.columns:
        df["_name_rank"] = df["vessel_name"].apply(lambda v: 1 if _coerce_str(v) else 0)
    else:
        df["_name_rank"] = 0
    df = df.sort_values(["_risk_rank", "_name_rank"], ascending=False, kind="mergesort")
    out: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        key = row["_mmsi_key"]
        if key in out:
            continue
        out[key] = {k: v for k, v in row.items() if not k.startswith("_")}
    return out


def _public_image_path(image_dir: Path, public_prefix: str, mmsi: str) -> str | None:
    """Return frontend-relative path if a downloaded JPG exists for this MMSI."""
    candidate = image_dir / f"{mmsi}.jpg"
    if candidate.exists():
        return f"{public_prefix.rstrip('/')}/{mmsi}.jpg"
    return None


def _summarize_with_anthropic(
    cards: list[VesselCard],
    *,
    model: str,
) -> int:
    """Fill ``card.summary`` for cards missing a summary. Returns count filled."""
    try:
        from anthropic import Anthropic
    except ImportError:
        return 0
    client = Anthropic()
    filled = 0
    for card in cards:
        if card.summary:
            continue
        bits: list[str] = []
        if card.vessel_type:
            bits.append(f"type={card.vessel_type}")
        if card.flag:
            bits.append(f"flag={card.flag}")
        if card.duration_hours is not None:
            bits.append(f"duration_hours={card.duration_hours:.1f}")
        if card.risk:
            bits.append(f"risk={card.risk}")
        if not bits:
            continue
        prompt = (
            "In one sentence (<= 24 words) describe what this vessel was doing in plain "
            "language for a port-officer dashboard. Be factual and avoid speculation. "
            f"Vessel name: {card.name or 'unknown'} (MMSI {card.mmsi}). "
            f"Signals: {', '.join(bits)}."
        )
        try:
            response = client.messages.create(
                model=model,
                max_tokens=80,
                messages=[{"role": "user", "content": prompt}],
            )
            text_parts = []
            for block in response.content:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
            summary = " ".join(p.strip() for p in text_parts if p.strip())
            if summary:
                card.summary = summary
                filled += 1
        except Exception:
            continue
    return filled


def build_vessel_cards(
    *,
    input_csv: Path,
    cache_path: Path,
    image_dir: Path,
    output_path: Path,
    public_image_prefix: str = "/data/vessel_images",
    with_summaries: bool = False,
    summary_model: str = "claude-haiku-4-5-20251001",
) -> CardsSummary:
    """Build ``vessel_cards.json`` from the enriched CSV + image cache + JPGs."""
    load_dotenv()
    dataframe = pd.read_csv(input_csv)
    rows_total = len(dataframe)
    by_mmsi = _select_first_row_per_mmsi(dataframe)

    cache: dict[str, str] = {}
    if cache_path.exists():
        try:
            parsed = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                cache = {
                    str(k).strip(): str(v).strip()
                    for k, v in parsed.items()
                    if str(v).strip()
                }
        except json.JSONDecodeError:
            cache = {}

    cards: list[VesselCard] = []
    for mmsi in sorted({*by_mmsi.keys(), *cache.keys()}):
        row = by_mmsi.get(mmsi, {"mmsi": mmsi})
        image_path = _public_image_path(image_dir, public_image_prefix, mmsi)
        image_url = cache.get(mmsi)
        cards.append(
            build_card_from_row(
                row,
                image_url=image_url or None,
                image_path=image_path,
            )
        )

    if with_summaries and os.getenv("ANTHROPIC_API_KEY"):
        _summarize_with_anthropic(cards, model=summary_model)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {card.mmsi: card.to_dict() for card in cards}
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    return CardsSummary(
        rows_total=rows_total,
        unique_vessels=len(by_mmsi),
        cards_written=len(cards),
        with_local_image=sum(1 for c in cards if c.image_path),
        with_remote_image=sum(1 for c in cards if c.image_source_url),
        with_summary=sum(1 for c in cards if c.summary),
        output_path=str(output_path),
    )
