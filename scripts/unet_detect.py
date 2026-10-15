"""
Compatibility wrapper. Detection and filter code now lives in
geo_anom/task1/detect.py, and the full run is scripts/map_buildings.py.
This file keeps older diagnostic scripts that do `from unet_detect import ...`
working unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo_anom.task1.detect import (  # noqa: E402,F401
    AREA_MAX_M2,
    AREA_MIN_M2,
    ASPECT_MAX,
    ASPECT_MIN,
    LENGTH_MAX_M,
    LENGTH_MIN_M,
    MIN_DIST_TO_ROAD_M,
    SPECIES_FILTER_OVERRIDES,
    WIDTH_MAX_M,
    WIDTH_MIN_M,
    load_road_union,
    passes_tulbure_filter,
    polygon_stats,
)


def polygon_geo_stats(poly) -> dict:
    """Old key names: area_m2, long_side_m, short_side_m."""
    s = polygon_stats(poly)
    return {"area_m2": s["area_m2"], "long_side_m": s["length_m"], "short_side_m": s["width_m"]}


def distance_to_road_m(poly, road_union_native_crs) -> float | None:
    if road_union_native_crs is None:
        return None
    return poly.centroid.distance(road_union_native_crs)


if __name__ == "__main__":
    sys.exit("Use scripts/map_buildings.py (same detector, plus de-duplication and KMZ output).")
