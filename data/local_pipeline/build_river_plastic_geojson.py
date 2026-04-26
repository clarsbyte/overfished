#!/usr/bin/env python3
"""Slim Meijer et al. 2021 river-outfall shapefile to Mapbox-friendly GeoJSON.

Source: figshare "Supplementary data for ... 80% of global riverine plastic emissions
into the ocean" (shapefile, ~31,819 outfalls, EPSG:4326 or similar).

Prereq:  pip install geopandas  (in any venv)

Usage:
  python3 build_river_plastic_geojson.py --input /path/River_plastic.shp \\
      --output ../../frontend/public/data/river_plastic_emissions.geojson

The frontend expects Point features and a numeric property *t_yr* (tonnes / year).
Default column candidates for emissions are tried in order; override with --emissions.
Only features with emissions >= min-tonnes (default 0.1) are kept.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _default_output_path() -> Path:
    """Repo root: .../overfished/frontend/public/data/river_plastic_emissions.geojson"""
    return Path(__file__).resolve().parents[2] / "frontend" / "public" / "data" / "river_plastic_emissions.geojson"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", type=Path, help="Path to a .shp (or any driver geopandas can read).")
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: <repo>/frontend/public/data/river_plastic_emissions.geojson).",
    )
    p.add_argument(
        "--emissions",
        type=str,
        default=None,
        help="Attribute column for tonnes/year. If omitted, a short list of known names is tried.",
    )
    p.add_argument(
        "--min-tonnes",
        type=float,
        default=0.1,
        help="Minimum t_yr to keep (default: 0.1).",
    )
    p.add_argument("--indent", type=int, default=0, help="JSON indent (0 = most compact).")

    args = p.parse_args()
    if args.output is None:
        args.output = _default_output_path()
    if args.input is None:
        p.print_help()
        print(
            "\nError: --input is required. Download the Meijer 2021 shapefile from figshare, unzip, and pass the .shp path.",
            file=sys.stderr,
        )
        return 1

    try:
        import geopandas as gpd
    except ImportError as e:  # pragma: no cover
        print("Missing dependency: geopandas\n  pip install geopandas", file=sys.stderr)
        raise SystemExit(2) from e

    gdf = gpd.read_file(args.input)
    gdf = gdf.to_crs(4326)

    col = args.emissions
    if not col:
        for candidate in (
            "MEP_2015",  # common in Meijer supplementary
            "MEP_2020",
            "MEP",
            "mep_2015",
            "mep_2020",
            "mep",
            "OPE_tons",  # alternate naming in some exports
        ):
            if candidate in gdf.columns:
                col = candidate
                break
        if not col:
            numeric = gdf.select_dtypes(include=["float64", "float32", "int64"]).columns
            for c in gdf.columns:
                if c.upper().startswith("MEP") and c in numeric:
                    col = c
                    break
    if not col or col not in gdf.columns:
        print("Could not find emissions column. Available columns:\n  " + ", ".join(map(str, gdf.columns)), file=sys.stderr)
        return 1

    t = gdf[col].astype(float)
    m = t >= float(args.min_tonnes)
    gdf = gdf.loc[m].copy()
    gdf["t_yr"] = gdf[col].astype(float)
    gdf = gdf.loc[gdf.geometry.geom_type == "Point"]
    out = gdf[["geometry", "t_yr"]]
    if out.empty:
        print("No features after filtering. Check --emissions and --min-tonnes.", file=sys.stderr)
        return 1

    fc = json.loads(out.to_json())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=None if args.indent == 0 else args.indent, ensure_ascii=False)
    n = len(fc.get("features", []))
    print(f"Wrote {n} features to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
