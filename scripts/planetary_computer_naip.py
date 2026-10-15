"""
4-band (RGB+NIR) NAIP tile acquisition from the Microsoft Planetary Computer.

MD iMAP (our other imagery source) is RGB-only, confirmed via its ArcGIS
service metadata (bandCount=3). Robinson et al.'s poultry-barn model needs
true 4-band input, so this pulls tiles from Planetary Computer's NAIP STAC
collection instead -- public, no auth, and has current (2023) 0.3m imagery
for Maryland, confirmed reachable via a direct windowed rasterio read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Tile download now lives in geo_anom/task1/tiles.py (shared with
# scripts/map_buildings.py --download-missing and the notebooks).
from geo_anom.task1.tiles import BUFFER_KM, TARGET_RESOLUTION_M, download_tile, find_naip_item  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent


def main():
    import argparse
    from concurrent.futures import ThreadPoolExecutor, as_completed

    parser = argparse.ArgumentParser()
    parser.add_argument("--sites-manifest", type=Path,
                         default=ROOT / "data/raw/naip_tiles_top10/manifest.json",
                         help="Manifest with farm_name/lat/lon to source imagery for")
    parser.add_argument("--out-dir", type=Path,
                         default=ROOT / "data/raw/naip_tiles_pc_4band_pilot")
    parser.add_argument("--max-workers", type=int, default=12,
                         help="Concurrent downloads (I/O-bound: STAC search + windowed "
                              "COG read against Microsoft's public Planetary Computer "
                              "infra, not a small state server -- fine to parallelize)")
    args = parser.parse_args()

    sites = json.loads(args.sites_manifest.read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Resume support: skip sites already downloaded.
    manifest_path = args.out_dir / "manifest.json"
    out_manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    done_names = {m["farm_name"] for m in out_manifest if Path(m["tile_path"]).exists()}

    todo = [(i, s) for i, s in enumerate(sites) if s["farm_name"] not in done_names]
    print(f"{len(done_names)} already done, {len(todo)} remaining")

    def _one(idx_site):
        i, site = idx_site
        out_path = args.out_dir / f"site_{i:04d}.tif"
        session = requests.Session()
        try:
            result = download_tile(site, out_path, session)
            return i, site, result, None
        except Exception as e:
            return i, site, None, e

    completed = 0
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(_one, item) for item in todo]
        for future in as_completed(futures):
            i, site, result, err = future.result()
            completed += 1
            if err is not None:
                print(f"[{completed}/{len(todo)}] FAILED {site['farm_name']}: {err}")
            elif result:
                out_manifest.append(result)
                print(f"[{completed}/{len(todo)}] ok {site['farm_name']} ({result['naip_datetime']})")
            else:
                print(f"[{completed}/{len(todo)}] no result for {site['farm_name']}")

            # Write incrementally so an interruption doesn't lose progress.
            if completed % 10 == 0 or completed == len(todo):
                manifest_path.write_text(json.dumps(out_manifest, indent=2))

    manifest_path.write_text(json.dumps(out_manifest, indent=2))
    print(f"\nDone: {len(out_manifest)}/{len(sites)} tiles -> {args.out_dir}")
    print(f"Manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
