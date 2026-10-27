"""
One county at a time: run the grid, then summarise it the same way everywhere.

Used by notebooks 04 (one county, looked at closely) and 05 (all counties).

    run_county(name)                 grid over the county -> run_pipeline (streamed,
                                     resumable) -> <results>/county_<slug>/
    county_buildings(...)            this county's buildings + distance-to-permit flag
    compare_with_ground_truth(...)   matches / ours-only / missed vs USGS hand tracing
    summarize_county(name)           accuracy + totals -> county_summary.json, one dict

USGS hand tracing (Soroka & Duren) covers the Delmarva peninsula only, so for
western counties accuracy is reported as not available, never as 0%.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from geo_anom.task1 import env, region, tiles
from geo_anom.task1.evaluate import evaluate_run, load_ground_truth
from geo_anom.task1.pipeline import run_pipeline
from geo_anom.task1.tiles import ROOT

UTM = region.UTM
POULTRY_TYPES = ["chickens_not_laying_hens", "laying_hens_dry_manure", "turkeys", "ducks_liquid_manure"]
# Eastern Shore first, ordered by share of Maryland's poultry (AWTF 2019: Worcester,
# Somerset, Wicomico, Caroline ~87% together)
EASTERN_SHORE = ["Worcester", "Somerset", "Wicomico", "Caroline", "Dorchester",
                 "Queen Anne's", "Kent", "Talbot", "Cecil"]
AWTF_CSV = ROOT / "data/reference/awtf_2017_broiler_layer_inventory_by_county.csv"
_AWTF_NAMES = {"St. Mary's": "Saint Mary's", "Baltimore County": "Baltimore", "Baltimore city": None}


def county_names() -> list[str]:
    """Every Maryland county as county_boundary() accepts it (Baltimore County
    and Baltimore city by their full names, the rest by short name)."""
    md = region.md_counties()
    dup = md["NAME"].duplicated(keep=False)
    return sorted(md.loc[~dup, "NAME"].tolist() + md.loc[dup, "NAMELSAD"].tolist())


def all_counties_in_order() -> list[str]:
    rest = [c for c in county_names() if c not in EASTERN_SHORE]
    return EASTERN_SHORE + rest


def slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "").replace(".", "")


def county_out(name: str, root: Path | None = None) -> Path:
    return Path(root or env.results_root()) / f"county_{slug(name)}"


def registry_points() -> gpd.GeoDataFrame:
    reg = tiles.load_registry()
    return gpd.GeoDataFrame(reg, geometry=gpd.points_from_xy([s["lon"] for s in reg], [s["lat"] for s in reg]),
                            crs=4326)


def run_county(name: str, stream: bool = True, max_workers: int = 8, progress=None,
               root: Path | None = None, log=print) -> dict:
    """Map every building in one county. Resumable: re-running continues."""
    county = region.county_boundary(name)
    sites = region.grid_sites(county, name)
    return run_pipeline(sites, county_out(name, root), manifest=tiles.load_registry(),
                        manifest_path=tiles.REGISTRY_SNAPSHOT, prefer="area",
                        stream=stream, max_workers=max_workers, progress=progress, log=log,
                        filters={"farm": [], "county": [name]})


def tile_status(name: str, root: Path | None = None) -> dict:
    """How many of the county's grid tiles have results, have no aerial photo, or are missing."""
    from geo_anom.task1.pipeline import NO_IMAGERY_DIR, shard_name

    out = county_out(name, root)
    grid = region.grid_sites(region.county_boundary(name), name)
    have = lambda d: {p.name for p in (out / d).glob("*.json")} if (out / d).exists() else set()
    done, none_ = have("tiles_done"), have(NO_IMAGERY_DIR)
    missing = [s["grid_id"] for s in grid if shard_name(s) not in done and shard_name(s) not in none_]
    return {"tiles": len(grid), "done": len(done), "no_imagery": len(none_), "missing": missing}


def is_complete(name: str, root: Path | None = None) -> bool:
    """Summarised, and every tile has results or is known to have no aerial photo.

    Until 2026-10-27 only the summary was checked, so tiles that failed (e.g. a
    504 from Planetary Computer) were never retried once a county was summarised.
    """
    out = county_out(name, root)
    if not ((out / "run_meta.json").exists() and (out / "county_summary.json").exists()):
        return False
    return not tile_status(name, root)["missing"]


def load_county_run(out: Path):
    meta = json.loads((out / "run_meta.json").read_text())
    sites_run = json.loads((out / "sites.json").read_text())
    buildings = gpd.read_file(out / "buildings.geojson")
    return meta, sites_run, buildings


def county_buildings(buildings: gpd.GeoDataFrame, county: gpd.GeoDataFrame, near_m: float = 1000) -> gpd.GeoDataFrame:
    """This county's buildings (centroid inside), in UTM, with `near_permit`."""
    b = buildings.to_crs(UTM) if buildings.crs is not None else buildings.set_crs(4326).to_crs(UTM)
    if b.empty:   # a county with no houses (e.g. Calvert) has an empty buildings.geojson with no columns
        b = b.copy()
        b["assigned_distance_m"] = pd.Series(dtype=float)
        b["near_permit"] = pd.Series(dtype=bool)
        return b
    b = b[b.centroid.within(county.to_crs(UTM).unary_union)].copy()
    b["near_permit"] = b["assigned_distance_m"] <= near_m
    return b


def compare_with_ground_truth(b: gpd.GeoDataFrame, gt: gpd.GeoDataFrame, county: gpd.GeoDataFrame) -> dict:
    """Which of our buildings overlap a hand-traced house, and which traced houses we missed."""
    gtc = gt.to_crs(UTM)
    gtc = gtc[gtc.centroid.within(county.to_crs(UTM).unary_union)]
    hit_b = gpd.sjoin(b[["geometry"]], gtc[["geometry"]], predicate="intersects").index.unique()
    hit_g = gpd.sjoin(gtc[["geometry"]], b[["geometry"]], predicate="intersects").index.unique()
    return {"gtc": gtc, "hit_b": hit_b, "hit_g": hit_g,
            "false_pos": b[~b.index.isin(hit_b)], "missed": gtc[~gtc.index.isin(hit_g)]}


def awtf_row(name: str) -> pd.Series:
    awtf = pd.read_csv(AWTF_CSV, comment="#").set_index("county")
    key = _AWTF_NAMES.get(name, name)
    return awtf.loc[key] if key in awtf.index else pd.Series(dtype=float)


def county_totals(name: str, b: gpd.GeoDataFrame, n_traced: int, reg_in: gpd.GeoDataFrame) -> pd.Series:
    row = awtf_row(name)
    pp = reg_in[reg_in.animal_type.isin(POULTRY_TYPES)]
    return pd.Series({
        "poultry houses detected": len(b),
        "  of which within 1 km of a registered permit": int(b.near_permit.sum()),
        "  of which farther": int((~b.near_permit).sum()),
        "hand-traced houses, 2016/17 (USGS)": n_traced,
        "registered poultry permits (MDE)": len(pp),
        "permitted poultry headcount (MDE registry)": int(pp.headcount.sum()),
        "AWTF 2017 inventory, USDA Ag Census (birds)": row.get("ag_census_2017_birds"),
        "AWTF 2017 inventory, MDE CAFO data (birds)": row.get("mde_cafo_2017_birds"),
    }, name=name)


def summarize_county(name: str, root: Path | None = None, gt: gpd.GeoDataFrame | None = None,
                     near_m: float = 1000, write: bool = True) -> dict:
    """Accuracy (where hand tracing exists) + totals for one finished county run."""
    out = county_out(name, root)
    county = region.county_boundary(name)
    meta, _, buildings = load_county_run(out)
    b = county_buildings(buildings, county, near_m)
    gt = gt if gt is not None else load_ground_truth()
    cmp = compare_with_ground_truth(b, gt, county)
    reg = registry_points()
    reg_in = reg[reg.within(county.unary_union)]
    if len(cmp["gtc"]):
        acc = evaluate_run(out, gt=gt, area=county)
        accuracy = {**acc["object_level"], "median_distance_to_traced_house_m": acc["centroid_distance_m"]["median"],
                    "far_from_permit_on_traced_house": int(b[~b.near_permit].index.isin(cmp["hit_b"]).sum())}
    else:
        accuracy = None   # no hand tracing here (outside Delmarva)
    totals = county_totals(name, b, len(cmp["gtc"]), reg_in)
    summary = {"county": name, "run": meta, "accuracy": accuracy,
               "totals": {k.strip(): (None if pd.isna(v) else float(v)) for k, v in totals.items()}}
    if write:
        (out / "county_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def summary_row(summary: dict) -> dict:
    """One flat row for the statewide table."""
    t, a, m = summary["totals"], summary["accuracy"], summary["run"]
    return {
        "county": summary["county"],
        "tiles": m.get("tiles"),
        "houses detected": t["poultry houses detected"],
        "near a permit": t["of which within 1 km of a registered permit"],
        "far from permits": t["of which farther"],
        "hand-traced (2016/17)": t["hand-traced houses, 2016/17 (USGS)"],
        "precision": a["precision"] if a else None,
        "recall": a["recall"] if a else None,
        "poultry permits": t["registered poultry permits (MDE)"],
        "permitted birds": t["permitted poultry headcount (MDE registry)"],
        "AWTF Census birds 2017": t["AWTF 2017 inventory, USDA Ag Census (birds)"],
        "AWTF MDE birds 2017": t["AWTF 2017 inventory, MDE CAFO data (birds)"],
        "code": m.get("git_commit"),
    }
