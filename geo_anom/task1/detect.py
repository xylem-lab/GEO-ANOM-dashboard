"""
Building detection: Robinson et al.'s (2022) U-Net + Tulbure et al.'s (2024)
shape filter.

Model: our own thin wrapper around Microsoft's published architecture
(cafo/models.get_unet(), MIT-licensed) and checkpoint (Open Use of Data
Agreement v1.0), patched to run on CPU/MPS -- microsoft/poultry-cafos
hard-requires CUDA.
    Robinson, Chugg, Anderson & Ho (2022), "Mapping industrial poultry
    operations at scale with deep learning and aerial imagery," IEEE JSTARS.
    Training labels: Soroka & Duren (2020), USGS, doi:10.5066/P9MO25Z7.

Filter: Tulbure, Caineta et al. (2024), GeoHealth, "Earth Observation Data
to Support Environmental Justice: Linking Non-Permitted Poultry Operations
to Social Vulnerability Indices" -- tighter and literature-validated (54%
overestimation reduction in NC) versus Microsoft's own filter_polygon().

Pipeline per tile:
    read tile -> U-Net probabilities -> hard mask -> morphological close
    -> polygons (tile CRS, meters) -> shape stats -> filter -> WGS84 features
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import segmentation_models_pytorch as smp
import torch
import torch.nn.functional as F
from pyproj import Transformer
from rasterio.features import shapes as rio_shapes
from shapely.geometry import mapping
from shapely.geometry import shape as shapely_shape
from shapely.ops import transform as shapely_transform

from geo_anom.task1.species import species_group
from geo_anom.task1.tiles import ROOT, read_tile, tile_path

CHECKPOINT_PATH = ROOT / "data/models/train-all_unet_0.5_0.01_rotation_best-checkpoint.pt"
DETECTOR_NAME = "unet_robinson2022_tulbure2024filter"

CHIP_SIZE = 256
PADDING = 32
HALF_PADDING = PADDING // 2
CHIP_STRIDE = CHIP_SIZE - PADDING

# Morphological close before polygonizing. A single real house's mask is
# sometimes patchy along its length (confidence dips at roof ridge
# lines/equipment), so plain connected components split it into fragments
# each too short to pass the length filter (site_0082/Sheng Lin Farm: 6 clear
# houses split into 18 fragments, 0 passing). Kernel sizes tested against
# Sheng Lin and against Alan C. Eck Farm (9 correctly-separated real houses,
# the regression check): 11 recovers Sheng Lin's fragments with Eck still
# 9/9; 15+ starts merging Eck's houses (9->3->1->0). 11 is the largest kernel
# that helps without any observed regression.
CLOSE_KERNEL = 11

# --- Tulbure et al. 2024 filter thresholds -------------------------------
# NC-derived. Length/area upper bounds widened after visual verification:
# Minh Vinh (595,000 birds) has real single houses ~265-278m long with no
# internal seam, which NC's 200m cap would zero out entirely.
# Lower bounds recalibrated 2026-09-02 against Soroka & Duren 2016/17
# hand-labeled houses: raw model output matched ground truth in aggregate
# (ratio 1.07) but the filter kept only ~63-69% of it. Of 10 >=60m raw
# detections within 20m of a real house that the filter rejected, 9 failed on
# length alone (60-106m, below the old 100m floor). The one confirmed false
# positive (site-6 road, 72.5m x 6.4m) still fails on WIDTH and AREA.
# ASPECT_MIN nudged down for one real short/wide house (aspect 2.30).
# NOTE: these thresholds were calibrated on the same ground truth the R^2
# in docs/task1_metrics.md is reported against -- not a held-out number.
AREA_MIN_M2, AREA_MAX_M2 = 500.0, 7500.0
LENGTH_MIN_M, LENGTH_MAX_M = 55.0, 300.0
WIDTH_MIN_M, WIDTH_MAX_M = 10.0, 30.0
ASPECT_MIN, ASPECT_MAX = 2.5, 18.0
MIN_DIST_TO_ROAD_M = 20.0

# Species-scoped exception (2026-09-21). Loosening LENGTH_MIN_M/ASPECT_MIN
# globally to 40/2.0 caught real beef barns on 2 zero-detection farms
# (Dwight Brandenburg, Panora Acres -- docs/beef_filter_diagnosis.json) but
# also added 169 unverified poultry-farm detections. Scoped to beef only.
SPECIES_FILTER_OVERRIDES = {
    "cattle_includes_heifers": {"LENGTH_MIN_M": 40.0, "ASPECT_MIN": 2.0},
}


def filter_thresholds(animal_type: str | None = None) -> dict:
    """The thresholds that apply to one species, overrides included."""
    t = {
        "AREA_MIN_M2": AREA_MIN_M2, "AREA_MAX_M2": AREA_MAX_M2,
        "LENGTH_MIN_M": LENGTH_MIN_M, "LENGTH_MAX_M": LENGTH_MAX_M,
        "WIDTH_MIN_M": WIDTH_MIN_M, "WIDTH_MAX_M": WIDTH_MAX_M,
        "ASPECT_MIN": ASPECT_MIN, "ASPECT_MAX": ASPECT_MAX,
        "MIN_DIST_TO_ROAD_M": MIN_DIST_TO_ROAD_M,
    }
    t.update(SPECIES_FILTER_OVERRIDES.get(animal_type, {}))
    return t


# --- Model ---------------------------------------------------------------

def get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_model(checkpoint_path: Path = CHECKPOINT_PATH, device: torch.device | None = None):
    device = device or get_device()
    model = smp.Unet(
        encoder_name="resnet18",
        encoder_depth=3,
        encoder_weights=None,
        decoder_channels=(128, 64, 64),
        in_channels=4,
        classes=2,
    )
    ckpt = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(ckpt["model_checkpoint"])
    model = model.to(device)
    model.eval()
    return model, device


def chip_transform(chip: np.ndarray) -> torch.Tensor:
    """Matches cafo/utils.py's chip_transformer: HWC uint8 -> CHW float32 [0,1]."""
    chip = chip / 255.0
    chip = np.rollaxis(chip, 2, 0).astype(np.float32)
    return torch.from_numpy(chip)


def predict_class_scores(model, device: torch.device, img: np.ndarray) -> np.ndarray:
    """Blended softmax scores [2, H, W] (background, building) for a 4-band HWC image.

    Matches Microsoft's inference.py tiling: 256px chips, 32px overlap,
    edge-weighted blending.
    """
    if img.shape[2] != 4:
        raise ValueError(f"image has {img.shape[2]} bands, expected 4 (RGB+NIR)")
    height, width = img.shape[0], img.shape[1]

    output = np.zeros((2, height, width), dtype=np.float32)
    counts = np.zeros((height, width), dtype=np.float32)
    kernel = np.ones((CHIP_SIZE, CHIP_SIZE), dtype=np.float32)
    kernel[HALF_PADDING:-HALF_PADDING, HALF_PADDING:-HALF_PADDING] = 5

    ys = list(range(0, max(height - CHIP_SIZE, 0) + 1, CHIP_STRIDE))
    xs = list(range(0, max(width - CHIP_SIZE, 0) + 1, CHIP_STRIDE))
    if not ys or ys[-1] + CHIP_SIZE < height:
        ys.append(max(height - CHIP_SIZE, 0))
    if not xs or xs[-1] + CHIP_SIZE < width:
        xs.append(max(width - CHIP_SIZE, 0))

    with torch.no_grad():
        for y in ys:
            for x in xs:
                chip = img[y : y + CHIP_SIZE, x : x + CHIP_SIZE]
                ch, cw = chip.shape[0], chip.shape[1]
                if ch < CHIP_SIZE or cw < CHIP_SIZE:
                    padded = np.zeros((CHIP_SIZE, CHIP_SIZE, 4), dtype=chip.dtype)
                    padded[:ch, :cw] = chip
                    chip = padded

                tensor = chip_transform(chip).unsqueeze(0).to(device)
                pred = F.softmax(model(tensor), dim=1).cpu().numpy()[0]

                out_h, out_w = min(CHIP_SIZE, height - y), min(CHIP_SIZE, width - x)
                output[:, y : y + out_h, x : x + out_w] += (
                    pred[:, :out_h, :out_w] * kernel[:out_h, :out_w]
                )
                counts[y : y + out_h, x : x + out_w] += kernel[:out_h, :out_w]

    return output / np.maximum(counts, 1e-6)


def scores_to_mask(scores: np.ndarray) -> np.ndarray:
    """Hard building mask = argmax over the 2 classes (ties -> background)."""
    return scores.argmax(axis=0).astype(np.uint8)


def mask_to_polygons(mask: np.ndarray, transform, close_kernel: int = CLOSE_KERNEL) -> list:
    """Polygonize a binary mask into tile-CRS (UTM, meters) polygons."""
    if close_kernel > 1:
        mask = cv2.morphologyEx(
            mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((close_kernel, close_kernel), np.uint8)
        )
    return [
        shapely_shape(geom)
        for geom, value in rio_shapes(mask, mask=mask.astype(bool), transform=transform)
        if value == 1
    ]


# --- Filter --------------------------------------------------------------

def polygon_stats(poly) -> dict:
    """Area and long/short side from the minimum rotated rectangle.

    `poly` must be in the tile's native, meters-based CRS (UTM). Feeding UTM
    meters to lon/lat geodesic functions silently returns NaN -- a real bug
    in an earlier version of this pipeline.
    """
    rect = poly.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)
    sides = [
        math.hypot(coords[i + 1][0] - coords[i][0], coords[i + 1][1] - coords[i][1])
        for i in range(len(coords) - 1)
    ]
    nonzero = [s for s in sides if s > 1e-6]
    length = max(sides) if sides else 0.0
    width = min(nonzero) if nonzero else 0.0
    return {
        "area_m2": poly.area,
        "length_m": length,
        "width_m": width,
        "aspect": length / width if width > 0 else float("inf"),
    }


def filter_reasons(stats: dict, animal_type: str | None = None,
                   dist_to_road_m: float | None = None) -> list[str]:
    """Every criterion a candidate fails. Empty list == kept."""
    t = filter_thresholds(animal_type)
    reasons = []
    if stats["width_m"] <= 0:
        return ["zero width"]
    if not t["AREA_MIN_M2"] <= stats["area_m2"] <= t["AREA_MAX_M2"]:
        reasons.append(f"area {stats['area_m2']:.0f} m2 outside {t['AREA_MIN_M2']:.0f}-{t['AREA_MAX_M2']:.0f}")
    if not t["LENGTH_MIN_M"] <= stats["length_m"] <= t["LENGTH_MAX_M"]:
        reasons.append(f"length {stats['length_m']:.1f} m outside {t['LENGTH_MIN_M']:.0f}-{t['LENGTH_MAX_M']:.0f}")
    if not t["WIDTH_MIN_M"] <= stats["width_m"] <= t["WIDTH_MAX_M"]:
        reasons.append(f"width {stats['width_m']:.1f} m outside {t['WIDTH_MIN_M']:.0f}-{t['WIDTH_MAX_M']:.0f}")
    if not t["ASPECT_MIN"] <= stats["aspect"] <= t["ASPECT_MAX"]:
        reasons.append(f"aspect {stats['aspect']:.2f} outside {t['ASPECT_MIN']}-{t['ASPECT_MAX']}")
    if dist_to_road_m is not None and dist_to_road_m < t["MIN_DIST_TO_ROAD_M"]:
        reasons.append(f"{dist_to_road_m:.0f} m from road (< {t['MIN_DIST_TO_ROAD_M']:.0f})")
    return reasons


def passes_tulbure_filter(stats: dict, dist_to_road_m: float | None,
                          animal_type: str | None = None) -> bool:
    """Backward-compatible boolean form of filter_reasons().

    Accepts the older stats keys (long_side_m/short_side_m) too.
    """
    if "length_m" not in stats:
        length, width = stats["long_side_m"], stats["short_side_m"]
        stats = {"area_m2": stats["area_m2"], "length_m": length, "width_m": width,
                 "aspect": length / width if width > 0 else float("inf")}
    return not filter_reasons(stats, animal_type, dist_to_road_m)


# --- Optional road filter (OSM) ------------------------------------------

def load_road_union(tile_bbox: tuple, cache_dir: Path):
    """OSM through-roads for a tile's bbox (WGS84), cached on disk."""
    import requests
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    cache_dir.mkdir(parents=True, exist_ok=True)
    key = f"{tile_bbox[0]:.4f}_{tile_bbox[1]:.4f}_{tile_bbox[2]:.4f}_{tile_bbox[3]:.4f}.json"
    cache_file = cache_dir / key
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
    else:
        w, s, e, n = tile_bbox
        highway = "motorway|trunk|primary|secondary|tertiary|unclassified|residential"
        query = f'[out:json][timeout:25];way["highway"~"^({highway})$"]({s},{w},{n},{e});out geom;'
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
    return unary_union(lines) if lines else None


# --- One site, end to end ------------------------------------------------

@dataclass
class SiteResult:
    """Everything produced for one tile, kept and rejected alike."""
    site: dict
    img: np.ndarray            # HWC uint8, R G B NIR
    meta: dict                 # crs, transform, bounds, res_m
    prob: np.ndarray           # building probability [H, W]
    mask: np.ndarray           # hard mask before morphological close
    candidates: list = field(default_factory=list)  # dicts, see detect_site()

    @property
    def kept(self) -> list:
        return [c for c in self.candidates if c["kept"]]

    @property
    def rejected(self) -> list:
        return [c for c in self.candidates if not c["kept"]]

    def features(self, include_rejected: bool = False) -> list[dict]:
        """GeoJSON features (WGS84) for this site."""
        rows = self.candidates if include_rejected else self.kept
        return [c["feature"] for c in rows]


def detect_site(site: dict, model, device, use_road_filter: bool = False,
                osm_cache_dir: Path = ROOT / "data/cache/osm") -> SiteResult:
    """Run the full pipeline on one manifest entry.

    Each candidate dict: {"poly" (tile CRS), "stats", "dist_to_road_m",
    "reasons", "kept", "feature" (GeoJSON, WGS84)}.
    """
    img, meta = read_tile(tile_path(site))
    scores = predict_class_scores(model, device, img)
    prob, mask = scores[1], scores_to_mask(scores)
    polys = mask_to_polygons(mask, meta["transform"])

    to_wgs84 = Transformer.from_crs(meta["crs"], "EPSG:4326", always_xy=True).transform
    road_union = None
    if use_road_filter and "bbox" in site:
        roads = load_road_union(tuple(site["bbox"]), osm_cache_dir)
        if roads is not None:
            to_native = Transformer.from_crs("EPSG:4326", meta["crs"], always_xy=True).transform
            road_union = shapely_transform(to_native, roads)

    animal_type = site.get("animal_type")
    group = species_group(animal_type)
    result = SiteResult(site=site, img=img, meta=meta, prob=prob, mask=mask)
    for i, poly in enumerate(polys):
        stats = polygon_stats(poly)
        dist = poly.centroid.distance(road_union) if road_union is not None else None
        reasons = filter_reasons(stats, animal_type, dist)
        kept = not reasons
        result.candidates.append({
            "poly": poly,
            "stats": stats,
            "dist_to_road_m": dist,
            "reasons": reasons,
            "kept": kept,
            "feature": {
                "type": "Feature",
                "geometry": mapping(shapely_transform(to_wgs84, poly)),
                "properties": {
                    "class_name": "building",
                    "detector": DETECTOR_NAME,
                    "kept": kept,
                    "reject_reasons": "; ".join(reasons) or None,
                    "farm_name": site["farm_name"],
                    "county": site.get("county"),
                    "animal_type": animal_type,
                    "species_group": group,
                    "headcount": site.get("headcount"),
                    "area_m2": round(stats["area_m2"], 1),
                    "length_m": round(stats["length_m"], 1),
                    "width_m": round(stats["width_m"], 1),
                    "aspect": round(stats["aspect"], 2) if math.isfinite(stats["aspect"]) else None,
                    "distance_to_road_m": round(dist, 1) if dist is not None else None,
                    "mean_prob": round(float(_mean_prob_in(poly, prob, meta["transform"])), 3),
                    "tile": Path(site["tile_path"]).name,
                    "tile_path": str(site["tile_path"]),
                    "naip_datetime": site.get("naip_datetime"),
                    "candidate_id": f"{Path(site['tile_path']).parent.name}/{Path(site['tile_path']).stem}_{i:03d}",
                },
            },
        })
    return result


def _mean_prob_in(poly, prob: np.ndarray, transform) -> float:
    """Mean model probability inside a polygon -- a per-building confidence."""
    from rasterio.features import geometry_mask
    inside = geometry_mask([mapping(poly)], out_shape=prob.shape, transform=transform, invert=True)
    return prob[inside].mean() if inside.any() else 0.0
