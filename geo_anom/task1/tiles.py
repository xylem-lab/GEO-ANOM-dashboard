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
from rasterio.windows import from_bounds

from geo_anom.core.geo_utils import BBox

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MANIFEST = ROOT / "data/raw/naip_tiles_pc_4band_full/manifest.json"
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


def download_tile(site: dict, out_path: Path, session: requests.Session | None = None) -> dict | None:
    """Download a 2km x 2km, 1m, 4-band tile centred on site lat/lon.

    Returns the site dict with tile_path/bbox/naip_item_id/naip_datetime
    filled in, or None if no imagery was found.
    """
    session = session or requests.Session()
    item = find_naip_item(site["lon"], site["lat"], session)
    if item is None:
        print(f"  no NAIP item found for {site['farm_name']}")
        return None

    href = item["assets"]["image"]["href"]
    bbox = BBox.from_point(lon=site["lon"], lat=site["lat"], buffer_km=BUFFER_KM)

    with rasterio.open(href) as src:
        left, bottom, right, top = transform_bounds(
            "EPSG:4326", src.crs, bbox.west, bbox.south, bbox.east, bbox.north
        )
        window = from_bounds(left, bottom, right, top, transform=src.transform)
        if window.width < 10 or window.height < 10:
            print(f"  empty/tiny window for {site['farm_name']}")
            return None

        scale = src.res[0] / TARGET_RESOLUTION_M
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
            height=data.shape[1], width=data.shape[2], transform=out_transform,
            driver="GTiff", compress="lzw", predictor=2,
            tiled=True, blockxsize=256, blockysize=256,
        )
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(data)

    return {
        **site,
        "tile_path": str(out_path.relative_to(ROOT)) if out_path.is_relative_to(ROOT) else str(out_path),
        "bbox": bbox.as_tuple,
        "naip_item_id": item["id"],
        "naip_datetime": item["properties"].get("datetime"),
    }


def read_tile(path: Path) -> tuple[np.ndarray, dict]:
    """Read a tile as HWC uint8 (R, G, B, NIR) plus its georeferencing."""
    with rasterio.open(path) as src:
        img = np.moveaxis(src.read(), 0, -1)
        meta = {"crs": src.crs, "transform": src.transform,
                "bounds": src.bounds, "res_m": src.res[0]}
    return img, meta
