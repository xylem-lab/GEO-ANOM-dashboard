"""
Full-registry NAIP tile acquisition for all active MDE AFO permits.

Extends the top-10 pilot (top_headcount_imagery_test.py) to the complete
active-permit set: fresh registry pull -> filter to active statuses ->
download one NAIP tile per site, writing a manifest.json that keeps
farm_name/county/animal_type/headcount attached to each tile so the
classical CV detector can attribute detections back to specific permits.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geo_anom.core.config import get_config
from geo_anom.core.geo_utils import BBox
from geo_anom.phase1.afo_registry import AFORegistryClient
from geo_anom.phase1.naip_downloader import NAIPDownloader

ROOT = Path(__file__).resolve().parent.parent
TILE_DIR = ROOT / "data/raw/naip_tiles_full"
MANIFEST_PATH = TILE_DIR / "manifest.json"
BUFFER_KM = 1.0  # matches top_headcount_imagery_test.py


def load_active_permits() -> list[dict]:
    config = get_config()
    client = AFORegistryClient(config)

    print("Downloading fresh MDE AFO registry...")
    records = client.download_json()
    gdf = client.parse_permits(records)
    gdf = client.filter_active_permits(gdf)
    print(f"{len(gdf)} active permits after filtering")

    sites = []
    for _, row in gdf.iterrows():
        pt = row.geometry
        if pt is None or pt.is_empty:
            continue
        sites.append({
            "farm_name": row["farm_name"],
            "county": row["county"],
            "animal_type": row["animal_type"],
            "headcount": int(row["headcount"]),
            "status": row["status"],
            "lat": pt.y,
            "lon": pt.x,
        })
    return sites


def download_tiles(sites: list[dict]) -> list[dict]:
    config = get_config()
    downloader = NAIPDownloader(config=config)
    TILE_DIR.mkdir(parents=True, exist_ok=True)

    # Resume support: skip sites whose tile already exists on disk.
    existing_manifest = []
    if MANIFEST_PATH.exists():
        existing_manifest = json.loads(MANIFEST_PATH.read_text())
    done_names = {m["farm_name"] for m in existing_manifest if Path(m["tile_path"]).exists()}

    manifest = list(existing_manifest)
    for i, site in enumerate(sites):
        if site["farm_name"] in done_names:
            continue
        bbox = BBox.from_point(lon=site["lon"], lat=site["lat"], buffer_km=BUFFER_KM)
        tile_path = TILE_DIR / f"site_{i:04d}.tif"
        try:
            downloader.export_tile(bbox, tile_path)
            print(f"  [{i}/{len(sites)}] downloaded {tile_path.name} for {site['farm_name']}")
            manifest.append({**site, "tile_path": str(tile_path), "bbox": bbox.as_tuple})
        except Exception as e:
            print(f"  [{i}/{len(sites)}] FAILED for {site['farm_name']}: {e}")

        # Write manifest incrementally so a low-bandwidth interruption
        # doesn't lose progress.
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))

    return manifest


if __name__ == "__main__":
    sites = load_active_permits()
    print(f"\nDownloading NAIP tiles for {len(sites)} active AFO permits...")
    manifest = download_tiles(sites)
    print(f"\nDone: {len(manifest)} tiles in {TILE_DIR}")
    print(f"Manifest -> {MANIFEST_PATH}")
