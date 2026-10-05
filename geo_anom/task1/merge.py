"""
Turn per-tile detections into one statewide building layer.

Two problems with simply concatenating every tile's output (what the
committed full_registry_unet_tulbure_detections.geojson does):

1. Duplicates. Tiles are 2km x 2km around each permit point, and neighbouring
   farms' tiles overlap, so one physical barn is detected once per tile that
   covers it. In the committed file, 541 of 2,726 features (20%) overlap a
   feature from a different tile by >50% -- e.g. the Tran-family farms share
   the same ~35 barns across 4 tiles.
2. Attribution. A tile's buildings include its neighbours' barns, so "farm
   the tile was pulled for" is not "farm the building belongs to".

deduplicate() collapses overlapping detections into one feature (the copy
with the highest model confidence) and attributes each building to the
nearest registry permit point. Registry points are often 400-860 m from the
real barns (2026-09-23 imagery review), so `assigned_distance_m` is kept on
every feature -- large values mean the attribution is a guess.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

from geo_anom.task1.species import species_group
from geo_anom.task1.tiles import site_id

UTM = "EPSG:32618"


def _components(n: int, pairs) -> np.ndarray:
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return np.array([find(i) for i in range(n)])


def deduplicate(features: list[dict], sites: list[dict], min_overlap: float = 0.5) -> gpd.GeoDataFrame:
    """Kept detections from all tiles -> unique, farm-attributed buildings.

    Two detections are the same building if their intersection covers more
    than `min_overlap` of the smaller one. Returns a GeoDataFrame (WGS84)
    with one row per building plus `n_detections` (how many tiles saw it),
    `assigned_farm`, `assigned_distance_m`, and the assigned permit's
    `animal_type`/`species_group`/`headcount`.
    """
    if not features:
        return gpd.GeoDataFrame(
            columns=["building_id", "n_detections", "seen_from_tiles", "assigned_site_id", "assigned_farm",
                     "assigned_distance_m", "animal_type", "species_group", "headcount",
                     "county", "farm_name", "area_m2", "mean_prob", "geometry"],
            geometry="geometry", crs="EPSG:4326")
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326").to_crs(UTM)
    gdf = gdf.rename(columns={"farm_name": "tile_farm_name"}).reset_index(drop=True)
    gdf["_i"] = np.arange(len(gdf))

    pairs = []
    if len(gdf):
        j = gpd.sjoin(gdf[["_i", "geometry"]], gdf[["_i", "geometry"]], predicate="intersects")
        j = j[j["_i_left"] < j["_i_right"]]
        geoms = gdf.geometry.values
        for a, b in zip(j["_i_left"], j["_i_right"]):
            ga, gb = geoms[a], geoms[b]
            if ga.intersection(gb).area > min_overlap * min(ga.area, gb.area):
                pairs.append((a, b))
    gdf["building_id"] = _components(len(gdf), pairs)

    gdf["n_detections"] = gdf.groupby("building_id")["_i"].transform("size")
    gdf["seen_from_tiles"] = gdf.groupby("building_id")["tile_path"].transform(lambda s: ",".join(sorted(set(s))))
    best = gdf.sort_values(["mean_prob", "area_m2"], ascending=False).drop_duplicates("building_id")
    best = best.sort_values("building_id").reset_index(drop=True)

    # Attribute to the nearest permit point.
    site_pts = gpd.GeoDataFrame(
        [{"assigned_site_id": site_id(s), "assigned_farm": s["farm_name"], "a_animal_type": s.get("animal_type"),
          "a_headcount": s.get("headcount"), "a_county": s.get("county")} for s in sites],
        geometry=[Point(s["lon"], s["lat"]) for s in sites], crs="EPSG:4326",
    ).to_crs(UTM)
    centroids = best.set_geometry(best.geometry.centroid)[["building_id", "geometry"]]
    near = gpd.sjoin_nearest(centroids, site_pts, how="left", distance_col="assigned_distance_m")
    near = near.drop_duplicates("building_id").set_index("building_id")

    best["assigned_site_id"] = best["building_id"].map(near["assigned_site_id"])
    best["assigned_farm"] = best["building_id"].map(near["assigned_farm"])
    best["assigned_distance_m"] = best["building_id"].map(near["assigned_distance_m"]).round(0)
    best["animal_type"] = best["building_id"].map(near["a_animal_type"])
    best["headcount"] = best["building_id"].map(near["a_headcount"])
    best["county"] = best["building_id"].map(near["a_county"])
    best["species_group"] = best["animal_type"].map(species_group)
    best["farm_name"] = best["assigned_farm"]
    best = best.drop(columns=["_i"])
    return best.to_crs("EPSG:4326")
