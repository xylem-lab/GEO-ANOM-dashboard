"""
Task 1, final: the published model and each improvement on top of it, one step at a time
(notebooks 11-13). Everything is rebuilt from result folders on the shared drive.

    The ladder (Eastern Shore; each step adds to the one before):
      0  published model     Robinson et al. (2022) U-Net + Tulbure shape filter (notebook 05 runs)
      1  rectangle outlines  each outline replaced by its minimum rotated rectangle
                             (the U-Net covers ~78% of a roof; the rectangle ~97%)
      2  brightened photo    houses found when the two darkest 2023 flights are rerun with the
                             photo tone-matched to 2021 (notebook 08)
      3  SAM repair          short rejected pieces / merged blobs grown or split into whole houses
                             by Segment Anything, kept only if house-shaped (>= 80 m long,
                             <= 25 m wide, aspect >= 5)             -> = final map v1 (2,823)
      4  checked by eye      drop detections every reviewer called "not poultry" (notebook 07);
                             add houses confirmed by eye that only the fine-tuned model found
                             (notebook 07 section 7)                 -> final map (frozen)

    Tested, not adopted (scored on the same footing, kept out of the map):
      road rule              drop outlines whose centre is < 20 m from an OpenStreetMap road --
                             fixes the fine-tuned model's road detections, but on this map it
                             removes real houses built close to a road
      fine-tuned model       notebook 10 (held-out counties; its own comparison)

    sam_pieces / sam_recover   the SAM step (resumable; ~30 min on a laptop CPU)
    build_steps(county)        the six layers for one county
    score(layer, traced, ...)  detections, houses found, precision (vs tracing and with the
                               eye-check labels), roof area, how much of each traced roof
                               the outline covers
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import mapping, shape

from geo_anom.task1 import county as C
from geo_anom.task1 import env, region

UTM = region.UTM
STEPS = ["published model", "rectangle outlines", "brightened photo", "SAM repair", "checked by eye"]
TESTED = ["road rule (not adopted)"]
OVERLAP = 0.3            # a new outline is a different house if it overlaps every existing one < 30%
SAM_RULE = {"length_min": 80.0, "width_max": 25.0, "aspect_min": 5.0}
ROAD_M = 20.0


def final_dir(root: Path | None = None) -> Path:
    return Path(root or env.results_root()) / "final"


# ── SAM repair ─────────────────────────────────────────────────────────────────

def sam_pieces(counties: list[str] = C.EASTERN_SHORE, root: Path | None = None, cell_m: float = 300.0) -> gpd.GeoDataFrame:
    """Rejected pieces worth growing: short fragments (10-55 m long) and blobs too big or
    too wide to be one house -- unless mostly inside a house already kept."""
    parts, kept = [], []
    for n in counties:
        out = C.county_out(n, root)
        _, sites, bld = C.load_county_run(out)
        items = {s["tile_path"]: s.get("naip_item_ids") for s in sites}
        cand = gpd.read_file(out / "candidates.geojson").to_crs(UTM)
        kept.append(C.county_buildings(bld, region.county_boundary(n))[["geometry"]])
        r = cand[~cand.kept].copy()
        frag = r[(r.length_m >= 10) & (r.length_m < 55) & (r.width_m >= 4)].assign(kind="fragment")
        big = r[((r.area_m2 > 7500) | (r.width_m > 30)) & (r.length_m <= 400)].assign(kind="merged")
        x = pd.concat([frag, big])
        x["county"] = n
        x["items"] = x.tile_path.map(items)
        parts.append(x)
    P = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=UTM)
    K = gpd.GeoDataFrame(pd.concat(kept, ignore_index=True), crs=UTM)
    inside = gpd.sjoin(P[["geometry"]], K, predicate="intersects")
    cov = {}
    for i, j in zip(inside.index, inside.index_right):
        cov[i] = max(cov.get(i, 0), P.geometry[i].intersection(K.geometry[j]).area / max(P.geometry[i].area, 1e-6))
    P = P[[cov.get(i, 0) < 0.5 for i in P.index]]
    P["key"] = [f"{round(g.centroid.x / 5)}_{round(g.centroid.y / 5)}" for g in P.geometry]
    P = P.drop_duplicates("key")
    c = P.geometry.centroid
    P["cell"] = [f"{int(x // cell_m)}_{int(y // cell_m)}" for x, y in zip(c.x, c.y)]
    return P


def sam_recover(out_dir: Path, counties: list[str] = C.EASTERN_SHORE, root: Path | None = None,
                cell_m: float = 300.0, window_m: float = 600.0, workers: int = 6, device: str | None = None,
                log=print) -> Path:
    """Run SAM on every piece (one 600 m photo per 300 m cell, same NAIP items as the run).
    Appends to out_dir/recovered.jsonl; cells done are listed in done_cells.txt (resumable)."""
    from geo_anom.task1 import tiles
    from geo_anom.task1.refine import SamRefiner

    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    P = sam_pieces(counties, root, cell_m)
    done_f, rec_f = out_dir / "done_cells.txt", out_dir / "recovered.jsonl"
    done = set(done_f.read_text().split()) if done_f.exists() else set()
    cells = [k for k in P.cell.unique() if k not in done]
    log(f"{len(P)} pieces {P.kind.value_counts().to_dict()} in {P.cell.nunique()} windows; {len(cells)} to do")
    if not cells:
        return rec_f
    sam = SamRefiner(device=device)

    def fetch(cell):
        g = P[P.cell == cell]
        cx, cy = [(int(v) + 0.5) * cell_m for v in cell.split("_")]
        lon, lat = gpd.GeoSeries(gpd.points_from_xy([cx], [cy]), crs=UTM).to_crs(4326).iloc[0].coords[0]
        ids = g["items"].dropna().iloc[0] if g["items"].notna().any() else None
        try:
            return cell, tiles.fetch_window(lon, lat, window_m, item_ids=list(ids) if ids is not None else None)
        except Exception as e:  # noqa: BLE001 -- recorded, the cell is retried on the next run
            return cell, e

    t0, n_new = time.time(), 0
    with ThreadPoolExecutor(workers) as ex:
        for k, (cell, got) in enumerate(ex.map(fetch, cells)):
            if isinstance(got, Exception):
                log(f"  {cell}: {got} (will retry next run)")
                continue
            recs = []
            if got is not None:
                img, t, crs = got
                sam.set_image(img[..., :3], t, key=cell)
                for _, r in P[P.cell == cell].iterrows():
                    g = gpd.GeoSeries([r.geometry], crs=UTM).to_crs(crs).iloc[0]
                    found = [sam.recover_fragment(g)] if r.kind == "fragment" else sam.split_merged(g)
                    for f in found:
                        if f:
                            poly = gpd.GeoSeries([f[0]], crs=crs).to_crs(UTM).iloc[0]
                            recs.append(dict(kind=r.kind, county=r.county, src=r.candidate_id, sam_score=f[1],
                                             geometry=mapping(poly)))
            with open(rec_f, "a") as fh:
                for x in recs:
                    fh.write(json.dumps(x) + "\n")
            with open(done_f, "a") as fh:
                fh.write(cell + "\n")
            n_new += len(recs)
            if k % 50 == 0:
                log(f"{k + 1}/{len(cells)} windows, {n_new} shapes, {time.time() - t0:.0f} s")
    log(f"finished: {n_new} shapes in {time.time() - t0:.0f} s")
    return rec_f


def load_sam(path: Path, rule: dict = SAM_RULE) -> gpd.GeoDataFrame:
    """SAM shapes that pass the strict house rule, best score first."""
    from geo_anom.task1.detect import polygon_stats

    rec = [json.loads(line) for line in open(path)]
    S = gpd.GeoDataFrame([{"kind": r["kind"], "sam_score": r["sam_score"], "geometry": shape(r["geometry"])} for r in rec],
                         geometry="geometry", crs=UTM)
    if not len(S):
        return S
    st = [polygon_stats(g) for g in S.geometry]
    ok = [x["length_m"] >= rule["length_min"] and x["width_m"] <= rule["width_max"] and x["aspect"] >= rule["aspect_min"]
          for x in st]
    return S[ok].sort_values("sam_score", ascending=False, kind="stable")


# ── building the layers ────────────────────────────────────────────────────────

def add_new(base: gpd.GeoDataFrame, new: gpd.GeoDataFrame, tag: str, overlap: float = OVERLAP) -> gpd.GeoDataFrame:
    """Append the rows of `new` that overlap nothing already there (< `overlap` of the smaller)."""
    keep, geoms = [], list(base.geometry)
    for g in new.geometry:
        if all(g.intersection(b).area < overlap * min(g.area, b.area) for b in geoms if b.intersects(g)):
            keep.append(g); geoms.append(g)
    return pd.concat([base, gpd.GeoDataFrame({"source": tag, "geometry": keep}, geometry="geometry", crs=UTM)],
                     ignore_index=True)


def rect(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    out["geometry"] = out.geometry.apply(lambda g: g.minimum_rotated_rectangle)
    return out


def build_steps(n: str, sam: gpd.GeoDataFrame, bright_root: Path | None, road_cache: Path | None = None,
                rejected: gpd.GeoDataFrame | None = None, confirmed_new: gpd.GeoDataFrame | None = None,
                root: Path | None = None) -> dict:
    """The layers (UTM, column `source`) for county `n`: STEPS, plus TESTED when `road_cache`
    is given. Steps 1-3 reproduce final map v1 exactly: new shapes are matched against the
    raw outlines, rectangles drawn at the end."""
    cty = region.county_boundary(n); cu = cty.to_crs(UTM).unary_union
    _, _, bld = C.load_county_run(C.county_out(n, root))
    O = C.county_buildings(bld, cty)[["geometry"]].reset_index(drop=True).assign(source="detector")
    T = gpd.GeoDataFrame(geometry=[], crs=UTM)
    if bright_root is not None and (Path(bright_root) / C.county_out(n).name / "buildings.geojson").exists():
        t = gpd.read_file(Path(bright_root) / C.county_out(n).name / "buildings.geojson").to_crs(UTM)
        T = t[t.centroid.within(cu)][["geometry"]]
    S = sam[sam.centroid.within(cu)] if len(sam) else sam
    OT = add_new(O, T, "brightened photo")
    OTS = add_new(OT, S, "SAM repair")
    L = {"published model": O, "rectangle outlines": rect(O), "brightened photo": rect(OT), "SAM repair": rect(OTS)}
    cur = L["SAM repair"]
    if road_cache is not None:
        from geo_anom.task1.detect import distance_to_roads
        d = distance_to_roads(cur, road_cache, bounds=cty.to_crs(4326).total_bounds)
        L["road rule (not adopted)"] = cur[d.values >= ROAD_M].reset_index(drop=True)
    if rejected is not None and len(rejected):
        bad = set(gpd.sjoin(cur[["geometry"]], rejected.to_crs(UTM)[["geometry"]], predicate="intersects").index)
        cur = cur.drop(index=list(bad)).reset_index(drop=True)
    if confirmed_new is not None and len(confirmed_new):
        cn = confirmed_new.to_crs(UTM)
        cur = add_new(cur, rect(cn[cn.centroid.within(cu)][["geometry"]]), "checked by eye (fine-tuned model)")
    L["checked by eye"] = cur
    for k in L:
        L[k] = L[k].assign(county=n)
    return L


# ── scoring ────────────────────────────────────────────────────────────────────

def traced_extent(gtc: gpd.GeoDataFrame, county_union):
    """Where USGS traced: convex hull of the county's traced houses + 500 m, inside the county
    (detections outside it can't be checked against the tracing)."""
    return gtc.unary_union.convex_hull.buffer(500).intersection(county_union)


def score(layer: gpd.GeoDataFrame, gtc: gpd.GeoDataFrame, extent, confirmed: gpd.GeoDataFrame | None = None) -> dict:
    """Scored inside the traced extent.
    found         traced houses touched by an outline
    on_traced     outlines touching a traced house
    confirmed     other outlines touching a house confirmed by eye (07)
    roof_m2       total outline area (whole county)
    cover         median share of a traced roof covered by the outline that touches it most"""
    b = layer[layer.centroid.within(extent)].reset_index(drop=True)
    out = {"houses": len(layer), "roof_m2": float(layer.geometry.area.sum()), "detections": len(b)}
    if not len(b):
        return {**out, "found": 0, "on_traced": 0, "confirmed": 0, "cover": np.nan}
    j = gpd.sjoin(b[["geometry"]], gtc[["geometry"]], predicate="intersects")
    on = set(j.index)
    conf = set()
    if confirmed is not None and len(confirmed):
        conf = set(gpd.sjoin(b[["geometry"]], confirmed.to_crs(UTM)[["geometry"]], predicate="intersects").index) - on
    best = {}
    for i, k in zip(j.index, j.index_right):
        c = b.geometry[i].intersection(gtc.geometry[k]).area / gtc.geometry[k].area
        best[k] = max(best.get(k, 0), c)
    return {**out, "found": j.index_right.nunique(), "on_traced": len(on), "confirmed": len(conf),
            "cover": float(np.median(list(best.values()))) if best else np.nan}


def ladder(layers: dict, gt: gpd.GeoDataFrame, confirmed: gpd.GeoDataFrame | None = None) -> pd.DataFrame:
    """One row per (county, step) plus an 'Eastern Shore' total per step.
    layers = {county: build_steps(county, ...)}."""
    rows = []
    for n, L in layers.items():
        cu = region.county_boundary(n).to_crs(UTM).unary_union
        gtc = gt[gt.centroid.within(cu)].reset_index(drop=True)
        ext = traced_extent(gtc, cu)
        for step in [s for s in STEPS + TESTED if s in L]:
            rows.append({"county": n, "step": step, "traced": len(gtc), **score(L[step], gtc, ext, confirmed)})
    T = pd.DataFrame(rows)
    tot = T.groupby("step", sort=False)[["traced", "houses", "roof_m2", "detections", "found", "on_traced", "confirmed"]].sum()
    tot["cover"] = T.groupby("step", sort=False)["cover"].median()
    T = pd.concat([T, tot.reset_index().assign(county="Eastern Shore")], ignore_index=True)
    T["recall"] = T.found / T.traced
    T["precision_vs_tracing"] = T.on_traced / T.detections
    T["precision_checked"] = (T.on_traced + T.confirmed) / T.detections
    T["roof_km2"] = T.roof_m2 / 1e6
    T["step_no"] = T.step.map({s: i for i, s in enumerate(STEPS)})          # NaN = tested, not adopted
    return T


# ── validation: does the mapped roof hold the birds Maryland reports? ──────────

FT2_PER_M2 = 10.7639
# (low, mid, high). Floor = roof footprint less eaves; density = birds per ft2 of floor when a
# flock is placed (NCC guidelines 6.5-9 lb/ft2 at market weight, Delmarva birds ~6-7.3 lb);
# occupancy = share of days a house holds birds (5-6 flocks a year with 2-3 weeks between).
ASSUMPTIONS = {
    "floor_share": (0.90, 0.93, 0.96),
    "birds_per_ft2": (0.90, 1.10, 1.30),
    "occupancy": (0.70, 0.80, 0.90),
    "flocks_per_year": (5.0, 5.5, 6.0),
}
DCA_2024 = {"birds": 601e6, "houses": 4909}   # Delmarva Chicken Association, 2024 facts


def capacity(roof_m2, a: dict = ASSUMPTIONS) -> dict:
    """Birds the mapped roof can hold at once (low/mid/high)."""
    ft2 = np.asarray(roof_m2, float) * FT2_PER_M2
    return {k: ft2 * a["floor_share"][i] * a["birds_per_ft2"][i] for i, k in enumerate(["low", "mid", "high"])}


def validation_table(final: gpd.GeoDataFrame, awtf: pd.DataFrame, permits: pd.DataFrame, a: dict = ASSUMPTIONS) -> pd.DataFrame:
    """Per county: houses, roof, capacity from the roof (range) vs MDE permitted capacity; birds
    on hand (capacity x occupancy) vs the 2017 Census of Agriculture inventory; birds a year vs
    houses x the DCA average per house."""
    g = final.to_crs(UTM).assign(roof_m2=lambda d: d.geometry.area).groupby("county")
    T = pd.DataFrame({"houses": g.size(), "roof_m2": g.roof_m2.sum()})
    cap = capacity(T.roof_m2, a)
    for k in cap:
        T[f"capacity_{k}"] = cap[k]
    T["mde_permitted"] = permits.reindex(T.index)
    lo, mid, hi = (T.capacity_low * a["occupancy"][0], T.capacity_mid * a["occupancy"][1], T.capacity_high * a["occupancy"][2])
    T["on_hand_low"], T["on_hand_mid"], T["on_hand_high"] = lo, mid, hi
    T["census2017_on_hand"] = awtf["ag_census_2017_birds"].reindex(T.index)
    T["mde_cafo2017_on_hand"] = awtf["mde_cafo_2017_birds"].reindex(T.index)
    T["per_year_mid"] = T.capacity_mid * a["flocks_per_year"][1]
    T["per_year_dca_avg"] = T.houses * DCA_2024["birds"] / DCA_2024["houses"]
    T.loc["Total"] = T.sum(numeric_only=True)
    return T


def freeze(files: dict, out: Path, meta: dict) -> dict:
    """Write MANIFEST.json (SHA-256 of every released file + run facts) next to the files."""
    man = {"made_at": pd.Timestamp.now().isoformat(timespec="seconds"), **meta,
           "files": {name: env.sha256(Path(p)) for name, p in files.items()}}
    (Path(out) / "MANIFEST.json").write_text(json.dumps(man, indent=2, default=str))
    return man
