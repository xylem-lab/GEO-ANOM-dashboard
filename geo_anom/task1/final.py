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


def load_sam(path: Path, rule: dict | None = SAM_RULE) -> gpd.GeoDataFrame:
    """SAM shapes with length / width / aspect, best score first; only those passing `rule`
    (None = all of them)."""
    from geo_anom.task1.detect import polygon_stats

    rec = [json.loads(line) for line in open(path)]
    S = gpd.GeoDataFrame([{"kind": r["kind"], "sam_score": r["sam_score"], "geometry": shape(r["geometry"])} for r in rec],
                         geometry="geometry", crs=UTM)
    if not len(S):
        return S
    st = pd.DataFrame([polygon_stats(g) for g in S.geometry], index=S.index)
    S["length_m"], S["width_m"], S["aspect"] = st.length_m, st.width_m, st.aspect
    S = S.sort_values("sam_score", ascending=False, kind="stable")
    return passes(S, rule) if rule else S


def passes(S: gpd.GeoDataFrame, rule: dict) -> gpd.GeoDataFrame:
    return S[(S.length_m >= rule["length_min"]) & (S.width_m <= rule["width_max"]) & (S.aspect >= rule["aspect_min"])]


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


def detector_and_bright(n: str, bright_root: Path | None, root: Path | None = None):
    """(published model's outlines, + brightened-photo houses) for county `n`, raw outlines."""
    cty = region.county_boundary(n); cu = cty.to_crs(UTM).unary_union
    _, _, bld = C.load_county_run(C.county_out(n, root))
    O = C.county_buildings(bld, cty)[["geometry"]].reset_index(drop=True).assign(source="detector")
    T = gpd.GeoDataFrame(geometry=[], crs=UTM)
    if bright_root is not None and (Path(bright_root) / C.county_out(n).name / "buildings.geojson").exists():
        t = gpd.read_file(Path(bright_root) / C.county_out(n).name / "buildings.geojson").to_crs(UTM)
        T = t[t.centroid.within(cu)][["geometry"]]
    return O, add_new(O, T, "brightened photo")


def build_steps(n: str, sam: gpd.GeoDataFrame, bright_root: Path | None, road_cache: Path | None = None,
                rejected: gpd.GeoDataFrame | None = None, confirmed_new: gpd.GeoDataFrame | None = None,
                root: Path | None = None) -> dict:
    """The layers (UTM, column `source`) for county `n`: STEPS, plus TESTED when `road_cache`
    is given. Steps 1-3 reproduce final map v1 exactly: new shapes are matched against the
    raw outlines, rectangles drawn at the end."""
    cty = region.county_boundary(n); cu = cty.to_crs(UTM).unary_union
    O, OT = detector_and_bright(n, bright_root, root)
    S = sam[sam.centroid.within(cu)] if len(sam) else sam
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


# ── correcting the map for the houses it misses ───────────────────────────────

# Missed traced houses checked by eye on 2023 photos (notebook 05/08 miss audit, 2026-10):
# 21 of 24 were still standing, 3 were gone.
STILL_STANDING = (21, 24)


def miss_correction(mapped: gpd.GeoDataFrame, gt: gpd.GeoDataFrame, counties: list[str] = C.EASTERN_SHORE,
                    standing: tuple = STILL_STANDING, unconfirmed: float = 0.03) -> pd.DataFrame:
    """Estimated real roof and houses per county, adding the traced houses the map misses.

    For each county (inside the USGS tracing):
      missed            traced houses no outline touches
      missed_area_m2    their traced footprint (missed houses are smaller than found ones)
      k                 outline roof / traced footprint on the houses we do find (outline size)
      s                 share of missed houses still standing in 2023 (by eye, Wilson 95% range)
      added roof        = missed_area_m2 x k x s
    low  = s at its lower bound, less the share of outlines not confirmed (`unconfirmed`)
    high = s at its upper bound.  Houses outside the tracing (e.g. west of the Bay) are not corrected."""
    from geo_anom.task1.review import wilson
    k_, n_ = standing
    s = {"low": wilson(k_, n_)[0], "mid": k_ / n_, "high": wilson(k_, n_)[1]}
    m = mapped.to_crs(UTM).reset_index(drop=True)
    rows = []
    for n in counties:
        cu = region.county_boundary(n).to_crs(UTM).unary_union
        g_ = gt[gt.centroid.within(cu)].reset_index(drop=True)
        mc = m[m.centroid.within(cu)]
        j = gpd.sjoin(g_[["geometry"]], mc[["geometry"]], predicate="intersects")
        hit = g_.index.isin(j.index)
        area = g_.geometry.area
        k = mc.loc[mc.index.isin(j.index_right)].geometry.area.sum() / area[hit].sum() if hit.any() else 1.0
        r = {"county": n, "traced": len(g_), "found": int(hit.sum()), "missed": int((~hit).sum()),
             "found_area_mean_m2": area[hit].mean(), "missed_area_mean_m2": area[~hit].mean(),
             "missed_area_m2": area[~hit].sum(), "k": k,
             "mapped_houses": len(mc), "mapped_roof_m2": mc.geometry.area.sum()}
        rows.append(r)
    T = pd.DataFrame(rows).set_index("county")
    tot = T[["traced", "found", "missed", "missed_area_m2", "mapped_houses", "mapped_roof_m2"]].sum()
    tot["found_area_mean_m2"] = (T.found_area_mean_m2 * T.found).sum() / T.found.sum()
    tot["missed_area_mean_m2"] = T.missed_area_m2.sum() / T.missed.sum()
    tot["k"] = (T.k * T.found).sum() / T.found.sum()
    T.loc["Eastern Shore"] = tot
    for lv, sv in s.items():
        add = T.missed_area_m2 * T.k * sv
        base = T.mapped_roof_m2 * (1 - unconfirmed) if lv == "low" else T.mapped_roof_m2
        T[f"roof_m2_{lv}"] = base + add
        T[f"houses_{lv}"] = T.mapped_houses * ((1 - unconfirmed) if lv == "low" else 1) + T.missed * sv
    T["still_standing"] = f"{k_}/{n_} ({s['low']:.2f}-{s['high']:.2f})"
    T["added_share_mid"] = T.roof_m2_mid / T.mapped_roof_m2 - 1
    return T


def freeze(files: dict, out: Path, meta: dict) -> dict:
    """Write MANIFEST.json (SHA-256 of every released file + run facts) next to the files."""
    man = {"made_at": pd.Timestamp.now().isoformat(timespec="seconds"), **meta,
           "files": {name: env.sha256(Path(p)) for name, p in files.items()}}
    (Path(out) / "MANIFEST.json").write_text(json.dumps(man, indent=2, default=str))
    return man


# ── the SAM shape rule, chosen fairly ──────────────────────────────────────────

FOLDS = {"A": ["Worcester", "Caroline", "Dorchester", "Kent", "Cecil"],
         "B": ["Wicomico", "Somerset", "Queen Anne's", "Talbot"]}
RULE_GRID = {"length_min": [60, 70, 80, 90, 100], "width_max": [20, 25, 30], "aspect_min": [3, 4, 5, 6, 7]}


def sam_rule_scores(sam_all: gpd.GeoDataFrame, bright_root: Path | None, gt: gpd.GeoDataFrame,
                    confirmed: gpd.GeoDataFrame | None = None, counties: list[str] = C.EASTERN_SHORE,
                    grid: dict = RULE_GRID, root: Path | None = None) -> pd.DataFrame:
    """Every rule in `grid` (plus 'no SAM') scored per county, as step 3 would be with it:
    one row per (rule, county) with traced / found / detections / on_traced / confirmed."""
    import itertools
    rules = [None] + [dict(zip(grid, v)) for v in itertools.product(*grid.values())]
    rows = []
    for n in counties:
        cu = region.county_boundary(n).to_crs(UTM).unary_union
        gtc = gt[gt.centroid.within(cu)].reset_index(drop=True)
        ext = traced_extent(gtc, cu)
        _, OT = detector_and_bright(n, bright_root, root)
        Sn = sam_all[sam_all.centroid.within(cu)]
        for r in rules:
            lay = rect(add_new(OT, passes(Sn, r), "SAM repair")) if r else rect(OT)
            s = score(lay, gtc, ext, confirmed)
            rows.append({"rule": "no SAM" if r is None else f"L>={r['length_min']} W<={r['width_max']} A>={r['aspect_min']}",
                         **(r or {}), "county": n, "traced": len(gtc), **s})
    return pd.DataFrame(rows)


def summarize_rules(scores: pd.DataFrame, counties: list[str]) -> pd.DataFrame:
    """Per rule over `counties`: recall, precision (checked by eye), F1."""
    d = scores[scores.county.isin(counties)].groupby("rule", sort=False)[
        ["traced", "found", "detections", "on_traced", "confirmed"]].sum()
    d["recall"] = d.found / d.traced
    d["precision_checked"] = (d.on_traced + d.confirmed) / d.detections
    d["f1"] = 2 * d.recall * d.precision_checked / (d.recall + d.precision_checked)
    return d


def cross_validate_rule(scores: pd.DataFrame, folds: dict = FOLDS, current: str = "L>=80 W<=25 A>=5") -> pd.DataFrame:
    """Choose the rule with the best F1 on one fold, report it on the other; next to the rule
    in use (chosen on all counties), no SAM, and the best rule in hindsight on the test fold."""
    rows = []
    for test, tune in [("B", "A"), ("A", "B")]:
        chosen = summarize_rules(scores, folds[tune]).f1.idxmax()
        on_test = summarize_rules(scores, folds[test])
        for label, rule in [("no SAM", "no SAM"), (f"chosen on fold {tune}", chosen), ("rule in use", current),
                            ("best on test fold (hindsight)", on_test.f1.idxmax())]:
            r = on_test.loc[rule]
            rows.append({"test fold": f"{test}: " + ", ".join(folds[test]), "rule from": label, "rule": rule,
                         "recall": r.recall, "precision_checked": r.precision_checked, "f1": r.f1, "found": int(r.found)})
    return pd.DataFrame(rows)
