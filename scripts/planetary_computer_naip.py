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

import numpy as np
import rasterio
import requests
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo_anom.core.geo_utils import BBox

ROOT = Path(__file__).resolve().parent.parent
STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
BUFFER_KM = 1.0  # matches the top-10 pilot script


def find_naip_item(lon: float, lat: float, session: requests.Session) -> dict | None:
    """Find the most recent NAIP STAC item covering a point."""
    resp = session.post(
        STAC_SEARCH_URL,
        json={
            "collections": ["naip"],
            "intersects": {"type": "Point", "coordinates": [lon, lat]},
            "limit": 5,
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    features = resp.json().get("features", [])
    return features[0] if features else None


TARGET_RESOLUTION_M = 1.0  # matches Microsoft's training imagery (1m NAIP);
# Planetary Computer serves recent MD NAIP at native 0.3m -- reading at native
# res would make a single poultry house span 300-650px, far larger than the
# model's 256px inference chip, which would badly degrade detection quality
# on top of ballooning file size 10x+. Resample to 1m during the read instead.


def download_tile(site: dict, out_path: Path, session: requests.Session) -> dict | None:
    item = find_naip_item(site["lon"], site["lat"], session)
    if item is None:
        print(f"  no NAIP item found for {site['farm_name']}")
        return None

    href = item["assets"]["image"]["href"]
    bbox = BBox.from_point(lon=site["lon"], lat=site["lat"], buffer_km=BUFFER_KM)

    with rasterio.open(href) as src:
        # Reproject bbox corners into the tile's CRS for the window read.
        from rasterio.warp import transform_bounds
        from rasterio.enums import Resampling

        left, bottom, right, top = transform_bounds(
            "EPSG:4326", src.crs, bbox.west, bbox.south, bbox.east, bbox.north
        )
        window = from_bounds(left, bottom, right, top, transform=src.transform)
        if window.width < 10 or window.height < 10:
            print(f"  empty/tiny window for {site['farm_name']}")
            return None

        native_res_m = src.res[0]  # assume square pixels, meters (projected CRS)
        scale = native_res_m / TARGET_RESOLUTION_M
        out_width = max(int(round(window.width * scale)), 1)
        out_height = max(int(round(window.height * scale)), 1)

        data = src.read(
            window=window,
            out_shape=(src.count, out_height, out_width),
            resampling=Resampling.average,
        )
        if data.size == 0:
            print(f"  empty read for {site['farm_name']}")
            return None
        # window_transform gives the native-res transform; rescale it to
        # match the resampled (target-res) output raster.
        native_transform = src.window_transform(window)
        out_transform = native_transform * native_transform.scale(
            window.width / out_width, window.height / out_height
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        profile = src.profile.copy()
        profile.update(
            height=data.shape[1],
            width=data.shape[2],
            transform=out_transform,
            driver="GTiff",
            compress="lzw",
            predictor=2,
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(data)

    return {
        **site,
        "tile_path": str(out_path),
        "bbox": bbox.as_tuple,
        "naip_item_id": item["id"],
        "naip_datetime": item["properties"].get("datetime"),
    }


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
