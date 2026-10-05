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
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo_anom.task1 import detect, tiles  # noqa: E402
from geo_anom.task1.kmz import write_kmz  # noqa: E402
from geo_anom.task1.merge import deduplicate  # noqa: E402

ROOT = tiles.ROOT


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "geo_anom", "scripts"],
                               capture_output=True, text=True).stdout.strip()
        return out + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


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
    sites = manifest
    if args.farm:
        sites = [s for s in sites if any(f.lower() in s["farm_name"].lower() for f in args.farm)]
    if args.county:
        sites = [s for s in sites if s.get("county") in args.county]
    if not sites:
        sys.exit("No sites selected.")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Tiles
    ready = []
    for i, s in enumerate(sites):
        if s.get("tile_path") and tiles.tile_path(s).exists():
            ready.append(s)
        elif args.download_missing:
            out = args.out_dir / "tiles" / f"site_{i:04d}.tif"
            got = tiles.download_tile(s, out)
            if got:
                ready.append(got)
        else:
            print(f"  no tile on disk for {s['farm_name']} (use --download-missing)")
    (args.out_dir / "sites.json").write_text(json.dumps(ready, indent=2))

    # Detect
    model, device = detect.load_model()
    print(f"Model on {device}; {len(ready)} tiles")
    candidates, farm_rows = [], []
    for i, s in enumerate(ready):
        r = detect.detect_site(s, model, device, use_road_filter=args.use_road_filter)
        candidates += r.features(include_rejected=True)
        farm_rows.append({"site_id": tiles.site_id(s), "farm_name": s["farm_name"], "county": s.get("county"),
                          "animal_type": s.get("animal_type"), "headcount": s.get("headcount"),
                          "tile": Path(s["tile_path"]).name, "naip_datetime": s.get("naip_datetime"),
                          "raw_candidates": len(r.candidates), "kept_in_tile": len(r.kept)})
        print(f"[{i + 1}/{len(ready)}] {s['farm_name'][:45]:<45} raw={len(r.candidates):<4} kept={len(r.kept)}")

    kept = [f for f in candidates if f["properties"]["kept"]]
    write_geojson(args.out_dir / "candidates.geojson", candidates)

    # Merge
    if args.no_dedupe:
        buildings_fc = kept
        n_unique = len(kept)
    else:
        buildings = deduplicate(kept, manifest)
        buildings_fc = json.loads(buildings.to_json(drop_id=True))["features"]
        n_unique = len(buildings)
        per_farm = buildings.groupby("assigned_site_id").agg(
            buildings=("building_id", "size"), building_area_m2=("area_m2", "sum"),
            median_assign_dist_m=("assigned_distance_m", "median"))
        farms = pd.DataFrame(farm_rows).set_index("site_id").join(per_farm, how="left")
        farms[["buildings", "building_area_m2"]] = farms[["buildings", "building_area_m2"]].fillna(0)
        farms.reset_index().to_csv(args.out_dir / "farms.csv", index=False)
    write_geojson(args.out_dir / "buildings.geojson", buildings_fc)

    rejected = [f for f in candidates if not f["properties"]["kept"]]
    write_kmz(buildings_fc + rejected, args.out_dir / "buildings.kmz", sites=ready,
              title=f"GEO-ANOM Task 1 buildings ({args.out_dir.name})")

    meta = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "manifest": str(args.manifest),
        "manifest_sha256": sha256(args.manifest),
        "checkpoint": str(detect.CHECKPOINT_PATH.relative_to(ROOT)),
        "checkpoint_sha256": sha256(detect.CHECKPOINT_PATH),
        "device": str(device),
        "filters": {"farm": args.farm, "county": args.county},
        "use_road_filter": args.use_road_filter,
        "dedupe": not args.no_dedupe,
        "thresholds": detect.filter_thresholds(),
        "species_overrides": detect.SPECIES_FILTER_OVERRIDES,
        "close_kernel": detect.CLOSE_KERNEL,
        "tiles": len(ready),
        "raw_candidates": len(candidates),
        "kept_detections": len(kept),
        "unique_buildings": n_unique,
    }
    (args.out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\n{len(kept)} kept detections -> {n_unique} unique buildings")
    print(f"Outputs in {args.out_dir}")


def write_geojson(path: Path, features: list[dict]):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


if __name__ == "__main__":
    main()
