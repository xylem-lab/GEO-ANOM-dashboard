#!/usr/bin/env python3
"""
Task 1 building mapping -- the one entry point.

    manifest -> (download missing tiles) -> U-Net + shape filter per tile
    -> de-duplicate across overlapping tiles -> attribute to permits
    -> buildings.geojson, candidates.geojson, farms.csv, buildings.kmz,
       run_meta.json

Examples:
    # everything in the full registry manifest
    python3 scripts/map_buildings.py

    # a few farms, to check by eye
    python3 scripts/map_buildings.py --farm "Lester C. Jones" --farm "Sheng Lin" --out-dir data/processed/task1/check

    # a new list of sites (needs farm_name/lat/lon; tiles are downloaded)
    python3 scripts/map_buildings.py --manifest my_sites.json --download-missing

N/P supply is a separate step: scripts/compute_supply.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo_anom.task1 import tiles  # noqa: E402
from geo_anom.task1.pipeline import run_pipeline, select_sites  # noqa: E402

ROOT = tiles.ROOT


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=tiles.DEFAULT_MANIFEST)
    ap.add_argument("--farm", action="append", default=[],
                    help="Only sites whose farm_name contains this (repeatable, case-insensitive)")
    ap.add_argument("--county", action="append", default=[], help="Only these counties (repeatable)")
    ap.add_argument("--out-dir", type=Path,
                    default=ROOT / f"data/processed/task1/run_{dt.date.today().isoformat()}")
    ap.add_argument("--download-missing", action="store_true",
                    help="Download tiles for sites with no tile on disk (Planetary Computer)")
    ap.add_argument("--use-road-filter", action="store_true",
                    help="Also reject candidates <20 m from an OSM road (off in the committed baseline)")
    ap.add_argument("--no-dedupe", action="store_true",
                    help="Keep one feature per tile detection (reproduces the old per-tile output)")
    args = ap.parse_args()

    manifest = tiles.load_manifest(args.manifest)
    sites = select_sites(manifest, args.farm, args.county)
    if not sites:
        sys.exit("No sites selected.")
    run_pipeline(sites, args.out_dir, manifest_path=args.manifest, manifest=manifest,
                 download_missing=args.download_missing, use_road_filter=args.use_road_filter,
                 dedupe=not args.no_dedupe, filters={"farm": args.farm, "county": args.county})


if __name__ == "__main__":
    main()
