"""
The full Task 1 mapping run, as one function.

`run_pipeline()` is what `scripts/map_buildings.py` and
`notebooks/03_full_dataset.ipynb` both call:

    sites -> (download missing tiles) -> U-Net + shape filter per tile
    -> de-duplicate across overlapping tiles -> attribute to permits
    -> out_dir/{sites.json, candidates.geojson, buildings.geojson,
                farms.csv, buildings.kmz, run_meta.json}
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from geo_anom.task1 import detect, tiles
from geo_anom.task1.kmz import write_kmz
from geo_anom.task1.merge import deduplicate, farm_overview

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


def select_sites(manifest: list[dict], farms: Iterable[str] = (), counties: Iterable[str] = ()) -> list[dict]:
    farms, counties = list(farms), list(counties)
    sites = manifest
    if farms:
        sites = [s for s in sites if any(f.lower() in s["farm_name"].lower() for f in farms)]
    if counties:
        sites = [s for s in sites if s.get("county") in counties]
    return sites


def write_geojson(path: Path, features: list[dict]):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def run_pipeline(
    sites: list[dict],
    out_dir: Path,
    manifest_path: Path = tiles.DEFAULT_MANIFEST,
    manifest: list[dict] | None = None,
    download_missing: bool = False,
    use_road_filter: bool = False,
    dedupe: bool = True,
    filters: dict | None = None,
    progress: Callable[[Iterable], Iterable] | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Run the whole mapping step and write every output. Returns run_meta.

    `manifest` (default: loaded from `manifest_path`) is the full permit list
    used to attribute buildings -- pass the full registry even when `sites`
    is a subset, so a barn near an unselected neighbour is attributed to it.
    `progress` wraps the per-tile loop (e.g. tqdm).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest if manifest is not None else tiles.load_manifest(manifest_path)

    # Tiles
    ready = []
    for i, s in enumerate(sites):
        if s.get("tile_path") and tiles.tile_path(s).exists():
            ready.append(s)
        elif download_missing:
            got = tiles.download_tile(s, out_dir / "tiles" / f"site_{i:04d}.tif")
            if got:
                ready.append(got)
        else:
            log(f"  no tile on disk for {s['farm_name']} (use download_missing)")
    (out_dir / "sites.json").write_text(json.dumps(ready, indent=2))

    # Detect
    model, device = detect.load_model()
    log(f"Model on {device}; {len(ready)} tiles")
    candidates, farm_rows = [], []
    loop = progress(ready) if progress else ready
    for i, s in enumerate(loop):
        r = detect.detect_site(s, model, device, use_road_filter=use_road_filter)
        candidates += r.features(include_rejected=True)
        farm_rows.append({"site_id": tiles.site_id(s), "farm_name": s["farm_name"], "county": s.get("county"),
                          "animal_type": s.get("animal_type"), "headcount": s.get("headcount"),
                          "tile": Path(s["tile_path"]).name, "naip_datetime": s.get("naip_datetime"),
                          "raw_candidates": len(r.candidates), "kept_in_tile": len(r.kept)})
        if not progress:
            log(f"[{i + 1}/{len(ready)}] {s['farm_name'][:45]:<45} raw={len(r.candidates):<4} kept={len(r.kept)}")

    kept = [f for f in candidates if f["properties"]["kept"]]
    write_geojson(out_dir / "candidates.geojson", candidates)

    # Merge
    if not dedupe:
        buildings_fc = kept
        n_unique = len(kept)
    else:
        buildings = deduplicate(kept, manifest)
        buildings_fc = json.loads(buildings.to_json(drop_id=True))["features"]
        n_unique = len(buildings)
        per_farm = buildings.groupby("assigned_site_id").agg(
            buildings=("building_id", "size"), building_area_m2=("area_m2", "sum"),
            median_assign_dist_m=("assigned_distance_m", "median"))
        overview = farm_overview(buildings)
        overview.to_file(out_dir / "farms_overview.geojson", driver="GeoJSON")
        farms = (pd.DataFrame(farm_rows).set_index("site_id").join(per_farm, how="left")
                 .join(overview.set_index("site_id")[["lat", "lon", "maps_url"]]
                       .rename(columns={"lat": "barns_lat", "lon": "barns_lon"}), how="left"))
        farms[["buildings", "building_area_m2"]] = farms[["buildings", "building_area_m2"]].fillna(0)
        farms.reset_index().to_csv(out_dir / "farms.csv", index=False)
    write_geojson(out_dir / "buildings.geojson", buildings_fc)

    rejected = [f for f in candidates if not f["properties"]["kept"]]
    write_kmz(buildings_fc + rejected, out_dir / "buildings.kmz", sites=ready,
              title=f"GEO-ANOM Task 1 buildings ({out_dir.name})")

    meta = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(Path(manifest_path)),
        "checkpoint": str(detect.CHECKPOINT_PATH.relative_to(ROOT)),
        "checkpoint_sha256": sha256(detect.CHECKPOINT_PATH),
        "device": str(device),
        "filters": filters or {"farm": [], "county": []},
        "use_road_filter": use_road_filter,
        "dedupe": dedupe,
        "thresholds": detect.filter_thresholds(),
        "species_overrides": detect.SPECIES_FILTER_OVERRIDES,
        "close_kernel": detect.CLOSE_KERNEL,
        "tiles": len(ready),
        "raw_candidates": len(candidates),
        "kept_detections": len(kept),
        "unique_buildings": n_unique,
    }
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))

    # Accuracy vs. Soroka & Duren hand-labelled houses, when that data is on disk.
    from geo_anom.task1.evaluate import GROUND_TRUTH, evaluate_run
    if dedupe and GROUND_TRUTH.exists():
        acc = evaluate_run(out_dir)
        (out_dir / "accuracy.json").write_text(json.dumps(acc, indent=2))
        o = acc["object_level"]
        log(f"Accuracy vs Soroka & Duren: precision {o['precision']:.2f}, recall {o['recall']:.2f}, "
            f"F1 {o['f1']:.2f}; farm-count R^2 {acc['farm_level_counts']['r2']:.2f}")
    log(f"\n{len(kept)} kept detections -> {n_unique} unique buildings")
    log(f"Outputs in {out_dir}")
    return meta


def latest_run(base: Path = ROOT / "data/processed/task1") -> Path | None:
    """Most recent complete run directory (has run_meta.json)."""
    runs = sorted((p for p in base.glob("*/run_meta.json")), key=lambda p: p.stat().st_mtime)
    return runs[-1].parent if runs else None
