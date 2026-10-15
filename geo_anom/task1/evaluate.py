"""
Accuracy of a map_buildings run against independent ground truth:
Soroka & Duren (2020), USGS, hand-digitised poultry-house footprints for
Delmarva from 2016/17 imagery (doi:10.5066/P9MO25Z7), in
data/raw/external/soroka_duren/.

Two measures, both restricted to the area covered by the run's tiles and by
the ground truth:

1. Farm-level count regression (the measure reported since 2026-09-10):
   per farm tile, kept detections vs. ground-truth houses in the same
   footprint, farms with >=1 ground-truth house.
2. Object-level precision / recall / F1: a detected building is correct if
   it overlaps a ground-truth footprint; a ground-truth house is found if a
   detection overlaps it. Plus IoU of matched pairs and centroid distances.

Caveats that belong next to any number from here:
- The shape filter's lower bounds were calibrated against this same ground
  truth (2026-09-02), so this is not a held-out test.
- Ground truth is 2016/17; imagery is 2023. Houses built since count as
  false positives, houses demolished since as misses.
- Before 2026-10-07 tiles were shifted for 219/417 sites; this ground truth
  was then wrongly described as "100-450 m off". On corrected tiles the median
  detection-to-house distance is ~4 m.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import box
from shapely.ops import unary_union

from geo_anom.phase1.evaluation import detection_metrics, regression_metrics
from geo_anom.task1.tiles import ROOT, tile_path

GROUND_TRUTH = ROOT / "data/raw/external/soroka_duren/Delmarva_PL_House_Final/Delmarva_PL_House_Final2.shp"


def load_ground_truth(path: Path = GROUND_TRUTH) -> gpd.GeoDataFrame:
    return gpd.read_file(path).explode(index_parts=False).reset_index(drop=True)


def _footprints(sites: list[dict], crs) -> list:
    out = []
    for s in sites:
        with rasterio.open(tile_path(s)) as src:
            out.append(gpd.GeoSeries([box(*src.bounds)], crs=src.crs).to_crs(crs).iloc[0])
    return out


def evaluate_run(run_dir: Path, gt: gpd.GeoDataFrame | None = None, area=None) -> dict:
    run_dir = Path(run_dir)
    gt = gt if gt is not None else load_ground_truth()
    sites = json.loads((run_dir / "sites.json").read_text())
    farms = pd.read_csv(run_dir / "farms.csv")
    fps = _footprints(sites, gt.crs)

    # 1. farm-level counts (farms.csv rows are in sites.json order)
    n_gt = [int(gt.intersects(fp).sum()) for fp in fps]
    d = pd.DataFrame({"detected": farms["kept_in_tile"].values, "ground_truth": n_gt})
    d = d[d.ground_truth > 0]
    farm_level = regression_metrics(d.ground_truth.tolist(), d.detected.tolist())

    # 2. object level, inside tiles AND the ground-truth extent
    covered = unary_union(fps).intersection(gt.unary_union.convex_hull.buffer(500))
    if area is not None:  # limit to e.g. a county (GeoDataFrame/GeoSeries with a CRS)
        covered = covered.intersection(area.to_crs(gt.crs).unary_union)
    area = covered
    b = gpd.read_file(run_dir / "buildings.geojson").to_crs(gt.crs)
    b = b[b.centroid.within(area)].reset_index(drop=True)
    g = gt[gt.centroid.within(area)].reset_index(drop=True)
    j = gpd.sjoin(b[["geometry"]], g[["geometry"]], predicate="intersects")
    obj = detection_metrics(tp=j.index.nunique(), fp=len(b) - j.index.nunique(),
                            fn=len(g) - j["index_right"].nunique())
    ious = [b.geometry[i].intersection(g.geometry[k]).area / b.geometry[i].union(g.geometry[k]).area
            for i, k in zip(j.index, j["index_right"])]
    dist = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=b.centroid, crs=gt.crs),
                             gpd.GeoDataFrame(geometry=g.centroid, crs=gt.crs), distance_col="d")["d"]

    def clean(m):
        return {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) else v) for k, v in m.items()}

    return {
        "ground_truth": "Soroka & Duren (2020) Delmarva poultry houses, 2016/17",
        "farm_level_counts": clean(farm_level),
        "object_level": {**clean(obj), "detections": len(b), "ground_truth_houses": len(g),
                         "median_iou_of_matches": round(float(np.median(ious)), 3) if ious else None},
        "centroid_distance_m": {"median": round(float(dist.median()), 1),
                                "p90": round(float(dist.quantile(0.9)), 1),
                                "share_within_25m": round(float((dist < 25).mean()), 3)},
        "caveats": ["filter calibrated on this ground truth (not held out)",
                    "ground truth 2016/17 vs imagery 2023"],
    }
