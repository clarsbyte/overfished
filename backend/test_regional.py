"""Smoke test for the regional-laws pipeline — no LangChain, no LLM.

Stages:
  1. Cache integrity (regions present, schemas valid)
  2. Bbox-based coastal-state resolution at 6 sample points
  3. LIVE ProtectedSeas Global Max LFP query at the same points
  4. Full dossier assembly for one point (Wolf Island, Galápagos)
"""

from __future__ import annotations

import json
import sys

from protectedseas_arcgis import query_lfp_at_point
from regional_lookup import (
    assemble_legal_dossier,
    get_region_by_country,
    get_region_by_id,
    identify_coastal_state,
    list_cached_regions,
)

SAMPLE_POINTS = [
    ("Galápagos (Wolf Island)",        -1.385,  -91.821),
    ("Hermandad reserve, NW of GMR",    1.500,  -91.500),
    ("Tubbataha Reefs",                 8.850,  119.917),
    ("Manila Bay",                     14.500,  120.900),
    ("Strait of Sicily",               36.500,   12.000),
    ("Mid-Atlantic (no cache)",         0.000,  -30.000),
]


def main() -> int:
    print("== 1) Cached regions ==")
    regions = list_cached_regions()
    for r in regions:
        bb = r["bbox"]
        print(
            f"  - {r['id']}: {r['name']} ({r['country']}) | "
            f"lat[{bb['lat_min']}, {bb['lat_max']}] lon[{bb['lon_min']}, {bb['lon_max']}]"
        )

    print()
    print("== 2) Bbox coastal-state resolution ==")
    for label, lat, lon in SAMPLE_POINTS:
        region = identify_coastal_state(lat, lon)
        hit = region["id"] if region else "NONE"
        print(f"  {label:32s} ({lat:+8.3f}, {lon:+9.3f}) -> {hit}")

    print()
    print("== 3) LIVE ProtectedSeas LFP queries ==")
    for label, lat, lon in SAMPLE_POINTS:
        try:
            lfp = query_lfp_at_point(lat, lon)
        except Exception as exc:
            print(f"  {label:32s} FAIL: {type(exc).__name__}: {exc}")
            continue
        score = lfp.get("lfp")
        area = lfp.get("area_sqkm")
        last = lfp.get("feature_last_update")
        if score is None:
            print(f"  {label:32s} no LFP polygon at this point")
        else:
            print(
                f"  {label:32s} LFP={score} area={area} sq.km last_update={last}"
            )

    print()
    print("== 4) Coastal-state direct lookups ==")
    for region_id in [r["id"] for r in regions]:
        region = get_region_by_id(region_id)
        fl = (region or {}).get("fishlex") or {}
        pl = (region or {}).get("portlex") or {}
        fx = (region or {}).get("faolex") or {}
        print(f"  {region_id}:")
        print(f"     fishlex provenance: {(fl.get('provenance') or {}).get('source_url')}")
        print(f"     portlex provenance: {(pl.get('provenance') or {}).get('source_url')}")
        print(f"     faolex records:     {len(fx.get('key_records') or [])}")

    by_country = get_region_by_country("PHL")
    if by_country:
        print(f"  by-country PHL -> {by_country['id']}")

    print()
    print("== 5) Full dossier (Wolf Island, port=ECU) ==")
    dossier = assemble_legal_dossier(-1.385, -91.821, port_country_code="ECU")
    print(json.dumps(dossier, indent=2, ensure_ascii=False, default=str)[:4000])
    print("  ...")

    if dossier.get("missing"):
        print(f"  Gaps reported: {dossier['missing']}")
    else:
        print("  All layers populated.")

    print()
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
