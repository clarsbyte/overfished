"""Smoke test for render_evidence_pdf — single combined PDF + risk gate.

No LLM, no API keys. Three scenarios:
  1. HIGH verdict       -> renders combined_legal_package.pdf, hash verifies.
  2. LOW verdict        -> tool refuses, no PDF written.
  3. INSUFFICIENT_DATA  -> tool refuses, no PDF written.

Usage:
    python test_render_pdf.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time

from documents.render import OUTPUT_DIR
from pipeline_agent import render_evidence_pdf

CASE_ID = "IUU-PIPELINE-TEST-001"
DOC = "combined_legal_package"


_LEGACY_DOCS = (
    "notice_of_violation",
    "cease_and_desist_order",
    "port_inspection_order",
    "evidence_package",
)


def _clean(case_dir):
    """Remove the combined PDF and any legacy four-PDF leftovers from earlier runs."""
    for doc in (DOC, *_LEGACY_DOCS):
        for ext in ("pdf", "html", "canonical.html"):
            (case_dir / f"{doc}.{ext}").unlink(missing_ok=True)


def scenario_high() -> tuple[bool, str]:
    case_dir = OUTPUT_DIR / CASE_ID
    case_dir.mkdir(parents=True, exist_ok=True)
    _clean(case_dir)

    events = json.dumps(
        [
            {
                "type": "GAP",
                "start": "2026-04-18T03:42:00+00:00",
                "end": "2026-04-18T11:27:00+00:00",
                "position": {"lat": -1.5383, "lon": -91.145},
                "duration_hours": 7.75,
                "metadata": {"reason": "AIS disabled inside Galapagos Marine Reserve"},
            },
            {
                "type": "PORT_VISIT",
                "start": "2024-09-03T08:14:00+00:00",
                "end": "2024-09-04T19:42:00+00:00",
                "position": {"lat": -12.0464, "lon": -77.1428},
                "duration_hours": 35.47,
                "metadata": {"port_name": "Callao", "prior_offense": True},
            },
        ]
    )

    t0 = time.monotonic()
    out = render_evidence_pdf.invoke(
        {
            "mmsi": "412345678",
            "latitude": -0.7533,
            "longitude": -90.3689,
            "region_name": "Galapagos Marine Reserve",
            "risk_classification": "HIGH",
            "risk_score": 0.92,
            "risk_reasoning": (
                "Vessel transited 86 nm inside the Galapagos Marine Reserve over 7h45m "
                "with AIS disabled. SAR confirms presence at 06:14 UTC. Unregistered with "
                "IATTC and Ecuador. Prior AIS-disabling offense in Peruvian EEZ (2024-09-03)."
            ),
            "vessel_name": "LU RONG YUAN YU 666",
            "vessel_flag": "CHN",
            "vessel_imo": "8765432",
            "gear_type": "longliners",
            "length_m": 56.0,
            "last_seen_iso": "2026-04-18T11:27:00+00:00",
            "region_id": "galapagos",
            "eez_country": "ECU",
            "case_id": CASE_ID,
            "events_json": events,
        }
    )
    elapsed = time.monotonic() - t0
    print(f"\n[HIGH] tool returned in {elapsed:.1f}s:")
    print(out)

    if not out.startswith("EVIDENCE_PDF_RENDERED:"):
        return False, "tool did not report a successful render"

    pdf = case_dir / f"{DOC}.pdf"
    canonical = case_dir / f"{DOC}.canonical.html"
    if not pdf.exists() or pdf.stat().st_size < 50_000:
        return False, f"{pdf} missing or too small"
    if not canonical.exists():
        return False, f"{canonical} missing"

    m = re.search(r"sha256:\s*([0-9a-f]{64})", out)
    if not m:
        return False, "no sha256 in tool output"
    actual = hashlib.sha256(canonical.read_bytes()).hexdigest()
    if actual != m.group(1):
        return False, f"hash mismatch: canonical={actual[:16]} reported={m.group(1)[:16]}"

    return True, f"{pdf.stat().st_size:,} B PDF, hash anchor verifies"


def scenario_refused(verdict: str) -> tuple[bool, str]:
    case_dir = OUTPUT_DIR / f"{CASE_ID}-{verdict}"
    case_dir.mkdir(parents=True, exist_ok=True)
    _clean(case_dir)

    out = render_evidence_pdf.invoke(
        {
            "mmsi": "412345678",
            "latitude": -0.7533,
            "longitude": -90.3689,
            "region_name": "Galapagos Marine Reserve",
            "risk_classification": verdict,
            "risk_reasoning": "All signals were silent; nothing actionable.",
            "case_id": f"{CASE_ID}-{verdict}",
        }
    )
    print(f"\n[{verdict}] tool returned:")
    print(out)

    pdf = case_dir / f"{DOC}.pdf"
    if pdf.exists():
        return False, f"PDF was written despite verdict={verdict}"
    if "NOT RENDERED" not in out and "skipped" not in out.lower():
        return False, "tool did not signal it skipped rendering"
    return True, "tool correctly refused; no PDF written"


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    for label, fn in [
        ("HIGH (renders)", scenario_high),
        ("LOW (refuses)", lambda: scenario_refused("LOW")),
        ("INSUFFICIENT_DATA (refuses)", lambda: scenario_refused("INSUFFICIENT_DATA")),
    ]:
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, f"raised {type(exc).__name__}: {exc}"
        results.append((label, ok, detail))

    print("\n---- summary ----")
    for label, ok, detail in results:
        print(f"  {'OK  ' if ok else 'FAIL'}  {label:<32}  {detail}")

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
