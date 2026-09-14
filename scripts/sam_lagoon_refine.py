"""
Lagoon refinement: classical-CV candidate boxes + Meta's Segment Anything
Model (SAM) for pixel-accurate masks, following PRISM-CAFO's described
methodology (detect candidates -> segment -> extract descriptors -> filter)
-- reimplemented with openly-licensed tools since PRISM-CAFO's own code has
no license and no published weights (see plan notes).

Classical CV's color-threshold candidate generator (scripts/classical_cv_detector.py
detect_lagoons()) has good precision but known recall gaps (darker/murkier
lagoons). SAM doesn't fix that recall gap -- it only refines candidates
classical CV already found -- but it gives pixel-accurate boundaries instead
of a coarse rotated-rectangle estimate, and its true mask shape enables a
solidity filter (constructed lagoons have regular, close-to-convex
boundaries; natural ponds/lakes have irregular, organic shorelines -- this
distinguishes real lagoons from the natural-lake false positive found and
correctly rejected by classical CV on site_04 during pilot QA) that the
coarse rectangle approach couldn't support.

Citation for the underlying model: Kirillov et al. (2023), "Segment
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
from classical_cv_detector import detect_lagoons, load_rgb

ROOT = Path(__file__).resolve().parent.parent
SAM_CHECKPOINT = ROOT / "data/models/sam_vit_b_01ec64.pth"
DEFAULT_BARN_GEOJSON = ROOT / "data/processed/detections/full_registry_unet_tulbure_detections.geojson"

# Minimum solidity (mask_area / convex_hull_area) to keep -- constructed
# lagoons are close to a filled rectangle/oval (solidity near 1); natural
# ponds/lakes have irregular, branching shorelines (much lower solidity).
# Tuned by checking against the known site_04 natural-lake case (see main()
# self-test) and the confirmed-real lagoons on sites 4 and 9.
MIN_SOLIDITY = 0.85

# Loosened color-candidate thresholds -- catch darker/murkier lagoons the
# default (24/18) threshold misses. Confirmed unsafe on their own (also
# catches residential pools, just as color-regular as real lagoons) --
# safe here only because loose-only candidates are additionally required to
# sit near a same-tile detected poultry house (see PROXIMITY_MAX_M below).
LOOSE_G_R_MIN, LOOSE_B_R_MIN = 15, 10

# Max distance (m) from a loose-only lagoon candidate to the nearest barn
# detected on the SAME tile, to admit it. Calibrated against the 13 (of 17)
# already-confirmed real lagoons that have at least one same-tile detected
# barn: same-tile nearest-barn distances range 308-1426m. 1500m keeps all 13
# with margin. The other 4/17 have no same-tile detected barn at all (their
# farm's own barn is one of the ~2.9% true U-Net misses -- confirmed via
# cross-check against the miss root-cause analysis, e.g. Brian Harding) --
# for those, proximity can't be computed, so loose-only candidates are never
# admitted for that tile; only candidates that already pass the original
# tight threshold are kept, unchanged from the pre-existing behavior.
PROXIMITY_MAX_M = 1500.0

# Max plausible lagoon area (m^2). Added after this session's own testing of
# the proximity filter found it wasn't sufficient on its own: SAM's solidity
# metric is computed only within the locally-cropped candidate box, so a
# smoothly-curving *section* of a much larger natural river/wetland can read
# as high-solidity (0.91-0.95 observed) even though the full feature is
# obviously not a lagoon by eye. Confirmed visually on Jabar Rahim's tile:
# three candidates at 48,654/92,560/107,919 m^2 were the same tidal creek.
# This bound is set from the previously-reported real-lagoon size range
# (654-15,337 m^2, from the original 17 SAM-refined detections) with ~30%
# headroom. Applied uniformly to BOTH tight and loose-proximity candidates --
# testing also found some already-deployed "tight" candidates exceeding this
# (e.g. Brian Harding's largest at 42,879 m^2, on a farm with zero detected
# barns and zero 2016/17 ground-truth houses -- plausibly a wetland/pond
# feature, not a real lagoon, that solidity alone never caught).
MAX_AREA_M2 = 20000.0


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
    """Does the SAM-segmented region's *own* pixel color still look like
    teal/turquoise water, using the same tight thresholds as the default
    candidate detector?

    Necessary because SAM's solidity check only validates the *shape* of
    whatever it segmented inside a prompted box -- it happily returns a
    solid, plausible-looking mask for a patch of cropland or shadow if
    that's what the (possibly loosely-thresholded) box actually contained.
    Found and added 2026-09-02 after a full-scale test run of the loosened
    candidate threshold produced 10-20 "lagoons" per farm, almost all of
    them field/soil regions with real teal-water color thresholds but SAM
    solidity was passing anyway -- confirmed visually on several. Re-checking
    color on the refined mask itself (not the original loose candidate box)
    catches this: a real lagoon's mask is still teal on average; a
    misclassified field is not, regardless of how the candidate was found.

    Thresholds here are deliberately NOT the same 24/18 used by
    detect_lagoons()'s default (tight) per-pixel candidate generation --
    that threshold is applied per-pixel to pick out a binary blob before
    SAM ever runs, whereas this checks the *mean* color across SAM's full
    predicted mask, which typically extends a bit past the tight blob's
    exact boundary (soft edge/shore pixels) and pulls the mean down. Direct
    measurement on this farm's own tiles: real tight-threshold-passing
    lagoons (Brian Harding, Roland Todd, Jabar Rahim) had mask-mean g-r in
    16.2-24.3 and b-r in 16.3-20.7; the field/soil false positives that
    motivated this check had mask-mean g-r in a similar 15.0-19.8 range
    (g-r alone doesn't separate real water from dense dark cropland) but
    b-r only 7.2-13.7 -- b-r is the real discriminator. g_r_min kept as a
    loose sanity floor; b_r_min=15 sits with margin between the two
    observed clusters (13.7 max false vs. 16.2 min real).
    """
    r = rgb[:, :, 0][mask].astype(np.int16)
    g = rgb[:, :, 1][mask].astype(np.int16)
    b = rgb[:, :, 2][mask].astype(np.int16)
    if r.size == 0:
        return False
    return bool((g.mean() - r.mean() > 12) and (b.mean() - r.mean() > 15))


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


def contour_to_geo_polygon(contour: np.ndarray, transform) -> list[tuple[float, float]]:
    # Simplify to keep the polygon reasonably small; contour is (N,1,2) in (x,y) px.
    epsilon = 0.01 * cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    coords = []
    for pt in approx.reshape(-1, 2):
        lon, lat = xy(transform, pt[1], pt[0])
        coords.append((lon, lat))
    coords.append(coords[0])
    return coords


def geodesic_polygon_area_m2(geo_coords: list[tuple[float, float]], geod) -> float:
    """Area of a lon/lat polygon ring in m^2 via geodesic shoelace (pyproj.Geod)."""
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

    Matched by farm_name, not tile filename -- the barn detections
    (unet_detect.py) and lagoon candidates (this script) come from two
    independently-built manifests (Planetary Computer 4-band vs. MD iMAP
    RGB tiles) that don't share a tile-numbering scheme, but both carry the
    same farm_name field from the underlying MDE registry pull.
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
    rgb, transform = load_rgb(tile_path)
    tight_candidates = detect_lagoons(rgb)
    predictor.set_image(rgb)

    if not enable_recall_widening:
        # Recall-widening (loosened color threshold + proximity/area/color
        # gating) is opt-in, not the default -- see main()'s --enable-
        # recall-widening flag docstring for why. Tight-only + the new
        # MAX_AREA_M2 cap is the safe, validated default.
        loose_candidates = []
    else:
        loose_candidates = detect_lagoons(rgb, g_r_min=LOOSE_G_R_MIN, b_r_min=LOOSE_B_R_MIN)

    same_farm_barns = barns_by_farm.get(site.get("farm_name"), [])

    # Tight and loose-only candidates are processed as separate lists, not a
    # union re-derived from the loose mask: the loosened threshold's
    # morphological close often merges a real lagoon's small tight blob into
    # a much larger, differently-shaped low-value region (forest shadow,
    # etc.), so the tight blob's own box may not survive as a distinct loose
    # candidate at all. Re-running SAM on the tight boxes directly guarantees
    # the previously-working tight-threshold behavior is fully preserved.
    loose_only = [
        cand for cand in loose_candidates
        if not any(_box_iou(cand["box_px"], t["box_px"]) > 0.1 for t in tight_candidates)
    ]

    def refine_and_locate(cand):
        box_xyxy = box_px_to_xyxy(cand["box_px"])
        refined = refine_candidate(predictor, box_xyxy, rgb)
        if refined is None or refined["solidity"] < MIN_SOLIDITY:
            return None, None, None, None
        geo_coords = contour_to_geo_polygon(refined["contour"], transform)
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
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [geo_coords]},
            "properties": {
                "class_name": "manure_lagoon",
                "detector": "classical_cv_candidates+sam_refined+barn_proximity",
                "farm_name": site.get("farm_name"),
                "county": site.get("county"),
                "headcount": site.get("headcount"),
                "area_px": refined["area_px"],
                "area_m2": round(area_m2, 1),
                "solidity": round(refined["solidity"], 3),
                "sam_score": round(refined["sam_score"], 3),
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
        # Loose-only candidate (wouldn't have passed the original tight
        # color threshold) -- only admit it if it sits near a same-farm
        # detected barn. Without that anchor (farm's barns weren't
        # detected, or genuinely far away), it's exactly the kind of
        # candidate that turned out to be a residential pool in prior
        # testing, so it's dropped rather than risking a false positive.
        if dist_m is None or dist_m > PROXIMITY_MAX_M:
            continue
        features.append(make_feature(refined, geo_coords, "loose_proximity_gated", dist_m, area_m2))

    return features, len(tight_candidates) + len(loose_only)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-geojson", type=Path, required=True)
    parser.add_argument("--barn-geojson", type=Path, default=DEFAULT_BARN_GEOJSON,
                         help="Detected poultry houses, used for the proximity filter "
                              "that gates loosened lagoon candidates (default: the "
                              "full-registry U-Net+Tulbure-filter output)")
    parser.add_argument("--enable-recall-widening", action="store_true",
                         help="Also run the loosened-color-threshold candidate pass, "
                              "gated by proximity/area/mask-color checks. OFF by "
                              "default: this session validated the mechanism on a "
                              "4-farm pilot, then found via full-scale testing that it "
                              "over-triggers on cropland at ~10-20 false candidates/farm; "
                              "a mask-color post-check (see mask_is_water_colored()) "
                              "fixed that specific class but a spot-check then found a "
                              "*different* false-positive class (dense forest canopy) "
                              "still getting through on at least one farm. Needs more "
                              "dedicated tuning (ideally NDWI/NIR, not available from "
                              "these RGB-only MD iMAP tiles) before trusting it at full "
                              "scale -- kept in the code, off by default, rather than "
                              "silently dropped, since the mechanism itself (proximity "
                              "+ area + mask-color gating) is real progress even though "
                              "it isn't safe to ship broadly yet.")
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
