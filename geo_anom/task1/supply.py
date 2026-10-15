"""
N / P2O5 supply from mapped buildings + registry permits.

Deliberately simple so every number can be checked by hand:

    farm annual N  = registry headcount x N per head per flock x flocks/yr
    building N     = farm N x (building floor area / farm's total floor area)

Headcount comes from the registry (capacity, not actual inventory). Imagery
supplies *where* the manure is (which buildings) and how a farm's total is
split across its buildings. A farm with no detected building keeps its full
supply at the registry point, flagged `located_by="registry_point_only"` --
dropping it would silently erase most dairy supply, since dairy barns are
mostly not detected (1/14 farms).

Coefficients come from configs/maryland.yaml. Check them against the AWTF
2023 report before trusting any total: as of 2026-10-05 the broiler
coefficient gives ~14x the AWTF statewide broiler N (see AWTF_BENCHMARKS and
notebooks/02_supply_check.ipynb).

The vision-first headcount model (branch
feature/vision-first-supply-estimate-2026-09-30) is not used here; it is
unmerged and has not been validated independently of the registry.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from geo_anom.core.config import get_config
from geo_anom.task1.species import species_group
from geo_anom.task1.tiles import site_id

# Registry animal_type -> config nutrient_coefficients key.
COEFF_KEY = {
    "chickens_not_laying_hens": "broiler_chicken",
    "laying_hens_dry_manure": "layer_chicken",
    "turkeys": "turkey",
    "dairy_cattle": "dairy_cattle",
    "cattle_includes_heifers": "beef_cattle",
    "swine_55_lbs": "swine",
    # ducks, horses: no coefficient in config -> no supply, reported as such
}

# Independent statewide figures to check totals against.
# Maryland Animal Waste Technology Assessment and Strategy Planning, Final
# Report (Lansing et al., Sept 2023), p.23: N derived from broiler litter, 2019.
AWTF_BENCHMARKS = {
    "broiler_N_lbs_2019": 21_849_000,
}


def farm_supply(sites: list[dict], buildings: gpd.GeoDataFrame, config=None) -> pd.DataFrame:
    """One row per registry farm: headcount, coefficients, N/P, building count/area."""
    config = config or get_config()
    area = buildings.groupby("assigned_site_id")["area_m2"].agg(["size", "sum"]) if len(buildings) else None

    rows = []
    for s in sites:
        key = COEFF_KEY.get(s.get("animal_type"))
        coeff = config.nutrient_coefficients.get(key) if key else None
        hc = s.get("headcount") or 0
        sid = site_id(s)
        n_bld = int(area.loc[sid, "size"]) if area is not None and sid in area.index else 0
        rows.append({
            "site_id": sid,
            "farm_name": s["farm_name"],
            "county": s.get("county"),
            "animal_type": s.get("animal_type"),
            "species_group": species_group(s.get("animal_type")),
            "headcount": hc,
            "coeff_key": key,
            "N_per_head_per_flock": coeff.N_lbs_per_head_per_year if coeff else None,
            "P2O5_per_head_per_flock": coeff.P2O5_lbs_per_head_per_year if coeff else None,
            "flocks_per_year": coeff.flocks_per_year if coeff else None,
            "annual_N_lbs": hc * coeff.N_lbs_per_head_per_year * coeff.flocks_per_year if coeff else 0.0,
            "annual_P2O5_lbs": hc * coeff.P2O5_lbs_per_head_per_year * coeff.flocks_per_year if coeff else 0.0,
            "n_buildings": n_bld,
            "building_area_m2": float(area.loc[sid, "sum"]) if n_bld else 0.0,
            "located_by": "detected_buildings" if n_bld else "registry_point_only",
            "no_coefficient": coeff is None,
            "lat": s["lat"],
            "lon": s["lon"],
        })
    return pd.DataFrame(rows)


def building_supply(buildings: gpd.GeoDataFrame, farms: pd.DataFrame) -> gpd.GeoDataFrame:
    """Split each farm's N/P across its buildings by floor-area share."""
    f = farms.set_index("site_id")
    out = buildings.copy()
    key = out["assigned_site_id"]
    share = out["area_m2"] / key.map(f["building_area_m2"])
    out["area_share"] = share.round(4)
    out["annual_N_lbs"] = (key.map(f["annual_N_lbs"]) * share).round(1)
    out["annual_P2O5_lbs"] = (key.map(f["annual_P2O5_lbs"]) * share).round(1)
    return out


def species_totals(farms: pd.DataFrame) -> pd.DataFrame:
    t = farms.groupby("species_group").agg(
        farms=("farm_name", "size"),
        farms_with_buildings=("n_buildings", lambda s: int((s > 0).sum())),
        headcount=("headcount", "sum"),
        annual_N_lbs=("annual_N_lbs", "sum"),
        annual_P2O5_lbs=("annual_P2O5_lbs", "sum"),
    )
    t["share_of_N"] = (t["annual_N_lbs"] / t["annual_N_lbs"].sum()).round(3)
    return t.sort_values("annual_N_lbs", ascending=False)
