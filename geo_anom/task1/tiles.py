"""
Tile manifests and 4-band NAIP tiles from the Microsoft Planetary Computer.

A manifest is a JSON list of sites, one tile each:
    {"farm_name", "county", "animal_type", "headcount", "status",
     "lat", "lon", "tile_path", "bbox", "naip_item_id", "naip_datetime"}

MD iMAP (our other imagery source) is RGB-only (service metadata:
bandCount=3). Robinson et al.'s model needs true 4-band input, so tiles come
from Planetary Computer's NAIP STAC collection -- public, no auth, current
(2023) 0.3m imagery for Maryland, resampled to 1m on read.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds

from geo_anom.core.geo_utils import BBox

ROOT = Path(__file__).resolve().parent.parent.parent
# v2 = edge-safe mosaic (2026-10-07). The older naip_tiles_pc_4band_full/ tiles
# are distorted for 219/417 sites -- don't use them.
DEFAULT_MANIFEST = ROOT / "data/raw/naip_tiles_pc_4band_v2/manifest.json"
STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
BUFFER_KM = 1.0

# Matches Microsoft's training imagery (1m NAIP). Planetary Computer serves
# recent MD NAIP at native 0.3m -- at native res a single poultry house spans
# 300-650px, far larger than the model's 256px inference chip, which badly
# degrades detection. Resample to 1m during the read instead.
TARGET_RESOLUTION_M = 1.0


def load_manifest(path: Path = DEFAULT_MANIFEST) -> list[dict]:
    return json.loads(Path(path).read_text())


def tile_path(site: dict) -> Path:
    """Manifest tile paths are stored relative to the repo root."""
    p = Path(site["tile_path"])
    return p if p.is_absolute() else ROOT / p


def site_id(site: dict) -> str:
    """Unique key for a site. Farm names are not unique (two separate
    'Chaudhry Farm, LLC/Pervaiz Akhtar' permits, 13 km apart)."""
    if site.get("tile_path"):
        # Full relative path: tile *file names* repeat across directories
        # (site_0000-0087 exist in both naip_tiles_pc_4band_full/ and _delta/).
        p = Path(site["tile_path"])
        return str(p.relative_to(ROOT) if p.is_absolute() and p.is_relative_to(ROOT) else p)
    return f"{site['farm_name']}@{site['lat']:.5f},{site['lon']:.5f}"


def find_site(manifest: list[dict], name: str) -> dict:
    """Case-insensitive substring match on farm_name; errors if not unique."""
    hits = [s for s in manifest if name.lower() in s["farm_name"].lower()]
    if len(hits) != 1:
        names = [s["farm_name"] for s in hits[:10]]
        raise ValueError(f"{len(hits)} sites match {name!r}: {names}")
    return hits[0]


def find_naip_item(lon: float, lat: float, session: requests.Session) -> dict | None:
    """Most recent NAIP STAC item covering a point."""
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


def find_naip_items(bbox: BBox, session: requests.Session) -> list[dict]:
    """All NAIP STAC items intersecting a bbox, most recent first."""
    w, so, e, n = bbox.west, bbox.south, bbox.east, bbox.north
    resp = session.post(
        STAC_SEARCH_URL,
        json={
            "collections": ["naip"],
            "intersects": {"type": "Polygon", "coordinates": [[[w, so], [e, so], [e, n], [w, n], [w, so]]]},
            "limit": 50,
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("features", [])


def download_tile(site: dict, out_path: Path, session: requests.Session | None = None) -> dict | None:
    """Download a 2km x 2km, 1m, 4-band tile centred on site lat/lon.

    Every NAIP image (quarter quad) touching the square is warped onto one
    fixed 1 m UTM grid and mosaicked, most recent first. The earlier version
    (used for every tile from 2026-09-01 to 2026-10-06) read a single image
    with an out-of-range window: when the 2 km square crossed that image's
    edge (219 of 417 sites), rasterio clipped the read to the image and the
    clipped data was then stretched over the full tile -- tiles shifted by up
    to ~500 m and distorted, while still looking self-consistent.

    Returns the site dict with tile_path/bbox/naip_item_id(s)/naip_datetime
    filled in, or None if no imagery was found.
    """
    from rasterio.transform import from_origin
    from rasterio.warp import reproject

    session = session or requests.Session()
    bbox = BBox.from_point(lon=site["lon"], lat=site["lat"], buffer_km=BUFFER_KM)
    items = find_naip_items(bbox, session)
    if not items:
        print(f"  no NAIP item found for {site['farm_name']}")
        return None

    # Destination grid: the first (most recent) item's UTM CRS, snapped to 1 m.
    with rasterio.open(items[0]["assets"]["image"]["href"]) as first:
        dst_crs = first.crs
        count = first.count
        profile = first.profile.copy()
    left, bottom, right, top = transform_bounds("EPSG:4326", dst_crs, bbox.west, bbox.south, bbox.east, bbox.north)
    r = TARGET_RESOLUTION_M
    left, top = np.floor(left / r) * r, np.ceil(top / r) * r
    width, height = int(np.ceil((right - left) / r)), int(np.ceil((top - bottom) / r))
    dst_transform = from_origin(left, top, r, r)

    mosaic = np.zeros((count, height, width), dtype=np.uint8)
    used = []
    for item in items:
        filled = mosaic.any(axis=0)
        if filled.all():
            break
        with rasterio.open(item["assets"]["image"]["href"]) as src:
            tmp = np.zeros_like(mosaic)
            for b in range(count):
                reproject(rasterio.band(src, b + 1), tmp[b], src_transform=src.transform, src_crs=src.crs,
                          dst_transform=dst_transform, dst_crs=dst_crs, src_nodata=0, dst_nodata=0,
                          resampling=Resampling.average)
        new = tmp.any(axis=0) & ~filled
        if new.any():
            mosaic[:, new] = tmp[:, new]
            used.append(item)
    if not used:
        print(f"  empty mosaic for {site['farm_name']}")
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile.update(
        height=height, width=width, transform=dst_transform, crs=dst_crs, count=count,
        driver="GTiff", compress="lzw", predictor=2, tiled=True, blockxsize=256, blockysize=256, nodata=None,
    )
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(mosaic)

    return {
        **site,
        "tile_path": str(out_path.relative_to(ROOT)) if out_path.is_relative_to(ROOT) else str(out_path),
        "bbox": bbox.as_tuple,
        "naip_item_id": used[0]["id"],
        "naip_item_ids": [it["id"] for it in used],
        "naip_datetime": used[0]["properties"].get("datetime"),
        "naip_datetimes": sorted({it["properties"].get("datetime", "")[:10] for it in used}),
        "tile_method": "mosaic_reproject_v2",
    }


def read_tile(path: Path) -> tuple[np.ndarray, dict]:
    """Read a tile as HWC uint8 (R, G, B, NIR) plus its georeferencing."""
    with rasterio.open(path) as src:
        img = np.moveaxis(src.read(), 0, -1)
        meta = {"crs": src.crs, "transform": src.transform,
                "bounds": src.bounds, "res_m": src.res[0]}
    return img, meta
