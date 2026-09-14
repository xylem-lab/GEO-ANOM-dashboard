"""
Lagoon detection on Planetary Computer 4-band imagery.

Replaces sam_lagoon_refine.py's MD-iMAP-sourced candidate generation.
MD iMAP and Planetary Computer NAIP are two different imagery sources with
a real ~70-100m mutual georeferencing offset (confirmed by direct visual
overlay -- house polygons that land exactly on real buildings on the PC
tile are visibly offset on the MD iMAP tile for the same farm). Houses are
already detected from Planetary Computer imagery; lagoons were the one
piece still on MD iMAP, so every lagoon polygon inherited that offset
directly -- this is the "lagoon sitting on a field" bug found in Google
Earth. Moving lagoons onto the same PC source as houses puts both layers
on one trustworthy coordinate frame, with no fix needed beyond the source
swap itself.

The original plan for this rebuild was to make NDWI (McFeeters 1996,
(Green-NIR)/(Green+NIR)) the *primary* water-discrimination signal, on the
theory that a physical water-absorbs-NIR signal would be more robust to
the dense-forest-canopy false positive that kept defeating RGB color
thresholds (river -> pool -> canopy, across this project's history).
Tested directly against the correctly-scoped canopy false positives this
project has on file: NDWI ranges for real lagoons and canopy false
positives overlap on this imagery at this resolution -- no clean threshold
separates them. A real, honestly-reported negative result, not silently
dropped: NDWI is still computed here and reported per-candidate as a
diagnostic field (`ndwi_mean`), useful for a methods write-up and for
future work, but it does not gate anything. The actual filters doing the
work are the same ones already validated on MD iMAP in
sam_lagoon_refine.py (color/solidity/area/barn-proximity) -- ported here
unchanged, now running on the correctly-registered source.

Citation for the segmentation model: Kirillov et al. (2023), "Segment
Anything," Meta AI Research. Apache 2.0 license, no training required.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import rasterio
from rasterio.transform import xy
from segment_anything import sam_model_registry, SamPredictor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classical_cv_detector import detect_lagoons

ROOT = Path(__file__).resolve().parent.parent
SAM_CHECKPOINT = ROOT / "data/models/sam_vit_b_01ec64.pth"
DEFAULT_BARN_GEOJSON = ROOT / "data/processed/detections/full_registry_unet_tulbure_detections.geojson"

# MIN_SOLIDITY was recalibrated for this source (was 0.85 on MD iMAP) --
# see MASK_B_R_MIN below for why a straight source swap wasn't safe.
# 0.90 rejects the Chaudhry canopy-shadow false positive (measured
# solidity 0.861) while keeping all 3 real lagoons in the ~15-case test
# set (measured 0.943-0.960). Calibrated on n=6 candidates -- explicitly
# flagged for revalidation once the full 417-farm run's output gets the
# same individual audit the original lagoon review got; a threshold that
# looks clean on a handful of hand-picked cases has broken at full scale
# before in this project (the recall-widening color check, 2026-09-02).
MIN_SOLIDITY = 0.90

# mask_is_water_colored()'s b-r floor was recalibrated for this source.
# Direct measurement on the ~15-case test set, re-rendered from Planetary
# Computer tiles instead of MD iMAP: real lagoons measured b-r in
# 20.5-37.7; Brian Harding's two known-false natural-pond/canopy-shadow
# candidates (documented false positives on MD iMAP too, at a different
# threshold -- see sam_lagoon_refine.py) measured b-r 15.8-17.5 on this
# source. The old MD-iMAP-calibrated threshold (15) sits *inside* that
# false-positive cluster on PC imagery -- confirmed empirically while
# building this script, not assumed: the same numeric threshold does not
# transfer between two imagery sources with different color processing,
# even though the underlying physical color relationship (water pulls
# green/blue above red) is the same idea on both. 19 sits with margin
# between the two observed clusters on this source (17.5 max false vs.
# 20.5 min real). Note this does NOT fix every false-positive class on
# this source by itself -- the Chaudhry canopy-shadow candidate actually
# measured b-r=36.0 (higher than 2 of the 3 real lagoons), so color alone
# still can't separate it; MIN_SOLIDITY above is what catches that one.
# Also calibrated on n=6 -- same full-scale-revalidation caveat applies.
MASK_B_R_MIN = 19

LOOSE_G_R_MIN, LOOSE_B_R_MIN = 15, 10
PROXIMITY_MAX_M = 1500.0
MAX_AREA_M2 = 20000.0


def load_rgb_nir(tile_path: Path) -> tuple[np.ndarray, np.ndarray, object, object]:
    """Read a Planetary Computer 4-band (R,G,B,NIR) tile.

    RGB is used exactly as classical_cv_detector.load_rgb() would (bands
    1-3); NIR (band 4) is kept separately for the NDWI diagnostic only.
    Also returns the tile's CRS -- Planetary Computer tiles are in a
    projected UTM CRS (EPSG:26918), unlike the MD iMAP tiles this pipeline
    used before (natively EPSG:4326, i.e. the raster transform already
    yielded lon/lat directly). contour_to_geo_polygon() below needs the
    real CRS to reproject correctly regardless of source -- ported code
    that assumed transform output was already lon/lat silently returned
    NaN areas here otherwise (found and fixed while building this script:
    pyproj.Geod.polygon_area_perimeter() given raw UTM meter values that
    look like huge, invalid degree values returns NaN, not an error).
    """
    with rasterio.open(tile_path) as src:
        bands = src.read()
        transform = src.transform
        crs = src.crs
    rgb = np.moveaxis(bands[:3], 0, -1).astype(np.uint8)
    nir = bands[3].astype(np.float32)
    return rgb, nir, transform, crs


def ndwi_mean_for_mask(rgb: np.ndarray, nir: np.ndarray, mask: np.ndarray) -> float | None:
    """Mean NDWI = (Green-NIR)/(Green+NIR) over a SAM mask's pixels.

    Diagnostic only -- see module docstring for why this doesn't gate
    anything (real lagoons and dense-canopy false positives overlap in
    NDWI on this imagery). Reported so the methods write-up has real
    numbers for that negative result instead of an anecdote.
    """
    green = rgb[:, :, 1][mask].astype(np.float32)
    nir_vals = nir[mask]
    if green.size == 0:
        return None
    denom = green + nir_vals
    valid = denom != 0
    if not valid.any():
        return None
    ndwi = (green[valid] - nir_vals[valid]) / denom[valid]
    return float(ndwi.mean())


def get_device():
    import torch
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_sam(checkpoint: Path = SAM_CHECKPOINT):
    sam = sam_model_registry["vit_b"](checkpoint=str(checkpoint))
    sam.to(device=get_device())
    return SamPredictor(sam)


def box_px_to_xyxy(box_px: np.ndarray) -> list[int]:
    x0, y0 = box_px[:, 0].min(), box_px[:, 1].min()
    x1, y1 = box_px[:, 0].max(), box_px[:, 1].max()
    return [int(x0), int(y0), int(x1), int(y1)]


def mask_is_water_colored(rgb: np.ndarray, mask: np.ndarray) -> bool:
    """Same mechanism as sam_lagoon_refine.py (check the SAM mask's own
    mean color, not the original candidate box) but with a b-r floor
    recalibrated for Planetary Computer's color rendering -- see
    MASK_B_R_MIN above for the measured values driving this."""
    r = rgb[:, :, 0][mask].astype(np.int16)
    g = rgb[:, :, 1][mask].astype(np.int16)
    b = rgb[:, :, 2][mask].astype(np.int16)
    if r.size == 0:
        return False
    return bool((g.mean() - r.mean() > 12) and (b.mean() - r.mean() > MASK_B_R_MIN))


def refine_candidate(predictor: SamPredictor, box_xyxy: list[int], rgb: np.ndarray) -> dict | None:
    """Prompt SAM with a candidate's bounding box; return mask + shape stats."""
    masks, scores, _ = predictor.predict(
        box=np.array(box_xyxy), multimask_output=False
    )
    mask = masks[0]
    area_px = int(mask.sum())
    if area_px < 50:
        return None
    if not mask_is_water_colored(rgb, mask):
        return None

    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    contour_area = cv2.contourArea(largest)
    hull = cv2.convexHull(largest)
    hull_area = cv2.contourArea(hull)
    solidity = contour_area / hull_area if hull_area > 0 else 0.0

    return {
        "mask": mask,
        "contour": largest,
        "area_px": area_px,
        "solidity": solidity,
        "sam_score": float(scores[0]),
    }


def contour_to_geo_polygon(contour: np.ndarray, transform, crs, to_wgs84) -> list[tuple[float, float]]:
    """Pixel contour -> lon/lat ring, reprojecting from the tile's native
    CRS. `to_wgs84` is a pyproj.Transformer(crs -> EPSG:4326); passed in
    (not constructed here) so it's built once per tile, not once per
    candidate polygon point."""
    epsilon = 0.01 * cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    coords = []
    for pt in approx.reshape(-1, 2):
        native_x, native_y = xy(transform, pt[1], pt[0])
        lon, lat = to_wgs84.transform(native_x, native_y)
        coords.append((lon, lat))
    coords.append(coords[0])
    return coords


def geodesic_polygon_area_m2(geo_coords: list[tuple[float, float]], geod) -> float:
    lons = [c[0] for c in geo_coords]
    lats = [c[1] for c in geo_coords]
    area, _ = geod.polygon_area_perimeter(lons, lats)
    return abs(area)


def _box_iou(box_a: np.ndarray, box_b: np.ndarray) -> float:
    from shapely.geometry import box as shapely_box
    a = shapely_box(*box_px_to_xyxy(box_a))
    b = shapely_box(*box_px_to_xyxy(box_b))
    inter = a.intersection(b).area
    if inter == 0:
        return 0.0
    return inter / a.union(b).area


def load_barns_by_farm(barn_geojson: Path | None) -> dict[str, list[tuple[float, float]]]:
    """farm_name -> list of (lon, lat) detected-poultry-house centroids.

    Barn detections and lagoon candidates now both come from Planetary
    Computer imagery (unlike the pre-rebuild MD-iMAP-sourced lagoon
    pipeline), so this join is on solid, co-registered ground -- still
    keyed by farm_name rather than tile filename since the two manifests
    are still built independently and don't share a tile-numbering scheme.
    """
    if barn_geojson is None or not barn_geojson.exists():
        return {}
    data = json.loads(barn_geojson.read_text())
    by_farm: dict[str, list[tuple[float, float]]] = {}
    for feat in data["features"]:
        name = feat["properties"].get("farm_name")
        if not name:
            continue
        coords = feat["geometry"]["coordinates"][0]
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        by_farm.setdefault(name, []).append((cx, cy))
    return by_farm


def process_tile(
    predictor: SamPredictor,
    tile_path: Path,
    site: dict,
    barns_by_farm: dict[str, list[tuple[float, float]]],
    geod,
    enable_recall_widening: bool = False,
) -> tuple[list[dict], int]:
    from pyproj import Transformer

    rgb, nir, transform, crs = load_rgb_nir(tile_path)
    to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    tight_candidates = detect_lagoons(rgb)
    predictor.set_image(rgb)

    if not enable_recall_widening:
        loose_candidates = []
    else:
        loose_candidates = detect_lagoons(rgb, g_r_min=LOOSE_G_R_MIN, b_r_min=LOOSE_B_R_MIN)

    same_farm_barns = barns_by_farm.get(site.get("farm_name"), [])

    loose_only = [
        cand for cand in loose_candidates
        if not any(_box_iou(cand["box_px"], t["box_px"]) > 0.1 for t in tight_candidates)
    ]

    def refine_and_locate(cand):
        box_xyxy = box_px_to_xyxy(cand["box_px"])
        refined = refine_candidate(predictor, box_xyxy, rgb)
        if refined is None or refined["solidity"] < MIN_SOLIDITY:
            return None, None, None, None
        geo_coords = contour_to_geo_polygon(refined["contour"], transform, crs, to_wgs84)
        area_m2 = geodesic_polygon_area_m2(geo_coords, geod)
        if area_m2 > MAX_AREA_M2:
            return None, None, None, None
        cand_lon = sum(c[0] for c in geo_coords[:-1]) / (len(geo_coords) - 1)
        cand_lat = sum(c[1] for c in geo_coords[:-1]) / (len(geo_coords) - 1)
        return refined, geo_coords, (cand_lon, cand_lat), area_m2

    def barn_distance_m(cand_lon, cand_lat):
        if not same_farm_barns:
            return None
        _, _, dists = geod.inv(
            [cand_lon] * len(same_farm_barns), [cand_lat] * len(same_farm_barns),
            [b[0] for b in same_farm_barns], [b[1] for b in same_farm_barns],
        )
        return min(dists)

    def make_feature(refined, geo_coords, source, dist_m, area_m2):
        ndwi_mean = ndwi_mean_for_mask(rgb, nir, refined["mask"])
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [geo_coords]},
            "properties": {
                "class_name": "manure_lagoon",
                "detector": "classical_cv_candidates+sam_refined+barn_proximity+pc_source",
                "farm_name": site.get("farm_name"),
                "county": site.get("county"),
                "headcount": site.get("headcount"),
                "area_px": refined["area_px"],
                "area_m2": round(area_m2, 1),
                "solidity": round(refined["solidity"], 3),
                "sam_score": round(refined["sam_score"], 3),
                "ndwi_mean": round(ndwi_mean, 4) if ndwi_mean is not None else None,
                "tile": tile_path.name,
                "candidate_source": source,
                "distance_to_barn_m": round(dist_m, 1) if dist_m is not None else None,
            },
        }

    features = []
    for cand in tight_candidates:
        refined, geo_coords, latlon, area_m2 = refine_and_locate(cand)
        if refined is None:
            continue
        dist_m = barn_distance_m(*latlon)
        features.append(make_feature(refined, geo_coords, "tight", dist_m, area_m2))

    for cand in loose_only:
        refined, geo_coords, latlon, area_m2 = refine_and_locate(cand)
        if refined is None:
            continue
        dist_m = barn_distance_m(*latlon)
        if dist_m is None or dist_m > PROXIMITY_MAX_M:
            continue
        features.append(make_feature(refined, geo_coords, "loose_proximity_gated", dist_m, area_m2))

    return features, len(tight_candidates) + len(loose_only)


def main():
    parser = argparse.ArgumentParser(
        description="Lagoon detection on Planetary Computer 4-band imagery "
                    "(fixes the MD-iMAP registration bug; NDWI reported as "
                    "a diagnostic, not a gate -- see module docstring)."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-geojson", type=Path, required=True)
    parser.add_argument("--barn-geojson", type=Path, default=DEFAULT_BARN_GEOJSON,
                         help="Detected poultry houses, used for the proximity filter "
                              "that gates loosened lagoon candidates (default: the "
                              "full-registry U-Net+Tulbure-filter output, already on "
                              "Planetary Computer imagery -- same source as this script).")
    parser.add_argument("--enable-recall-widening", action="store_true",
                         help="Also run the loosened-color-threshold candidate pass, "
                              "gated by proximity/area/mask-color checks. OFF by "
                              "default -- unchanged from sam_lagoon_refine.py: full-scale "
                              "testing found this still lets dense forest canopy through "
                              "on at least one farm even after the mask-color fix, and "
                              "NDWI (tested as the fix for exactly this) doesn't cleanly "
                              "separate canopy from real lagoons on this imagery either. "
                              "Kept in the code, off by default, rather than silently "
                              "dropped.")
    args = parser.parse_args()

    from pyproj import Geod
    geod = Geod(ellps="WGS84")

    manifest = json.loads(args.manifest.read_text())
    barns_by_farm = load_barns_by_farm(args.barn_geojson)
    print(f"Loaded barn detections for {len(barns_by_farm)} farms from {args.barn_geojson}")
    predictor = load_sam()
    print(f"SAM loaded on device={get_device()}")

    all_features = []
    for i, site in enumerate(manifest):
        tile_path = Path(site["tile_path"])
        features, n_candidates = process_tile(
            predictor, tile_path, site, barns_by_farm, geod,
            enable_recall_widening=args.enable_recall_widening,
        )
        print(f"[{i}] {site['farm_name']:<45} candidates={n_candidates:<3} kept={len(features)}")
        all_features.extend(features)

    args.out_geojson.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_geojson, "w") as f:
        json.dump({"type": "FeatureCollection", "features": all_features}, f, indent=2)

    print(f"\nTotal: {len(all_features)} SAM-refined lagoons across {len(manifest)} tiles")
    print(f"Saved -> {args.out_geojson}")


if __name__ == "__main__":
    main()
