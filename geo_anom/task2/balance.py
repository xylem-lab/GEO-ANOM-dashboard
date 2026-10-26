"""
The poultry -> corn loop: litter supply (Task 1 houses) against corn (CDL) on
a square grid, first without nutrient coefficients, then with them.

    houses_on_grid(buildings, cell_m)         houses + roof area per cell
    build_grid(houses, crops, cell_m)         one GeoDataFrame, all cells with either
    add_within(grid, cols, radius_m, cell_m)  the same sums over every cell within a
                                              radius (how far litter is hauled)
    roof_per_acre(supply, demand)             the coefficient-free balance index
    nutrient_balance(grid, coeffs, ...)       N / P2O5 supply, demand and balance,
                                              only once every coefficient is filled in

Why the index already says most of what the map will say: if litter per m2 of
house floor (a) and crop need per acre (b) are constants, then

    surplus  <=>  a * roof_m2 > b * acres  <=>  roof_m2 / acres > b / a

so ranking places by roof m2 per corn acre is the same ranking the N or P map
will give. The Extension numbers (Ginny Rhodes, John Moyle) set where the
surplus line b / a falls, not which places are on top. The assumption is that
a and b don't vary much from place to place (same bird type, stocking, flocks
per year; same yield goal), which is worth asking them about.

Cells are absolute: cell (ix, iy) is [ix * cell_m, (ix + 1) * cell_m) in UTM 18N
metres, so grids of the same size line up across runs.
"""

from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

UTM = "EPSG:32618"

# Every coefficient the N/P map needs. None = not agreed yet; nutrient_balance()
# refuses to run until all are set. Fill in from the Extension meeting
# (Rhodes, Moyle) and the AWTF 2023 report, with the source next to each.
COEFFICIENTS = {
    # supply, per m2 of detected poultry-house roof
    "detection_recall": {"value": 0.67, "unit": "share of houses found",
                         "source": "notebook 05: Eastern Shore pooled recall vs USGS hand tracing (2016/17)"},
    "birds_per_m2": {"value": None, "unit": "birds on the floor per m2 of house", "source": "pending: Extension"},
    "flocks_per_year": {"value": None, "unit": "flocks / yr", "source": "pending: Extension"},
    "litter_N_lb_per_bird_flock": {"value": None, "unit": "lb N in litter per bird per flock",
                                   "source": "pending: Extension / AWTF 2023 Table 1a.1"},
    "litter_N_available": {"value": None, "unit": "share of litter N available to the crop in year 1",
                           "source": "pending: Extension"},
    "litter_P2O5_lb_per_bird_flock": {"value": None, "unit": "lb P2O5 in litter per bird per flock",
                                      "source": "pending: Extension / AWTF 2023 Table 1a.1"},
    # demand, per acre of corn
    "corn_N_lb_per_acre": {"value": None, "unit": "lb N / acre / yr", "source": "pending: UMD nutrient recommendations"},
    "corn_P2O5_lb_per_acre": {"value": None, "unit": "lb P2O5 / acre / yr (crop removal)",
                              "source": "pending: UMD nutrient recommendations"},
}


def coefficient_table(coeffs: dict = COEFFICIENTS) -> pd.DataFrame:
    return pd.DataFrame(coeffs).T[["value", "unit", "source"]]


def missing_coefficients(coeffs: dict = COEFFICIENTS) -> list[str]:
    return [k for k, v in coeffs.items() if v.get("value") is None]


def cell_of(x, y, cell_m: float):
    return np.floor(np.asarray(x) / cell_m).astype(int), np.floor(np.asarray(y) / cell_m).astype(int)


def houses_on_grid(buildings: gpd.GeoDataFrame, cell_m: float) -> pd.DataFrame:
    """Houses and roof area (m2, measured in UTM) per cell, by house centroid."""
    b = buildings.to_crs(UTM)
    c = b.geometry.centroid
    ix, iy = cell_of(c.x, c.y, cell_m)
    d = pd.DataFrame({"ix": ix, "iy": iy, "roof_m2": b.geometry.area.values})
    return d.groupby(["ix", "iy"]).agg(houses=("roof_m2", "size"), roof_m2=("roof_m2", "sum"))


def build_grid(houses: pd.DataFrame, crops: dict, cell_m: float) -> gpd.GeoDataFrame:
    """Join houses_on_grid() with {name: {(ix, iy): acres}} into one grid.

    Crop columns are named `<name>_acres`. Every cell with houses or any crop
    is kept; missing values are 0.
    """
    keys = set(houses.index) | set().union(*[set(d) for d in crops.values()])
    idx = pd.MultiIndex.from_tuples(sorted(keys), names=["ix", "iy"])
    g = houses.reindex(idx).fillna(0)
    g["houses"] = g["houses"].astype(int)
    for name, d in crops.items():
        g[f"{name}_acres"] = pd.Series(d).reindex(idx).fillna(0).values
    g = g.reset_index()
    g["cell_id"] = g.ix.astype(str) + "_" + g.iy.astype(str)
    geom = [box(i * cell_m, j * cell_m, (i + 1) * cell_m, (j + 1) * cell_m) for i, j in zip(g.ix, g.iy)]
    return gpd.GeoDataFrame(g, geometry=geom, crs=UTM)


def _disk(radius_m: float, cell_m: float) -> np.ndarray:
    r = int(math.ceil(radius_m / cell_m))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (np.hypot(xx, yy) * cell_m <= radius_m).astype(float)


def add_within(grid: gpd.GeoDataFrame, cols: list[str], radius_m: float, cell_m: float) -> gpd.GeoDataFrame:
    """For each cell, the sum of `cols` over all cells whose centre is within
    radius_m of its centre (itself included). New columns `<col>_<R>km`."""
    from scipy.ndimage import convolve

    g = grid.copy()
    i0, j0 = g.ix.min(), g.iy.min()
    shape = (g.iy.max() - j0 + 1, g.ix.max() - i0 + 1)
    k = _disk(radius_m, cell_m)
    tag = f"{radius_m / 1000:g}km"
    for col in cols:
        a = np.zeros(shape)
        a[g.iy - j0, g.ix - i0] = g[col].values
        s = convolve(a, k, mode="constant", cval=0.0)
        g[f"{col}_{tag}"] = s[g.iy - j0, g.ix - i0]
    return g


def roof_per_acre(supply, demand) -> np.ndarray:
    """m2 of poultry-house roof per acre of crop. inf where there are houses but
    no crop; NaN where there is neither."""
    s, d = np.asarray(supply, float), np.asarray(demand, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = s / d
    r[(d == 0) & (s > 0)] = np.inf
    r[(d == 0) & (s == 0)] = np.nan
    return r


def implied_birds_per_m2(birds: float, roof_m2: float, recall: float) -> float:
    """Birds per m2 of house implied by a county's reported inventory and our
    detected roof area, scaled up for the houses we miss. A cross-check for the
    Extension stocking number, not a replacement for it."""
    return birds / (roof_m2 / recall) if roof_m2 else float("nan")


def nutrient_balance(grid: gpd.GeoDataFrame, coeffs: dict, roof_col: str = "roof_m2",
                     acres_col: str = "corn_acres") -> gpd.GeoDataFrame:
    """N (plant-available) and P2O5: supply, demand, balance (lb/yr) per cell.

    Refuses to run while any coefficient is missing, so no N/P number exists
    before the inputs are agreed.
    """
    miss = missing_coefficients(coeffs)
    if miss:
        raise ValueError("coefficients not set yet: " + ", ".join(miss))
    v = {k: c["value"] for k, c in coeffs.items()}
    g = grid.copy()
    birds = g[roof_col] / v["detection_recall"] * v["birds_per_m2"]
    bird_flocks = birds * v["flocks_per_year"]
    g["N_supply_lb"] = bird_flocks * v["litter_N_lb_per_bird_flock"] * v["litter_N_available"]
    g["P2O5_supply_lb"] = bird_flocks * v["litter_P2O5_lb_per_bird_flock"]
    g["N_demand_lb"] = g[acres_col] * v["corn_N_lb_per_acre"]
    g["P2O5_demand_lb"] = g[acres_col] * v["corn_P2O5_lb_per_acre"]
    g["N_balance_lb"] = g.N_supply_lb - g.N_demand_lb
    g["P2O5_balance_lb"] = g.P2O5_supply_lb - g.P2O5_demand_lb
    return g
