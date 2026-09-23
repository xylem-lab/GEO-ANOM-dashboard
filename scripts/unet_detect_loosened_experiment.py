"""
End-to-end poultry-barn detection: Robinson et al.'s U-Net (via
unet_inference.py) + Tulbure et al.'s (2024) published false-positive
filter, applied over a tile manifest (same manifest.json format used
throughout this project's acquisition scripts).

Filter thresholds are from Tulbure, Caineta et al. (2024), GeoHealth,
"Earth Observation Data to Support Environmental Justice: Linking
Non-Permitted Poultry Operations to Social Vulnerability Indices" --
tighter and literature-validated (54% overestimation reduction in NC)
versus Microsoft's own looser filter_polygon() in their repo.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform as shapely_transform

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unet_inference import load_model, run_inference_on_tile, mask_to_polygons

ROOT = Path(__file__).resolve().parent.parent

# Tulbure et al. 2024 filter thresholds (area/length/width/aspect ranges are
# derived from North Carolina broiler houses). Length/area upper bounds
# widened here after direct visual verification on our own pilot data: site 0
# (Minh Vinh, our single highest-headcount permit, 595,000 birds) has real,
# single-building houses ~265-278m long with no internal seam -- confirmed by
# eye on the segmentation mask, not a merged-blob artifact -- which NC's
# 200m cap would incorrectly zero out entirely. Width/aspect bounds are left
# at Tulbure's values since those weren't contradicted by anything observed.
# Lower bounds recalibrated 2026-09-02 against real ground truth (Soroka &
# Duren 2016/17 hand-labeled houses): raw model output matches ground truth
# almost exactly in aggregate (ratio 1.07), but the filter was keeping only
# ~63-69% of it uniformly across farm sizes -- confirmed the single biggest
# lever in the whole pipeline. Sampled 25 sites, found 10 reasonably-sized
# (>=60m, so not fragmentation noise) raw detections sitting within 20m of a
# real 2016/17 house that the filter was rejecting -- 9/10 failed on length
# alone (60-106m, all below the old 100m floor), confirming Tulbure's NC
# floor is too strict for smaller/older MD houses. Verified the one
# confirmed false positive (site-6 road, length=72.5m, width=6.4m) still
# fails independently on WIDTH (unchanged, 10.0m floor) and on AREA (approx
# 464 m^2, below the new 500 floor) even with the lower length bound, so
# this widening doesn't reopen that hole. ASPECT_MIN nudged down too (one
# real case, aspect=2.30, is a short/wide house Tulbure's NC-derived 3.4
# floor excludes).
# EXPERIMENTAL 2026-09-21: LENGTH_MIN_M and ASPECT_MIN loosened from the
# validated 55.0/2.5 to try to catch two real, plausible beef-barn shapes
# found on Dwight Brandenburg (length=52.5, aspect=2.25) and Panora Acres
# (length=44.0, aspect=2.06) via scripts/diagnose_species_filter.py -- both
# are ~700+ m^2, well-formed rectangular candidates, not fragmentation noise.
# This is a full-registry experimental run, NOT a replacement for
# scripts/unet_detect.py -- output must be diffed against the validated
# full_registry_unet_tulbure_detections.geojson and every newly-introduced
# detection (especially on poultry farms) audited before this threshold
# change is adopted for real.
AREA_MIN_M2, AREA_MAX_M2 = 500.0, 7500.0
LENGTH_MIN_M, LENGTH_MAX_M = 40.0, 300.0
WIDTH_MIN_M, WIDTH_MAX_M = 10.0, 30.0
ASPECT_MIN, ASPECT_MAX = 2.0, 18.0
MIN_DIST_TO_ROAD_M = 20.0


def polygon_geo_stats(poly) -> dict:
    """Area and long/short side from the minimum rotated rectangle.

    `poly` is in the tile's native CRS (UTM, from mask_to_polygons -- see
    unet_inference.run_inference_on_tile), which is already meters-based and
    accurate enough at this scale (~1-2km tiles) -- no geodesic math needed,
    and using it directly avoids feeding projected-CRS coordinates into
    lon/lat-expecting geodesic functions (a real bug from an earlier version
    of this script: pyproj.Geod.geometry_area_perimeter silently returns NaN
    when given UTM meters instead of degrees).
    """
    area_m2 = poly.area
    rect = poly.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)
    side_lengths = [
        math.hypot(coords[i + 1][0] - coords[i][0], coords[i + 1][1] - coords[i][1])
        for i in range(len(coords) - 1)
    ]
    long_side = max(side_lengths) if side_lengths else 0.0
    short_side = min(s for s in side_lengths if s > 1e-6) if any(s > 1e-6 for s in side_lengths) else 0.0
    return {"area_m2": area_m2, "long_side_m": long_side, "short_side_m": short_side}


def passes_tulbure_filter(stats: dict, dist_to_road_m: float | None) -> bool:
    area, length, width = stats["area_m2"], stats["long_side_m"], stats["short_side_m"]
    if width <= 0:
        return False
    aspect = length / width
    return all([
        AREA_MIN_M2 <= area <= AREA_MAX_M2,
        LENGTH_MIN_M <= length <= LENGTH_MAX_M,
        WIDTH_MIN_M <= width <= WIDTH_MAX_M,
        ASPECT_MIN <= aspect <= ASPECT_MAX,
        dist_to_road_m is None or dist_to_road_m >= MIN_DIST_TO_ROAD_M,
    ])


def load_road_union(tile_bbox: tuple, cache_dir: Path):
    """Load cached OSM through-roads for a tile's bbox (built during the
    road-mask experiment this session); returns a buffered union or None."""
    import requests
    from shapely.geometry import LineString
    from shapely.ops import unary_union as _union

    cache_dir.mkdir(parents=True, exist_ok=True)
    key = f"{tile_bbox[0]:.4f}_{tile_bbox[1]:.4f}_{tile_bbox[2]:.4f}_{tile_bbox[3]:.4f}.json"
    cache_file = cache_dir / key
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
    else:
        w, s, e, n = tile_bbox
        highway_filter = "motorway|trunk|primary|secondary|tertiary|unclassified|residential"
        query = f'[out:json][timeout:25];way["highway"~"^({highway_filter})$"]({s},{w},{n},{e});out geom;'
        session = requests.Session()
        session.headers.update({"User-Agent": "geo-anom-research/0.1 (educational, rate-limited)"})
        resp = session.post("https://overpass-api.de/api/interpreter", data={"data": query}, timeout=30)
        if resp.status_code != 200:
            return None
        data = resp.json()
        cache_file.write_text(json.dumps(data))

    lines = [
        LineString([(pt["lon"], pt["lat"]) for pt in el["geometry"]])
        for el in data.get("elements", [])
        if el.get("geometry") and len(el["geometry"]) >= 2
    ]
    if not lines:
        return None
    return _union(lines)


def distance_to_road_m(poly, road_union_native_crs) -> float | None:
    """poly and road_union must already be in the same (tile-native, meters) CRS."""
    if road_union_native_crs is None:
        return None
    return poly.centroid.distance(road_union_native_crs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-geojson", type=Path, required=True)
    parser.add_argument("--use-road-filter", action="store_true",
                         help="Apply the >=20m-from-road criterion (needs OSM Overpass access)")
    parser.add_argument("--osm-cache-dir", type=Path,
                         default=Path("/private/tmp/claude-501/-Users-umeshadari-XylemLab-GEO-ANOM/"
                                      "1ce2c901-9f1c-4914-90e7-46db6a433aed/scratchpad/osm_cache"))
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    model, device = load_model()
    print(f"Model loaded on device={device}")

    all_features = []
    for i, site in enumerate(manifest):
        import rasterio

        tile_path = Path(site["tile_path"])
        with rasterio.open(tile_path) as src:
            tile_crs = src.crs
        to_wgs84 = Transformer.from_crs(tile_crs, "EPSG:4326", always_xy=True).transform

        mask, transform = run_inference_on_tile(model, device, tile_path)
        raw_polys = mask_to_polygons(mask, transform)  # native (UTM) CRS

        road_union = None
        if args.use_road_filter and "bbox" in site:
            road_union_wgs84 = load_road_union(tuple(site["bbox"]), args.osm_cache_dir)
            if road_union_wgs84 is not None:
                to_native = Transformer.from_crs("EPSG:4326", tile_crs, always_xy=True).transform
                road_union = shapely_transform(to_native, road_union_wgs84)

        kept = []
        for poly in raw_polys:
            stats = polygon_geo_stats(poly)  # meters, in native UTM CRS
            dist = distance_to_road_m(poly, road_union) if args.use_road_filter else None
            if passes_tulbure_filter(stats, dist):
                kept.append((poly, stats, dist))

        print(f"[{i}] {site['farm_name']:<45} raw={len(raw_polys):<4} filtered={len(kept)}")

        for poly, stats, dist in kept:
            poly_wgs84 = shapely_transform(to_wgs84, poly)
            all_features.append({
                "type": "Feature",
                "geometry": mapping(poly_wgs84),
                "properties": {
                    "class_name": "poultry_house",
                    "detector": "unet_robinson2022_tulbure2024filter",
                    "farm_name": site["farm_name"],
                    "county": site.get("county"),
                    "headcount": site.get("headcount"),
                    "area_m2": round(stats["area_m2"], 1),
                    "length_m": round(stats["long_side_m"], 1),
                    "width_m": round(stats["short_side_m"], 1),
                    "distance_to_road_m": round(dist, 1) if dist is not None else None,
                    "tile": tile_path.name,
                },
            })

    args.out_geojson.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_geojson, "w") as f:
        json.dump({"type": "FeatureCollection", "features": all_features}, f, indent=2)

    print(f"\nTotal: {len(all_features)} filtered poultry houses across {len(manifest)} tiles")
    print(f"Saved -> {args.out_geojson}")


if __name__ == "__main__":
    main()
