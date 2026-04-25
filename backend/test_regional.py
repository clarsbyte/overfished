"""Smoke test for the regional-laws lookup — no LangChain, no LLM."""

from __future__ import annotations

import json
import sys

from regional_lookup import (
    get_region_by_country,
    get_region_by_id,
    identify_region,
    list_regions,
)


SAMPLE_POINTS = [
    ("Galápagos (Wolf Island)",          -1.385,  -91.821),
    ("Hermandad reserve, NW of GMR",      1.500,  -91.500),
    ("Tubbataha Reefs",                   8.850,  119.917),
    ("Manila Bay",                       14.500,  120.900),
    ("Strait of Sicily",                 36.500,   12.000),
    ("Mid-Atlantic (no cache)",           0.000,  -30.000),
]


def main() -> int:
    print("Cached regions:")
    for r in list_regions():
        bb = r["bbox"]
        print(
            f"  - {r['id']}: {r['name']} ({r['country']}) | "
            f"lat[{bb['lat_min']}, {bb['lat_max']}] lon[{bb['lon_min']}, {bb['lon_max']}]"
        )

    print()
    print("Point-in-region resolution:")
    for label, lat, lon in SAMPLE_POINTS:
        region = identify_region(lat, lon)
        hit = region["id"] if region else "NONE"
        print(f"  {label:32s} ({lat:+8.3f}, {lon:+9.3f}) -> {hit}")

    print()
    print("Direct lookup by id (galapagos-marine-reserve):")
    region = get_region_by_id("galapagos-marine-reserve")
    if region:
        print(f"  Rules: {len(region['rules'])}")
        print(f"  Foreign-vessel requirements: {region['foreign_vessel_requirements'][:120]}...")
        print(f"  Port state measures:         {region['port_state_measures'][:120]}...")
    else:
        print("  FAIL: not found")
        return 1

    print()
    print("Direct lookup by country (PHL):")
    region = get_region_by_country("PHL")
    if region:
        print(f"  Matched: {region['name']}")
        print(f"  First rule: {region['rules'][0]['rule'][:120]}...")
    else:
        print("  FAIL: not found")
        return 2

    if len(sys.argv) > 1 and sys.argv[1] == "--dump":
        print()
        print("Full Galápagos record:")
        print(json.dumps(get_region_by_id("galapagos-marine-reserve"), indent=2, ensure_ascii=False))

    print()
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
