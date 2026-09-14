"""
Classical CV detector for AFO poultry houses and manure lagoons.

Zero-shot YOLO-World found nothing on any of our 10 test tiles, despite
poultry houses being clearly visible in every one. Since both feature
types have very distinctive, consistent visual signatures --
poultry houses: long, bright, elongated rectangular roofs;
manure lagoons: teal/turquoise rectangular water --
this tries plain color + shape filtering instead of a learned model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import rasterio
from rasterio.transform import xy

ROOT = Path(__file__).resolve().parent.parent
TILE_DIR = ROOT / "data/raw/naip_tiles_top10"
MANIFEST_PATH = TILE_DIR / "manifest.json"
OUT_DIR = ROOT / "docs/imagery_experiment_assets"
OUT_GEOJSON = ROOT / "data/processed/detections/top10_classical_cv_detections.geojson"


def load_rgb(tile_path: Path) -> tuple[np.ndarray, object]:
    with rasterio.open(tile_path) as src:
        bands = src.read()
        transform = src.transform
    rgb = np.moveaxis(bands[:3], 0, -1).astype(np.uint8)
    return rgb, transform


def detect_poultry_houses(rgb: np.ndarray) -> list[dict]:
    """Bright, elongated rectangular roofs (broiler houses)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)

    # Bright, low-saturation (white/light-gray metal roofs). Roof surfaces show
    # alternating bright/shadowed ridge stripes, so only a light morphological
    # close is used -- enough to bridge a single roof's stripes, not enough to
    # fuse adjacent houses together (tested: k=9 over-merges whole clusters).
    mask = ((v > 140) & (s < 60)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    # Open breaks incidental thin bridges between adjacent houses that close()
    # leaves connected -- without it, neighboring roofs fuse into one blob
    # that fails the aspect-ratio filter below.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    results = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 150 or area > 4000:
            continue
        rect = cv2.minAreaRect(c)  # ((cx,cy),(w,h),angle)
        (w, h_) = rect[1]
        if min(w, h_) < 1:
            continue
        long_side, short_side = max(w, h_), max(min(w, h_), 1)
        aspect = long_side / short_side
        if aspect < 2.5:  # poultry houses are long and narrow
            continue
        if long_side < 25 or long_side > 300:
            continue
        box = cv2.boxPoints(rect)
        results.append({"class_name": "poultry_house", "box_px": box, "area_px": area, "aspect": aspect})
    # A single roof often shows up as 2 parallel stripe-contours (bright slope +
    # shadowed ridge); merge only very tight pairs (<12px centroid distance) so
    # those collapse into 1 box without chain-merging whole rows together.
    #
    # Tried: dropping boxes with no other house-box within 150px, on the
    # theory that farm roads (site 6's known FP) are isolated while real
    # houses cluster in rows. Measured against all 10 tiles: it cut the
    # true-positive count from 122 to 106 (-16), because several real
    # AFOs have a single isolated house with no other structure nearby
    # (confirmed visually on site 4 -- 3 of the "isolated" boxes it would
    # drop sit right next to a farmstead driveway, not in open field like
    # the site-6 road). Also tried a minimum-width cutoff instead (the
    # site-6 road's 6.4px short side looked narrower than real houses at
    # first) -- but several confirmed-real houses on other tiles are just
    # as narrow (6.1-7.0px), so width doesn't separate them either.
    # Neither is a clean fix without hand-labeled ground truth to tune
    # against, so left as-is: the road false-positive is a known,
    # documented limitation of color+shape-only detection, not something
    # to "fix" by trading away real recall.
    return merge_nearby_boxes(results, dist_thresh=12.0)


def merge_nearby_boxes(dets: list[dict], dist_thresh: float = 10.0) -> list[dict]:
    """Merge multiple stripe-detections that belong to the same roof (union-find on centroid distance)."""
    n = len(dets)
    if n == 0:
        return dets
    centroids = [d["box_px"].mean(axis=0) for d in dets]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if np.linalg.norm(centroids[i] - centroids[j]) < dist_thresh:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    merged = []
    for idxs in groups.values():
        pts = np.concatenate([dets[i]["box_px"] for i in idxs], axis=0).astype(np.float32)
        rect = cv2.minAreaRect(pts)
        box = cv2.boxPoints(rect)
        area = sum(dets[i]["area_px"] for i in idxs)
        merged.append({"class_name": "poultry_house", "box_px": box, "area_px": area, "aspect": None})
    return merged


def detect_lagoons(rgb: np.ndarray, g_r_min: int = 24, b_r_min: int = 18) -> list[dict]:
    """Teal/turquoise rectangular manure lagoons.

    Plain HSV hue thresholding false-positives heavily on dark forest-shadow
    pixels (similar hue, low saturation). What actually distinguishes
    teal/turquoise water is the *relationship* between channels -- green and
    blue both pulled well above red -- which shadow doesn't share.

    g_r_min/b_r_min are exposed (not hardcoded) so callers can loosen them to
    catch darker/murkier lagoons missed at the default thresholds -- see
    sam_lagoon_refine.py's proximity-to-barn filter, which is what makes
    loosening these safe to use (it was previously found to also pick up
    residential swimming pools, which are just as color-regular as real
    lagoons; the default values here are unchanged and still the safe,
    tight setting for any caller that doesn't pass a proximity filter).
    """
    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)
    v = rgb.max(axis=2)

    mask = ((g - r > g_r_min) & (b - r > b_r_min) & (v > 80) & (v < 235)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    results = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 300 or area > 60000:
            continue
        rect = cv2.minAreaRect(c)
        w, h_ = rect[1]
        if min(w, h_) < 1:
            continue
        long_side, short_side = max(w, h_), max(min(w, h_), 1)
        if long_side / short_side > 5:  # excludes long thin field-edge slivers
            continue
        box = cv2.boxPoints(rect)
        results.append({"class_name": "manure_lagoon", "box_px": box, "area_px": area, "aspect": None})
    return results


def px_box_to_geo(box_px: np.ndarray, transform) -> list[tuple[float, float]]:
    coords = []
    for x_px, y_px in box_px:
        lon, lat = xy(transform, y_px, x_px)
        coords.append((lon, lat))
    coords.append(coords[0])
    return coords


def annotate(rgb: np.ndarray, houses: list[dict], lagoons: list[dict]) -> np.ndarray:
    out = rgb.copy()
    for det in houses:
        pts = det["box_px"].astype(int)
        cv2.drawContours(out, [pts], 0, (255, 60, 60), 3)
    for det in lagoons:
        pts = det["box_px"].astype(int)
        cv2.drawContours(out, [pts], 0, (255, 215, 0), 3)
    return out


def main():
    parser = argparse.ArgumentParser(description="Classical CV detector for AFO poultry houses and lagoons.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH,
                         help="Path to a tile manifest.json (default: top-10 pilot manifest)")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR,
                         help="Directory for annotated preview PNGs")
    parser.add_argument("--out-geojson", type=Path, default=OUT_GEOJSON,
                         help="Output detections GeoJSON path")
    parser.add_argument("--no-previews", action="store_true",
                         help="Skip writing annotated PNGs (faster for large runs)")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)

    all_features = []
    total_houses = 0
    total_lagoons = 0

    for i, site in enumerate(manifest):
        tile_path = Path(site["tile_path"])
        rgb, transform = load_rgb(tile_path)

        houses = detect_poultry_houses(rgb)
        lagoons = detect_lagoons(rgb)
        total_houses += len(houses)
        total_lagoons += len(lagoons)

        print(f"[{i}] {site['farm_name']:<45} houses={len(houses):<3} lagoons={len(lagoons)}")

        if not args.no_previews:
            annotated = annotate(rgb, houses, lagoons)
            from PIL import Image
            Image.fromarray(annotated).save(args.out_dir / f"cv_annotated_site_{i:04d}.png")

        for det in houses + lagoons:
            geo_coords = px_box_to_geo(det["box_px"], transform)
            all_features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [geo_coords]},
                "properties": {
                    "class_name": det["class_name"],
                    "detector": "classical_cv",
                    "farm_name": site["farm_name"],
                    "county": site["county"],
                    "headcount": site["headcount"],
                    "area_px": round(float(det["area_px"]), 1),
                    "tile": tile_path.name,
                },
            })

    args.out_geojson.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_geojson, "w") as f:
        json.dump({"type": "FeatureCollection", "features": all_features}, f, indent=2)

    print(f"\nTotal: {total_houses} poultry houses, {total_lagoons} lagoons across {len(manifest)} tiles")
    print(f"Saved -> {args.out_geojson}")
    if not args.no_previews:
        print(f"Annotated previews -> {args.out_dir}/cv_annotated_site_*.png")


if __name__ == "__main__":
    main()
