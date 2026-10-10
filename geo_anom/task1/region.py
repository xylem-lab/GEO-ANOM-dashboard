"""
Area-wide runs: map every building in a county, not only around registry farms.

    county_boundary("Somerset")  -> county polygon (WGS84), from the Census
                                    cartographic boundary file, cached in
                                    data/reference/
    grid_sites(polygon, name)    -> one "site" per 2 km tile, overlapping so a
                                    building up to OVERLAP_M long is whole in at
                                    least one tile; same dict shape as manifest
                                    entries, so detect/pipeline work unchanged
    download_many(sites)         -> parallel tile download, skipping tiles on disk

Tiles are the same 2 km x 2 km, 1 m, 4-band NAIP mosaics as the registry run
(tiles.download_tile), just centred on a regular grid instead of permit points.
"""

from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import geopandas as gpd
import numpy as np
import requests
from shapely.geometry import Point, box

from geo_anom.task1 import tiles
from geo_anom.task1.tiles import ROOT

UTM = "EPSG:32618"
MD_FIPS = "24"
COUNTY_ZIP_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
COUNTY_CACHE = ROOT / "data/reference/md_counties_cb_2023_500k.geojson"

TILE_M = 2000.0      # tiles.download_tile cuts 2 km x 2 km (BUFFER_KM = 1.0)
OVERLAP_M = 250.0    # longest poultry houses seen are ~300 m; 250 covers nearly all
STRIDE_M = TILE_M - OVERLAP_M


def md_counties(refresh: bool = False) -> gpd.GeoDataFrame:
    """All Maryland counties (incl. Baltimore City), WGS84, cached locally.

    Census 'cartographic boundary' polygons are clipped to the shoreline, so
    open water (the Bay, Tangier Sound) mostly falls outside them.
    """
    if COUNTY_CACHE.exists() and not refresh:
        return gpd.read_file(COUNTY_CACHE)
    resp = requests.get(COUNTY_ZIP_URL, timeout=120)
    resp.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    shp = next(n for n in z.namelist() if n.endswith(".shp"))
    tmp = COUNTY_CACHE.parent / "_cb_county_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    z.extractall(tmp)
    us = gpd.read_file(tmp / shp)
    md = us[us["STATEFP"] == MD_FIPS][["NAME", "NAMELSAD", "GEOID", "ALAND", "AWATER", "geometry"]]
    md = md.to_crs("EPSG:4326").sort_values("NAME").reset_index(drop=True)
    md.to_file(COUNTY_CACHE, driver="GeoJSON")
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    return md


def county_boundary(name: str) -> gpd.GeoDataFrame:
    """One county by name, e.g. "Somerset", "Queen Anne's", "Baltimore city"."""
    md = md_counties()
    hit = md[md["NAME"].str.lower() == name.lower()]
    if len(hit) != 1:
        hit = md[md["NAMELSAD"].str.lower() == name.lower()]
    if len(hit) != 1:
        raise ValueError(f"county {name!r} not found; options: {sorted(md['NAME'])}")
    return hit.reset_index(drop=True)


def grid_sites(area: gpd.GeoDataFrame, name: str, min_land_share: float = 0.05,
               tile_dir: Path | None = None) -> list[dict]:
    """Tile centres on a regular grid over `area`, as site dicts.

    Keeps a tile if at least `min_land_share` of it is inside the area.
    Each site gets a stable id "r<row>_c<col>" and a tile_path under
    data/raw/naip_grid/<name>/.
    """
    slug = name.lower().replace(" ", "_").replace("'", "")
    tile_dir = tile_dir or ROOT / "data/raw/naip_grid" / slug
    geom = area.to_crs(UTM).unary_union
    x0, y0, x1, y1 = geom.bounds
    sites = []
    for r, cy in enumerate(np.arange(y1 - TILE_M / 2, y0 - TILE_M / 2, -STRIDE_M)):
        for c, cx in enumerate(np.arange(x0 + TILE_M / 2, x1 + TILE_M / 2, STRIDE_M)):
            sq = box(cx - TILE_M / 2, cy - TILE_M / 2, cx + TILE_M / 2, cy + TILE_M / 2)
            share = sq.intersection(geom).area / sq.area
            if share < min_land_share:
                continue
            p = gpd.GeoSeries([Point(cx, cy)], crs=UTM).to_crs("EPSG:4326").iloc[0]
            tid = f"r{r:03d}_c{c:03d}"
            path = tile_dir / f"{tid}.tif"
            sites.append({
                "farm_name": f"{name} grid {tid}",   # pipeline field name; here a tile id
                "grid_id": tid,
                "county": name,
                "animal_type": None,
                "headcount": None,
                "lat": round(p.y, 7),
                "lon": round(p.x, 7),
                "land_share": round(share, 3),
                "tile_path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            })
    return sites


def download_many(sites: list[dict], max_workers: int = 8, progress=None) -> list[dict]:
    """Download every missing tile in parallel; returns sites whose tile is on disk.

    Each tile goes to the site's own stored tile_path (never a path rebuilt
    from list order -- see the 2026-09 manifest-order bug in NEXT_SESSION.md).
    """
    def one(s):
        dest = tiles.tile_path(s)
        if dest.exists():
            return s, "cached"
        try:
            got = tiles.download_tile(s, dest, requests.Session())
            return (got or s), ("ok" if got else "no imagery")
        except Exception as e:  # network hiccups shouldn't kill a county run
            return s, f"error: {type(e).__name__}"

    done, status = [], {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(one, s) for s in sites]
        it = as_completed(futures)
        for f in (progress(it, total=len(futures)) if progress else it):
            s, st = f.result()
            status[st.split(":")[0]] = status.get(st.split(":")[0], 0) + 1
            if tiles.tile_path(s).exists():
                done.append(s)
    order = {s["tile_path"]: i for i, s in enumerate(sites)}
    done.sort(key=lambda s: order.get(s["tile_path"], 0))
    print("tiles:", status)
    return done
