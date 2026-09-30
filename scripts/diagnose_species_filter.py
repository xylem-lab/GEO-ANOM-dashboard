#!/usr/bin/env python3
"""
Diagnose why 13/14 dairy farms show zero poultry-U-Net detections.

Runs raw U-Net inference + polygonization (no filter) on each of the 14
dairy_cattle farms in the full manifest, and reports, for every raw
candidate polygon: its area/length/width/aspect, and exactly which
Tulbure-filter criterion it fails (if any). This distinguishes two
competing hypotheses from docs/research_log.md's 2026-09-16..21 entry:

  (1) the model DOES segment plausible barn-shaped blobs on these farms,
      but WIDTH_MAX_M=30.0 (or another threshold) rejects them -- a cheap
      filter fix.
  (2) the model produces no reasonable candidate shapes at all on these
      farms -- a deeper segmentation/roof-signature issue, not fixable by
      threshold tuning alone.

Usage:
    python scripts/diagnose_dairy_filter.py
"""
import json
import sys
from pathlib import Path

import rasterio
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unet_inference import load_model, run_inference_on_tile, mask_to_polygons
from unet_detect import (
    polygon_geo_stats,
    passes_tulbure_filter,
    AREA_MIN_M2, AREA_MAX_M2,
    LENGTH_MIN_M, LENGTH_MAX_M,
    WIDTH_MIN_M, WIDTH_MAX_M,
    ASPECT_MIN, ASPECT_MAX,
)

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data/raw/naip_tiles_pc_4band_full/manifest.json"


def failing_criteria(stats: dict) -> list[str]:
    area, length, width = stats["area_m2"], stats["long_side_m"], stats["short_side_m"]
    fails = []
    if not (AREA_MIN_M2 <= area <= AREA_MAX_M2):
        fails.append(f"AREA={area:.0f} (need {AREA_MIN_M2:.0f}-{AREA_MAX_M2:.0f})")
    if not (LENGTH_MIN_M <= length <= LENGTH_MAX_M):
        fails.append(f"LENGTH={length:.1f} (need {LENGTH_MIN_M:.0f}-{LENGTH_MAX_M:.0f})")
    if width <= 0 or not (WIDTH_MIN_M <= width <= WIDTH_MAX_M):
        fails.append(f"WIDTH={width:.1f} (need {WIDTH_MIN_M:.0f}-{WIDTH_MAX_M:.0f})")
    if width > 0:
        aspect = length / width
        if not (ASPECT_MIN <= aspect <= ASPECT_MAX):
            fails.append(f"ASPECT={aspect:.2f} (need {ASPECT_MIN:.1f}-{ASPECT_MAX:.1f})")
    return fails


import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--farm-names", nargs="*", default=None,
                         help="Exact farm_name values to diagnose")
    parser.add_argument("--animal-type-contains", default=None,
                         help="Substring to match against manifest animal_type")
    parser.add_argument("--out-json", default=None,
                         help="Output path for the raw diagnosis JSON")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text())
    if args.farm_names:
        wanted = set(args.farm_names)
        dairy_sites = [f for f in manifest if f["farm_name"] in wanted]
    elif args.animal_type_contains:
        dairy_sites = [f for f in manifest if args.animal_type_contains in f["animal_type"].lower()]
    else:
        dairy_sites = [f for f in manifest if "dairy" in f["animal_type"].lower()]
    print(f"Diagnosing {len(dairy_sites)} farms...\n")

    model, device = load_model()
    print(f"Model loaded on device={device}\n")

    results = []
    for site in dairy_sites:
        tile_path = Path(site["tile_path"])
        if not tile_path.is_absolute():
            tile_path = ROOT / tile_path
        if not tile_path.exists():
            print(f"[{site['farm_name']}] MISSING TILE: {tile_path}")
            continue

        with rasterio.open(tile_path) as src:
            tile_crs = src.crs
        to_wgs84 = Transformer.from_crs(tile_crs, "EPSG:4326", always_xy=True).transform

        mask, transform = run_inference_on_tile(model, device, tile_path)
        raw_polys = mask_to_polygons(mask, transform)

        print(f"=== {site['farm_name']} (headcount={site['headcount']}, county={site['county']}) ===")
        print(f"    raw candidate polygons: {len(raw_polys)}")

        n_pass = 0
        near_misses = []
        for poly in raw_polys:
            stats = polygon_geo_stats(poly)
            if stats["area_m2"] < 50:  # skip tiny noise fragments entirely
                continue
            passed = passes_tulbure_filter(stats, None)
            fails = failing_criteria(stats)
            if passed:
                n_pass += 1
            elif stats["area_m2"] >= 200:  # only show plausibly-barn-sized fragments
                near_misses.append((stats, fails))

        print(f"    passing current filter: {n_pass}")
        for stats, fails in sorted(near_misses, key=lambda x: -x[0]["area_m2"])[:5]:
            print(f"    near-miss: area={stats['area_m2']:.0f}m2 "
                  f"length={stats['long_side_m']:.1f}m width={stats['short_side_m']:.1f}m "
                  f"-- fails: {', '.join(fails)}")
        print()

        results.append({
            "farm_name": site["farm_name"],
            "headcount": site["headcount"],
            "raw_count": len(raw_polys),
            "n_pass_current_filter": n_pass,
            "near_misses": [
                {"area_m2": s["area_m2"], "length_m": s["long_side_m"],
                 "width_m": s["short_side_m"], "fails": f}
                for s, f in near_misses
            ],
        })

    out_path = Path(args.out_json) if args.out_json else ROOT / "docs/dairy_filter_diagnosis.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")

    total_farms_with_width_only_fail = sum(
        1 for r in results
        if r["n_pass_current_filter"] == 0
        and any(len(nm["fails"]) == 1 and nm["fails"][0].startswith("WIDTH") for nm in r["near_misses"])
    )
    print(f"\nFarms with >=1 near-miss shape failing ONLY on WIDTH: {total_farms_with_width_only_fail}")


if __name__ == "__main__":
    main()
