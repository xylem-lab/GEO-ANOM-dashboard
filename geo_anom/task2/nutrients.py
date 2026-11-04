"""
Task 2: poultry litter from the mapped houses against what Maryland's cropland can use
(notebook 13). Every number comes from one coefficient sheet with a low / mid / high value
and a source for each; change the sheet, rerun, and every table and map follows.

    houses -> litter                  roof m2 x floor share x birds/ft2 -> birds per flock
                                      x flocks/yr x share of houses active -> birds a year
                                      x lb litter per bird -> tons of litter a year
    litter -> nutrients               tons x lb N/ton x share available in year 1 -> crop-available N
                                      tons x lb P/ton x 2.29 -> P2O5
    cropland -> need (CDL 2023)       corn, soybeans, small grains and their double crops,
                                      UMD-style rates per acre (soybeans take no N)
    the P limit                       cropland too high in P takes none: share from the DLLC (2019)
                                      Maryland fit, 1.632 x (lb litter P per cropland acre) + 10.294 %,
                                      plus an offset; P on the rest = removal x P_rate_multiplier
    the balance, in tons of litter    what the cropland can take = the smaller of the N-based and
                                      P-based amounts; surplus = litter - that
    uncertainty                       every coefficient drawn from a triangular(low, mid, high)
                                      distribution; a place is a *robust* surplus when it is in
                                      surplus in >= 90% of draws
    translocation                     surplus tons moved to counties with room, least ton-km
                                      (linear program); what doesn't fit stays "unplaced"

Delaware and Virginia cropland is not in the demand (Maryland data only), so "unplaced"
litter is the part that would have to leave Maryland's cropland or go to other uses.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SHEET = ROOT / "data/reference/task2_coefficients.csv"
FT2_PER_M2 = 10.7639
P_TO_P2O5 = 2.2914
REQUIRED = ["floor_share", "birds_per_ft2", "flocks_per_year", "active_share", "litter_lb_per_bird", "N_lb_per_ton",
            "P_lb_per_ton", "N_available", "corn_N_lb_per_acre", "corn_P2O5_lb_per_acre", "soy_P2O5_lb_per_acre",
            "small_grain_N_lb_per_acre", "small_grain_P2O5_lb_per_acre", "P_rate_multiplier", "high_P_offset"]
LEVELS = ["low", "mid", "high"]

# CDL classes by demand group (NASS legend). Hay and pasture are left out of the demand.
CROPS = {
    "corn": [1],
    "soybeans": [5],
    "small_grains": [21, 23, 24, 27, 28],        # barley, spring wheat, winter wheat, rye, oats
    "small_grain_soy": [26, 254],                # double crop winter wheat / soybeans, barley / soybeans
    "small_grain_corn": [225, 226, 237],         # double crop wheat / corn, oats / corn, barley / corn
    "corn_soy": [241],                           # double crop corn / soybeans
}
# optional (scenario): hay takes litter too; needs hay_N_lb_per_acre / hay_P2O5_lb_per_acre in the sheet
HAY = [36, 37]                                   # alfalfa, other hay
# DLLC (2019) Maryland fit: % of cropland above FIV 150 = A * (lb litter P per cropland acre) + B
DLLC_HIGH_P = (1.632, 10.294)


# ── the coefficient sheet ──────────────────────────────────────────────────────

def load_coefficients(path: Path | None = None) -> pd.DataFrame:
    """The sheet (CSV) indexed by name; checks every coefficient is there and low <= mid <= high."""
    path = Path(path or DEFAULT_SHEET)
    c = pd.read_csv(path, comment="#").set_index("name")
    miss = [k for k in REQUIRED if k not in c.index]
    if miss:
        raise ValueError(f"{path.name} is missing: {', '.join(miss)}")
    c[LEVELS] = c[LEVELS].astype(float)
    bad = c[(c["low"] > c["mid"]) | (c["mid"] > c["high"])].index.tolist()
    if bad:
        raise ValueError(f"low <= mid <= high fails for: {', '.join(bad)}")
    c.attrs["path"], c.attrs["sha256"] = str(path), hashlib.sha256(path.read_bytes()).hexdigest()
    return c


def sheet_changes(sheet: pd.DataFrame, default: Path = DEFAULT_SHEET) -> pd.DataFrame:
    """Rows where `sheet` differs from the repo's default sheet (what Rafi changed)."""
    d = load_coefficients(default)
    common = sheet.index.intersection(d.index)
    diff = (sheet.loc[common, LEVELS] != d.loc[common, LEVELS]).any(axis=1)
    out = sheet.loc[common[diff], LEVELS + ["source"]].join(d.loc[common[diff], LEVELS], rsuffix="_default")
    return out


def values(sheet: pd.DataFrame, level: str = "mid") -> dict:
    return sheet[level].to_dict()


def draw(sheet: pd.DataFrame, n: int, seed: int = 0) -> dict:
    """n draws of every coefficient, triangular(low, mid, high); fixed ones stay fixed. Arrays (n, 1)."""
    rng = np.random.default_rng(seed)
    out = {}
    for k, r in sheet.iterrows():
        lo, mid, hi = r["low"], r["mid"], r["high"]
        x = np.full(n, mid) if lo == hi else rng.triangular(lo, mid, hi, n)
        out[k] = x[:, None]
    return out


# ── supply, need, balance ──────────────────────────────────────────────────────

def litter(roof_m2, v: dict) -> dict:
    """Birds a year, tons of litter, crop-available N and P2O5 (lb) from roof area (m2)."""
    roof = np.asarray(roof_m2, float)
    birds_flock = roof * FT2_PER_M2 * v["floor_share"] * v["birds_per_ft2"]
    birds_year = birds_flock * v["flocks_per_year"] * v["active_share"]
    tons = birds_year * v["litter_lb_per_bird"] / 2000
    return {"birds_year": birds_year, "tons": tons,
            "N_total_lb": tons * v["N_lb_per_ton"],
            "N_available_lb": tons * v["N_lb_per_ton"] * v["N_available"],
            "P_lb": tons * v["P_lb_per_ton"],
            "P2O5_lb": tons * v["P_lb_per_ton"] * P_TO_P2O5}


def crop_need(acres: dict, v: dict) -> dict:
    """N and P2O5 the cropland needs (lb), from acres per CROPS group."""
    a = {k: np.asarray(acres.get(k, 0.0), float) for k in CROPS}
    cN, cP = v["corn_N_lb_per_acre"], v["corn_P2O5_lb_per_acre"]
    sP = v["soy_P2O5_lb_per_acre"]
    gN, gP = v["small_grain_N_lb_per_acre"], v["small_grain_P2O5_lb_per_acre"]
    N = a["corn"] * cN + a["small_grains"] * gN + a["small_grain_soy"] * gN + a["small_grain_corn"] * (gN + cN) + a["corn_soy"] * cN
    P = (a["corn"] * cP + a["soybeans"] * sP + a["small_grains"] * gP + a["small_grain_soy"] * (gP + sP)
         + a["small_grain_corn"] * (gP + cP) + a["corn_soy"] * (cP + sP))
    acres_total = sum(a.values())
    if "hay" in acres:
        if "hay_N_lb_per_acre" not in v:
            raise ValueError("hay acres given but the sheet has no hay_N_lb_per_acre / hay_P2O5_lb_per_acre")
        h = np.asarray(acres["hay"], float)
        N, P, acres_total = N + h * v["hay_N_lb_per_acre"], P + h * v["hay_P2O5_lb_per_acre"], acres_total + h
    return {"N_need_lb": N, "P2O5_need_lb": P, "crop_acres": acres_total}


def high_P_share(P_lb, crop_acres, v: dict):
    """Share of cropland too high in P to take any (DLLC fit + offset), between 0 and 0.95."""
    with np.errstate(divide="ignore", invalid="ignore"):
        per_acre = np.where(np.asarray(crop_acres) > 0, np.asarray(P_lb) / np.asarray(crop_acres), 0.0)
    s = (DLLC_HIGH_P[0] * per_acre + DLLC_HIGH_P[1]) / 100 + v["high_P_offset"]
    return np.clip(s, 0.0, 0.95)


def balance(roof_m2, acres: dict, v: dict, hiP=None) -> dict:
    """Everything per place, in lb and tons of litter. `hiP` = the share of cropland too high in
    P (computed from the place's own litter P per acre if not given -- the DLLC fit is a
    county-level relation, so for grid cells pass the county's share)."""
    s, d = litter(roof_m2, v), crop_need(acres, v)
    if hiP is None:
        hiP = high_P_share(s["P_lb"], d["crop_acres"], v)
    P_need_ok = d["P2O5_need_lb"] * (1 - hiP) * v["P_rate_multiplier"]
    N_per_ton = v["N_lb_per_ton"] * v["N_available"]
    P2O5_per_ton = v["P_lb_per_ton"] * P_TO_P2O5
    cap_N, cap_P = d["N_need_lb"] / N_per_ton, P_need_ok / P2O5_per_ton
    cap = np.minimum(cap_N, cap_P)
    return {**s, **d, "high_P_share": hiP, "P2O5_need_eligible_lb": P_need_ok,
            "N_balance_lb": s["N_available_lb"] - d["N_need_lb"], "P2O5_balance_lb": s["P2O5_lb"] - P_need_ok,
            "capacity_tons_N": cap_N, "capacity_tons_P": cap_P, "capacity_tons": cap,
            "P_limits": cap_P < cap_N, "surplus_tons": s["tons"] - cap}


# ── uncertainty ────────────────────────────────────────────────────────────────

def monte_carlo(roof_m2, acres: dict, sheet: pd.DataFrame, n: int = 2000, seed: int = 0, hiP_from=None) -> dict:
    """balance() for n coefficient draws; arrays (n, places). `hiP_from` = (roof, acres) of the
    areas whose litter P sets the high-P share (e.g. counties) and an index mapping each place
    to one of them: (roof_c, acres_c, idx)."""
    v = draw(sheet, n, seed)
    hiP = None
    if hiP_from is not None:
        roof_c, acres_c, idx = hiP_from
        sc, dc = litter(roof_c, v), crop_need(acres_c, v)
        hiP = high_P_share(sc["P_lb"], dc["crop_acres"], v)[:, idx]
    return balance(roof_m2, acres, v, hiP)


def summarize_draws(x: np.ndarray, index) -> pd.DataFrame:
    """p5 / p50 / p95 and P(x > 0) per place from (draws, places)."""
    return pd.DataFrame({"p5": np.percentile(x, 5, axis=0), "p50": np.percentile(x, 50, axis=0),
                         "p95": np.percentile(x, 95, axis=0), "p_surplus": (x > 0).mean(axis=0)}, index=index)


def tornado(roof_m2, acres: dict, sheet: pd.DataFrame, what: str = "surplus_tons", agg=np.sum) -> pd.DataFrame:
    """One coefficient at a time at its low and high (the rest at mid): the change in `what`
    summed over places. Sorted by swing."""
    base = agg(balance(roof_m2, acres, values(sheet))[what])
    rows = []
    for k in sheet.index:
        if sheet.loc[k, "low"] == sheet.loc[k, "high"]:
            continue
        r = {"coefficient": k, "base": base}
        for lev in ["low", "high"]:
            v = values(sheet); v[k] = sheet.loc[k, lev]
            r[lev] = agg(balance(roof_m2, acres, v)[what])
        r["swing"] = abs(r["high"] - r["low"])
        rows.append(r)
    return pd.DataFrame(rows).sort_values("swing", ascending=False).reset_index(drop=True)


# ── translocation ──────────────────────────────────────────────────────────────

def translocate(surplus: pd.Series, room: pd.Series, dist_km: pd.DataFrame) -> tuple:
    """Least ton-km moves of surplus litter (tons, by place) into room (tons, by place).
    Returns (flows: from, to, tons, km; unplaced tons by origin). Linear program (HiGHS)."""
    from scipy.optimize import linprog

    src = surplus[surplus > 0]
    dst = room[room > 0]
    if not len(src):
        return pd.DataFrame(columns=["from", "to", "tons", "km"]), pd.Series(dtype=float)
    ns, nd = len(src), len(dst)
    D = dist_km.loc[src.index, dst.index].values if nd else np.zeros((ns, 0))
    big = 10 * (D.max() if D.size else 1) + 1
    # variables: flows (ns x nd) then unplaced (ns); cost = ton-km, unplaced at a high price
    c = np.concatenate([D.ravel(), np.full(ns, big)])
    A_eq = np.zeros((ns, ns * nd + ns)); b_eq = src.values
    for i in range(ns):
        A_eq[i, i * nd:(i + 1) * nd] = 1; A_eq[i, ns * nd + i] = 1
    A_ub = np.zeros((nd, ns * nd + ns)); b_ub = dst.values
    for j in range(nd):
        A_ub[j, j:ns * nd:nd] = 1
    res = linprog(c, A_ub=A_ub if nd else None, b_ub=b_ub if nd else None, A_eq=A_eq, b_eq=b_eq,
                  bounds=(0, None), method="highs")
    if not res.success:
        raise RuntimeError(res.message)
    f = res.x[:ns * nd].reshape(ns, nd)
    rows = [{"from": src.index[i], "to": dst.index[j], "tons": f[i, j], "km": D[i, j]}
            for i in range(ns) for j in range(nd) if f[i, j] > 1e-6]
    return pd.DataFrame(rows), pd.Series(res.x[ns * nd:], index=src.index)


# Where trucks cross between the Eastern Shore and the rest of Maryland (lon, lat)
CROSSINGS = {"Chesapeake Bay Bridge": (-76.381, 38.993), "I-95 Susquehanna bridge": (-76.083, 39.563)}


def centroid_km(gdf, name_col: str, road_factor: float = 1.25, east: list | None = None,
                crossings: dict | None = None, utm: str = "EPSG:32618") -> pd.DataFrame:
    """Distance between area centroids, km: straight line x a road factor. With `east` (the
    names on the Eastern Shore), a trip between the two shores goes over the nearer crossing
    (`crossings`, default the Bay Bridge and the I-95 bridge) instead of across the water."""
    import geopandas as gpd

    c = gdf.set_index(name_col).geometry.centroid
    x, y = c.x.values, c.y.values
    d = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
    if east is not None:
        crossings = crossings or CROSSINGS
        pts = gpd.GeoSeries(gpd.points_from_xy(*zip(*crossings.values())), crs=4326).to_crs(utm)
        via = np.min([np.hypot(x - p.x, y - p.y)[:, None] + np.hypot(x - p.x, y - p.y)[None, :] for p in pts], axis=0)
        e = np.isin(c.index, east)
        other = e[:, None] != e[None, :]
        d = np.where(other, via, d)
    return pd.DataFrame(d / 1000 * road_factor, index=c.index, columns=c.index)


def within(x: np.ndarray, ix, iy, radius_m: float, cell_m: float) -> np.ndarray:
    """For (draws, cells) values on a square grid (cell indices ix, iy): the sum over all cells
    whose centre is within radius_m, per draw. Same disk as balance.add_within."""
    from scipy.signal import fftconvolve

    from geo_anom.task2.balance import _disk

    x = np.atleast_2d(x)
    ix, iy = np.asarray(ix), np.asarray(iy)
    i0, j0 = ix.min(), iy.min()
    a = np.zeros((x.shape[0], iy.max() - j0 + 1, ix.max() - i0 + 1))
    a[:, iy - j0, ix - i0] = x
    k = _disk(radius_m, cell_m)[None]
    s = fftconvolve(a, k, mode="same", axes=(1, 2))
    return np.round(s[:, iy - j0, ix - i0], 6)
