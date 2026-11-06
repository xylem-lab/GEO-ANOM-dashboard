"""
Task 1 accuracy assessment by design (notebook 14).

Protocol: docs/TASK1_ACCURACY_PROTOCOL.md (its SHA-256 goes into every saved file's meta).
Replaces the single-reviewer 97% precision and the informal 21/24 still-standing check.

    frames(release, traced)     every map outline and traced house in its stratum, + 1 km cells
      S1  map outline touching a traced house          (inside the traced extent)
      S2  map outline touching no traced house          (inside the traced extent)
      S3  map outline outside the traced extent        (30 Eastern Shore + 26 west: census)
      S4  traced house no map outline touches
      S6  1 km Eastern Shore cells: A contains a known house, B within 1 km of one, C farther
    draw(objects, cells, sizes, seed)   stratified random sample by county; every stratum and
                                county is a full random permutation, so the next items are the
                                reserve and the last ones are the calibration set
    chip2023 / render_object / render_cell   blind photos: NAIP 2023 only, crosshair, no outline
    Store, label_ui, cell_ui    append-only labels per interpreter
    agreement / adjudication_queue / final_labels
    estimate(...)               stratified estimators, bootstrap 95% CIs

  Addendum (verification protocol v1.1, statewide; drawn after the first sample, own seed):
    frames_west(...)            S7 western notebook-05 detections on no release outline (census),
                                S8 cells around western poultry permits (census), S6W-A/B western cells
    load_footprints / frames_footprints   S5 Microsoft footprint candidates: S5ES, and west split by
                                building density into S5WR (rural) and S5WD (developed); k_f
    draw_addendum(...)          new strata only, seed 20261106, refuses if a new key has a label
    known_layer(...)            every known building drawn on cell photos
    capture_rates(...)          q for the model residual (geometry only)

Keys: "map:<house_id>", "usgs:<row in the SHA-checked tracing>", "cell:<x>_<y>" (UTM 18N km),
"w05:<candidate_id>" (western notebook-05 detection), "msfp:<row in the footprint file>".
Everything that names a place is saved to the shared drive only (`acc_dir()`).
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from geo_anom.task1 import county as C
from geo_anom.task1 import env, region

UTM = region.UTM
ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs" / "TASK1_ACCURACY_PROTOCOL.md"
VERSION = "accuracy_v1"
YEAR = "2023"

LABELS = ["house", "gone", "under construction", "not a house", "unsure"]
CELL_COUNTS = ["0", "1", "2", "3", "4", "5", "6+"]
V11_OBJECT = ["S1", "S2", "S3", "S4"]
V11_CELL = ["S6A", "S6B", "S6C"]
NEW_OBJECT = ["S5ES", "S5WR", "S5WD", "S7"]        # addendum
NEW_CELL = ["S8", "S6WA", "S6WB"]                  # addendum
OBJECT_STRATA = V11_OBJECT + NEW_OBJECT           # new strata last: the v1.1 draw consumes the same random numbers
CELL_STRATA = V11_CELL + NEW_CELL
RESIDUAL_CELLS = ["S6A", "S6B", "S6C", "S6WA", "S6WB"]
STRATUM_NAMES = {
    "S1": "map outline on a traced house", "S2": "map outline, not traced", "S3": "map outline outside tracing",
    "S4": "traced house, not mapped", "S6A": "cell with a known house", "S6B": "cell within 1 km",
    "S6C": "cell farther than 1 km",
    "S5ES": "footprint candidate, Eastern Shore", "S5WR": "footprint candidate, west, rural",
    "S5WD": "footprint candidate, west, developed",
    "S7": "western detection, not on the map", "S8": "western cell near a poultry permit",
    "S6WA": "western cell with a known building", "S6WB": "western cell within 1 km",
}
# protocol sample sizes (None = all); n >= N -> all
SIZES = {"S1": 100, "S2": 150, "S3": None, "S4": 150, "S6A": 150, "S6B": 150, "S6C": 100,
         "S5ES": 150, "S5WR": 170, "S5WD": 30, "S7": None, "S8": None, "S6WA": 40, "S6WB": 60}
RURAL_DENSITY = 100        # footprints per 1 km cell: below -> S5WR (rural), else S5WD (developed)
ASSUMED_ZERO = ("S5WD",)   # protocol: developed land holds no poultry houses -- stated assumption, spot-checked
SEED_V12 = 20261106
REGISTRY = ROOT / "data" / "reference" / "mde_afo_registry_snapshot.json"
POULTRY_PERMITS = ["chickens_not_laying_hens", "laying_hens_dry_manure", "turkeys", "ducks_liquid_manure"]
FOOTPRINT_RULE = {"length_min": 60.0, "aspect_min": 4.0}
OTHER_FORM = "poultry, other form"
PILOT = {"S1": 25, "S2": 25, "S4": 25}
CALIBRATION = {"S1": 10, "S2": 10, "S4": 10}
MIN_PER_COUNTY = 5
CELL_M = 1000.0
NEAR_M = 1000.0


def acc_dir(root: Path | None = None) -> Path:
    d = (root or env.results_root()) / VERSION
    d.mkdir(parents=True, exist_ok=True)
    return d


def sha256_file(path: Path) -> str:
    return env.sha256(Path(path))


# ── frames ─────────────────────────────────────────────────────────────────────

def traced_extent(gtc: gpd.GeoDataFrame, county_union):
    """Same rule as final.traced_extent: hull of the county's traced houses + 500 m, inside the county."""
    return gtc.unary_union.convex_hull.buffer(500).intersection(county_union)


def frames(release: gpd.GeoDataFrame, traced: gpd.GeoDataFrame, counties: list = None,
           boundaries: dict | None = None) -> tuple:
    """(objects, cells, k) for the strata above.

    release      frozen map (house_id, county, geometry); any CRS
    traced       USGS tracing (any CRS), one polygon per row, index = key
    boundaries   {county: shapely geometry in UTM}; default region.county_boundary
    k            {county: outline area / traced area on S1 pairs} (outline size, for the roof of S4)"""
    counties = list(counties or C.EASTERN_SHORE)
    if boundaries is None:
        boundaries = {n: region.county_boundary(n).to_crs(UTM).unary_union for n in counties}
    m = release.to_crs(UTM).reset_index(drop=True)
    g = traced.to_crs(UTM)
    objs, k = [], {}
    in_es = np.zeros(len(m), bool)
    known = []
    for n in counties:
        cu = boundaries[n]
        gtc = g[g.centroid.within(cu)]
        ext = traced_extent(gtc, cu) if len(gtc) else cu.buffer(0).difference(cu)
        mc = m[(m.county == n)]
        in_es[mc.index] = True
        j = gpd.sjoin(mc[["geometry"]], gtc[["geometry"]], predicate="intersects")
        on = mc.index.isin(j.index)
        inside = mc.centroid.within(ext).values
        for code, sel in (("S1", inside & on), ("S2", inside & ~on), ("S3", ~inside)):
            part = mc[sel]
            objs.append(pd.DataFrame({"key": "map:" + part.house_id.astype(str), "stratum": code, "county": n,
                                      "area_m2": part.geometry.area.values, "geometry": part.geometry.values}))
        # S4: traced houses no outline (any county) touches
        jt = gpd.sjoin(gtc[["geometry"]], m[["geometry"]], predicate="intersects")
        miss = gtc[~gtc.index.isin(jt.index)]
        objs.append(pd.DataFrame({"key": "usgs:" + miss.index.astype(str), "stratum": "S4", "county": n,
                                  "area_m2": miss.geometry.area.values, "geometry": miss.geometry.values}))
        hit = gtc.index.isin(j.index_right)
        k[n] = float(mc.geometry[on].area.sum() / gtc.geometry[hit].area.sum()) if hit.any() else 1.0
        known += [mc.geometry, gtc.geometry]
    west = m[~in_es]
    objs.append(pd.DataFrame({"key": "map:" + west.house_id.astype(str), "stratum": "S3", "county": west.county.values,
                              "area_m2": west.geometry.area.values, "geometry": west.geometry.values}))
    objects = gpd.GeoDataFrame(pd.concat(objs, ignore_index=True), geometry="geometry", crs=UTM)
    objects = _lonlat(objects)

    # 1 km cells on a fixed grid (multiples of 1 km in UTM 18N), kept if the centre is in a county
    known = gpd.GeoDataFrame(geometry=pd.concat(known, ignore_index=True), crs=UTM)
    rows = []
    for n in counties:
        cu = boundaries[n]
        x0, y0, x1, y1 = cu.bounds
        xs = np.arange(np.floor(x0 / CELL_M) * CELL_M, x1, CELL_M)
        ys = np.arange(np.floor(y0 / CELL_M) * CELL_M, y1, CELL_M)
        cand = gpd.GeoDataFrame({"x": np.repeat(xs, len(ys)), "y": np.tile(ys, len(xs))},
                                geometry=[box(x, y, x + CELL_M, y + CELL_M) for x in xs for y in ys], crs=UTM)
        cand = cand[cand.centroid.within(cu)]
        cand["county"] = n
        rows.append(cand)
    cells = gpd.GeoDataFrame(pd.concat(rows, ignore_index=True), crs=UTM)
    cells["key"] = [f"cell:{int(x // 1000)}_{int(y // 1000)}" for x, y in zip(cells.x, cells.y)]
    a = set(gpd.sjoin(cells[["geometry"]], known, predicate="intersects").index)
    near = known.copy(); near["geometry"] = near.buffer(NEAR_M)
    b = set(gpd.sjoin(cells[["geometry"]], near, predicate="intersects").index) - a
    cells["stratum"] = ["S6A" if i in a else "S6B" if i in b else "S6C" for i in cells.index]
    cells["area_m2"] = cells.geometry.area
    cells = _lonlat(cells.drop(columns=["x", "y"]))
    return objects, cells, k


def _lonlat(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    c = gdf.geometry.centroid.to_crs(4326)
    gdf["lon"], gdf["lat"] = c.x.values, c.y.values
    return gdf


def frame_counts(objects: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    """N per (stratum, county)."""
    f = pd.concat([objects[["stratum", "county"]], cells[["stratum", "county"]]])
    return f.groupby(["stratum", "county"]).size().rename("N").reset_index()


# ── addendum frames: west of the Bay, footprints ───────────────────────────────────

def west_counties() -> list:
    return [n for n in C.county_names() if n not in C.EASTERN_SHORE]


def load_detections(counties: list, root: Path | None = None) -> gpd.GeoDataFrame:
    """Notebook-05 (published model, step 0) outlines of each county, centroid inside, UTM;
    columns candidate_id, county, geometry."""
    parts = []
    for n in counties:
        cty = region.county_boundary(n)
        _, _, b = C.load_county_run(C.county_out(n, root))
        b = C.county_buildings(b, cty)
        if len(b):
            cid = b["candidate_id"].astype(str) if "candidate_id" in b else pd.Series(
                [f"{C.slug(n)}/{i}" for i in range(len(b))], index=b.index)
            parts.append(gpd.GeoDataFrame({"candidate_id": cid.values, "county": n}, geometry=b.geometry.values, crs=UTM))
    if not parts:
        return gpd.GeoDataFrame({"candidate_id": [], "county": []}, geometry=[], crs=UTM)
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=UTM)


def permit_points(registry: Path = REGISTRY, counties: list | None = None) -> gpd.GeoDataFrame:
    """Poultry permits (protocol 10.2 types) in the given counties, UTM."""
    sites = [s for s in json.load(open(registry))["sites"] if s["animal_type"] in POULTRY_PERMITS]
    if counties is not None:
        sites = [s for s in sites if s["county"] in counties]
    return gpd.GeoDataFrame(pd.DataFrame(sites)[["county", "animal_type"]] if sites else
                            pd.DataFrame({"county": [], "animal_type": []}),
                            geometry=gpd.points_from_xy([s["lon"] for s in sites], [s["lat"] for s in sites]),
                            crs=4326).to_crs(UTM)


def _grid(boundaries: dict) -> gpd.GeoDataFrame:
    """1 km cells (multiples of 1 km in UTM 18N) with centre inside each county."""
    rows = []
    for n, cu in boundaries.items():
        x0, y0, x1, y1 = cu.bounds
        xs = np.arange(np.floor(x0 / CELL_M) * CELL_M, x1, CELL_M)
        ys = np.arange(np.floor(y0 / CELL_M) * CELL_M, y1, CELL_M)
        cand = gpd.GeoDataFrame({"x": np.repeat(xs, len(ys)), "y": np.tile(ys, len(xs))},
                                geometry=[box(x, y, x + CELL_M, y + CELL_M) for x in xs for y in ys], crs=UTM)
        cand = cand[cand.centroid.within(cu)]
        cand["county"] = n
        rows.append(cand)
    cells = gpd.GeoDataFrame(pd.concat(rows, ignore_index=True), crs=UTM)
    cells["key"] = [f"cell:{int(x // 1000)}_{int(y // 1000)}" for x, y in zip(cells.x, cells.y)]
    cells["area_m2"] = cells.geometry.area
    return cells.drop(columns=["x", "y"])


def rect_area(geoms) -> np.ndarray:
    import shapely
    return shapely.area(shapely.oriented_envelope(np.asarray(geoms)))


def frames_west(release: gpd.GeoDataFrame, detections: gpd.GeoDataFrame, permits: gpd.GeoDataFrame,
                boundaries: dict | None = None) -> tuple:
    """(S7 objects, S8/S6WA/S6WB cells, n far cells not sampled) west of the Bay (protocol 10.2).

    detections   western notebook-05 outlines (load_detections(west_counties()))
    permits      western poultry permits (permit_points(counties=west_counties()))"""
    if boundaries is None:
        boundaries = {n: region.county_boundary(n).to_crs(UTM).unary_union for n in west_counties()}
    m = release.to_crs(UTM)
    d = detections.to_crs(UTM).reset_index(drop=True)
    hit = set(gpd.sjoin(d[["geometry"]], m[["geometry"]], predicate="intersects").index)
    s7 = d[~d.index.isin(hit)]
    objects = gpd.GeoDataFrame({"key": "w05:" + s7.candidate_id.astype(str), "stratum": "S7", "county": s7.county.values,
                                "area_m2": rect_area(s7.geometry.values)}, geometry=s7.geometry.values, crs=UTM)
    cells = _grid(boundaries)
    mw = m[m.county.isin(list(boundaries))] if "county" in m else m
    known = gpd.GeoDataFrame(geometry=pd.concat([d.geometry, mw.geometry], ignore_index=True), crs=UTM)
    near_p = gpd.GeoDataFrame(geometry=permits.to_crs(UTM).buffer(NEAR_M), crs=UTM)
    s8 = set(gpd.sjoin(cells[["geometry"]], near_p, predicate="intersects").index) if len(near_p) else set()
    a = set(gpd.sjoin(cells[["geometry"]], known, predicate="intersects").index) - s8 if len(known) else set()
    kb = known.copy(); kb["geometry"] = kb.buffer(NEAR_M)
    b = set(gpd.sjoin(cells[["geometry"]], kb, predicate="intersects").index) - s8 - a if len(known) else set()
    cells["stratum"] = ["S8" if i in s8 else "S6WA" if i in a else "S6WB" if i in b else "far" for i in cells.index]
    far = int((cells.stratum == "far").sum())
    cells = cells[cells.stratum != "far"]
    return _lonlat(objects), _lonlat(cells.copy()), far


FOOTPRINTS = {
    "url": "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/Maryland.geojson.zip",
    "path": ROOT / "data" / "raw" / "external" / "ms_buildings" / "Maryland.geojson.zip",
    "content_md5_b64": "qdjqLZKguh7Vhf0iYGaugg==",     # server Content-MD5 on 2026-11-06 (57,507,353 bytes)
    "source": "Microsoft US Building Footprints v2, Maryland (ODbL)",
}


def ensure_footprints(download: bool = False) -> Path:
    """The Microsoft Maryland footprint file (~57 MB zip, ~411 MB unzipped), checked against the
    server's MD5; its SHA-256 is recorded in sample_meta_addendum.json. download=False never fetches."""
    import base64
    p = FOOTPRINTS["path"]
    if not p.exists():
        on_drive = env.results_root() / "reference" / p.name
        if on_drive.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(on_drive.read_bytes())
        elif download:
            import requests
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".part")
            with requests.get(FOOTPRINTS["url"], stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            tmp.rename(p)
        else:
            raise FileNotFoundError(f"{p.name} not downloaded (set DOWNLOAD_FOOTPRINTS = True)")
    md5 = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            md5.update(chunk)
    if base64.b64encode(md5.digest()).decode() != FOOTPRINTS["content_md5_b64"]:
        raise RuntimeError(f"{p} is not the file published on 2026-11-06 (MD5 mismatch)")
    return p


def shape_filter(gdf: gpd.GeoDataFrame, rule: dict = FOOTPRINT_RULE) -> gpd.GeoDataFrame:
    """Footprints whose minimum rotated rectangle is >= length_min long with length/width >= aspect_min."""
    import shapely
    g = gdf.to_crs(UTM)
    if not len(g):
        return g.assign(length_m=[], width_m=[])
    env_ = shapely.oriented_envelope(g.geometry.values)
    c = shapely.get_coordinates(env_).reshape(len(g), 5, 2)          # closed rectangle: 5 corners
    e1 = np.hypot(*(c[:, 1] - c[:, 0]).T)
    e2 = np.hypot(*(c[:, 2] - c[:, 1]).T)
    L, W = np.maximum(e1, e2), np.minimum(e1, e2)
    keep = (L >= rule["length_min"]) & (L >= rule["aspect_min"] * np.maximum(W, 1e-6))
    out = g[keep].copy()
    out["length_m"], out["width_m"] = L[keep], W[keep]
    return out


def load_footprints(path: Path) -> gpd.GeoDataFrame:
    """Shape-filtered footprints (UTM) with their row number in the file as `fid` and any capture-date
    property the file carries."""
    raw = gpd.read_file(f"zip://{path}")
    raw["fid"] = np.arange(len(raw))
    out = shape_filter(raw)
    out["density"] = footprint_density(raw.geometry, out.geometry)
    out.attrs["n_raw"] = len(raw)
    out.attrs["date_columns"] = [c for c in raw.columns if "date" in c.lower() or "capture" in c.lower()]
    return out


def _cell_ids(geoms: gpd.GeoSeries) -> np.ndarray:
    """1 km grid cell id of each geometry's centre (geometries in UTM)."""
    import shapely
    c = shapely.get_coordinates(geoms.centroid.values)
    return (c[:, 0] // CELL_M).astype(np.int64) * 100000 + (c[:, 1] // CELL_M).astype(np.int64)


def footprint_density(all_geoms: gpd.GeoSeries, geoms: gpd.GeoSeries) -> np.ndarray:
    """Number of footprints (all of them, before the shape rule) whose centre is in the same 1 km grid
    cell as each of `geoms` (the protocol's rural / developed split for western candidates)."""
    counts = pd.Series(_cell_ids(all_geoms.to_crs(UTM))).value_counts()
    return counts.reindex(_cell_ids(geoms.to_crs(UTM))).fillna(0).astype(int).values


def frames_footprints(fp: gpd.GeoDataFrame, release: gpd.GeoDataFrame, traced: gpd.GeoDataFrame,
                      west_detections: gpd.GeoDataFrame, boundaries: dict | None = None) -> tuple:
    """(S5 objects, k_f). S5 = shape-filtered footprints touching no release outline, no traced polygon
    and (west) no notebook-05 detection; S5ES by the county holding the centroid; western ones split
    by `density` (footprints in their 1 km cell): S5WR < RURAL_DENSITY <= S5WD.
    k_f = release outline area / footprint area on S1-type pairs (release outline on a traced house
    that also touches a footprint)."""
    if boundaries is None:
        boundaries = {n: region.county_boundary(n).to_crs(UTM).unary_union for n in C.county_names()}
    f = fp.to_crs(UTM).reset_index(drop=True)
    m, g, w = release.to_crs(UTM), traced.to_crs(UTM), west_detections.to_crs(UTM)
    touch = set()
    for layer in (m, g, w):
        if len(layer):
            touch |= set(gpd.sjoin(f[["geometry"]], layer[["geometry"]], predicate="intersects").index)
    cand = f[~f.index.isin(touch)].copy()
    cty = gpd.GeoDataFrame({"county": list(boundaries)}, geometry=list(boundaries.values()), crs=UTM)
    cen = gpd.GeoDataFrame(geometry=cand.centroid.values, index=cand.index, crs=UTM)
    j = gpd.sjoin(cen, cty, predicate="within")
    cand = cand.loc[j.index]
    cand["county"] = j["county"].values
    es = cand.county.isin(C.EASTERN_SHORE)
    rural = cand["density"].values < RURAL_DENSITY
    stratum = np.where(es, "S5ES", np.where(rural, "S5WR", "S5WD"))
    keep = [c for c in cand.columns if "date" in c.lower() or "capture" in c.lower() or c == "density"]
    objects = gpd.GeoDataFrame({"key": "msfp:" + cand.fid.astype(str), "stratum": stratum,
                                "county": cand.county.values, "area_m2": cand.geometry.area.values,
                                **{c: cand[c].values for c in keep}}, geometry=cand.geometry.values, crs=UTM)
    # k_f on release outlines that touch both a traced house and a footprint
    on = gpd.sjoin(m[["geometry"]], g[["geometry"]], predicate="intersects").index.unique()
    mo = m.loc[on]
    jj = gpd.sjoin(mo[["geometry"]], f[["geometry"]], predicate="intersects")
    if len(jj):
        fa = f.geometry.area
        pair = jj.reset_index().drop_duplicates("index_right")
        k_f = float(mo.loc[pair["index"].unique()].geometry.area.sum() / fa.loc[pair.index_right].sum())
    else:
        k_f = 1.0
    return _lonlat(objects), k_f


def known_layer(release, traced, west_detections=None, footprints_frame=None) -> gpd.GeoDataFrame:
    """Every building drawn on cell photos (protocol 10.3): release outlines, traced polygons, western
    notebook-05 detections and S5 frame footprints, one neutral colour."""
    parts = [release.to_crs(UTM).geometry, traced.to_crs(UTM).geometry]
    for x in (west_detections, footprints_frame):
        if x is not None and len(x):
            parts.append(x.to_crs(UTM).geometry)
    return gpd.GeoDataFrame(geometry=pd.concat(parts, ignore_index=True), crs=UTM)


def capture_rates(traced_es: gpd.GeoDataFrame, fp: gpd.GeoDataFrame, release: gpd.GeoDataFrame,
                  step0: gpd.GeoDataFrame) -> pd.DataFrame:
    """Model residual inputs (protocol 10.5): share of traced houses touched by
    neither a (shape-filtered) footprint nor a release outline (q_ES), and by neither a footprint nor a
    step-0 published-model detection (q_W). Geometry only; Clopper-Pearson 95%."""
    from scipy.stats import beta
    g = traced_es.to_crs(UTM).reset_index(drop=True)

    def touched(layer):
        return set(gpd.sjoin(g[["geometry"]], layer.to_crs(UTM)[["geometry"]], predicate="intersects").index) \
            if len(layer) else set()
    by_fp = touched(fp)
    rows = []
    for name, other in (("q_ES (no footprint, no release outline)", release),
                        ("q_W (no footprint, no step-0 detection)", step0)):
        miss = len(g) - len(by_fp | touched(other))
        n = len(g)
        rows.append({"rate": name, "missed": miss, "n": n, "q": miss / n,
                     "low": beta.ppf(0.025, miss, n - miss + 1) if miss else 0.0,
                     "high": beta.ppf(0.975, miss + 1, n - miss) if miss < n else 1.0})
    return pd.DataFrame(rows).set_index("rate")


# ── sample ─────────────────────────────────────────────────────────────────────

def allocate(counts: pd.Series, n: int | None, min_per: int = MIN_PER_COUNTY) -> pd.Series:
    """Proportional allocation of n over counties (largest remainder), at least min_per per county
    (or all its items if fewer); n=None = take everything (census). If the minimums alone exceed n
    (many counties, small n: e.g. S6W-A, 14 counties, n 40), the minimum is lowered one step at a time
    until they fit; no county is ever trimmed below it."""
    counts = counts[counts > 0]
    if n is None or n >= counts.sum():
        return counts.copy()
    floor_ = np.minimum(counts, min_per)
    while floor_.sum() > n and min_per > 0:
        min_per -= 1
        floor_ = np.minimum(counts, min_per)
    raw = counts / counts.sum() * n
    out = np.maximum(np.floor(raw), floor_).astype(int)
    out = np.minimum(out, counts)
    rem = (raw - np.floor(raw)).sort_values(ascending=False)
    while out.sum() < n:                                   # add to the largest remainders
        for c in rem.index:
            if out.sum() >= n:
                break
            if out[c] < counts[c]:
                out[c] += 1
    while out.sum() > n:                                   # minimums pushed it over: trim the largest
        c = (out - floor_).idxmax()
        if out[c] <= floor_[c]:
            raise RuntimeError("allocation can't meet its minimums")       # unreachable after the loop above
        out[c] -= 1
    return out.astype(int)


def draw(objects: gpd.GeoDataFrame, cells: gpd.GeoDataFrame, sizes: dict = SIZES, seed: int = 20261105,
         pilot: dict = PILOT, calibration: dict = CALIBRATION) -> gpd.GeoDataFrame:
    """Every item of every frame, with its random rank inside (stratum, county) and a role:
    sample / reserve / calibration / not drawn (cells beyond n are 'not drawn', they have no reserve role
    but keep their rank). Calibration = the last items of each county's order (never sampled, never
    a reserve). Pilot = a random `pilot[h]` of each object stratum's sample."""
    rng = np.random.default_rng(seed)
    frame = pd.concat([objects.assign(kind="object"), cells.assign(kind="cell")], ignore_index=True)
    frame = gpd.GeoDataFrame(frame, geometry="geometry", crs=UTM)
    frame["rank"], frame["role"], frame["pilot"] = -1, "", False
    for h in OBJECT_STRATA + CELL_STRATA:
        fh = frame[frame.stratum == h]
        if not len(fh):
            continue
        alloc = allocate(fh.groupby("county").size(), sizes.get(h))
        # calibration from the tail, round-robin over the counties with the most spare items
        spare = fh.groupby("county").size() - alloc.reindex(fh.groupby("county").size().index).fillna(0)
        cal = pd.Series(0, index=spare.index)
        for _ in range(calibration.get(h, 0)):
            left = spare[spare - cal > 0]
            if not len(left):
                break
            c = min(left.index, key=lambda c_: (cal[c_], -left[c_]))   # fewest so far, then most spare
            cal[c] += 1
        for c, idx in fh.groupby("county").groups.items():
            order = rng.permutation(np.asarray(idx))
            frame.loc[order, "rank"] = np.arange(len(order))
            na, nc = int(alloc.get(c, 0)), int(cal.get(c, 0))
            role = np.array(["reserve" if h in OBJECT_STRATA else "not drawn"] * len(order), dtype=object)
            role[:na] = "sample"
            if nc:
                role[len(order) - nc:] = "calibration"
            frame.loc[order, "role"] = role
        if h in pilot:
            s = frame.index[(frame.stratum == h) & (frame.role == "sample")]
            frame.loc[rng.choice(s, size=min(pilot[h], len(s)), replace=False), "pilot"] = True
    return frame


def replace_pilot(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Pilot failed the kappa gate: drop the pilot items (role -> 'discarded pilot') and put the next
    reserve item of the same stratum and county in each one's place (it becomes a pilot item)."""
    f = frame.copy()
    for i in f.index[f.pilot & (f.role == "sample")]:
        h, c = f.at[i, "stratum"], f.at[i, "county"]
        res = f[(f.stratum == h) & (f.county == c) & (f.role == "reserve")].sort_values("rank")
        if not len(res):
            raise RuntimeError(f"no reserve left in {h} / {c}")
        j = res.index[0]
        f.at[i, "role"], f.at[i, "pilot"] = "discarded pilot", False
        f.at[j, "role"], f.at[j, "pilot"] = "sample", True
    return f


def draw_addendum(new_objects: gpd.GeoDataFrame, new_cells: gpd.GeoDataFrame, labelled_keys=(),
                  seed: int = SEED_V12, sizes: dict = SIZES) -> gpd.GeoDataFrame:
    """Addendum strata only (S5ES, S5WR, S5WD, S7, S8, S6WA, S6WB), own seed, no pilot or calibration.
    Refuses if any of their keys already has a label."""
    keys = set(new_objects.key) | set(new_cells.key)
    bad = keys & set(labelled_keys)
    if bad:
        raise RuntimeError(f"{len(bad)} addendum keys already have labels (e.g. {sorted(bad)[:3]}): the addendum "
                           "can't be drawn after labelling has seen them")
    strata = set(new_objects.stratum) | set(new_cells.stratum)
    if not strata <= set(NEW_OBJECT + NEW_CELL):
        raise ValueError(f"not addendum strata: {strata - set(NEW_OBJECT + NEW_CELL)}")
    f = draw(new_objects, new_cells, sizes=sizes, seed=seed, pilot={}, calibration={})
    f["protocol"] = "v1.1 addendum"
    return f


def queue(frame: pd.DataFrame, reviewer: str, phase: str, seed: int = 20261105) -> pd.DataFrame:
    """Items for one interpreter and phase, in that interpreter's own random order.
    phase: 'calibration' | 'pilot' | 'main' (v1.1 sampled objects not in the pilot) | 'cells' (v1.1)
           | 'addendum objects' (S5, S7) | 'addendum cells' (S8, S6W)."""
    smp = frame.role == "sample"
    if phase == "calibration":
        q = frame[frame.role == "calibration"]
    elif phase == "pilot":
        q = frame[smp & frame.pilot]
    elif phase == "main":
        q = frame[smp & ~frame.pilot & frame.stratum.isin(V11_OBJECT)]
    elif phase == "cells":
        q = frame[smp & frame.stratum.isin(V11_CELL)]
    elif phase == "addendum objects":
        q = frame[smp & frame.stratum.isin(NEW_OBJECT)]
    elif phase == "addendum cells":
        q = frame[smp & frame.stratum.isin(NEW_CELL)]
    else:
        raise ValueError(phase)
    h = int(hashlib.sha256(f"{seed}:{reviewer.strip().lower()}:{phase}".encode()).hexdigest()[:8], 16)
    return q.iloc[np.random.default_rng(h).permutation(len(q))].reset_index(drop=True)


# ── photos (blind: NAIP 2023, crosshair, nothing else) ─────────────────────────

def chip2023(lon: float, lat: float, size_m: float = 500, res: float = 1.0):
    """(RGB uint8, transform, crs, flight dates) of a size_m square of NAIP from the YEAR flight only
    (the tile fetcher would otherwise take the newest NAIP), at `res` m, in memory. None if no YEAR photo.

    For display only: a windowed read in the image's own grid uses the COG overviews and fetches just
    the blocks the square needs (tiles.build_mosaic warps whole bands: fine for 2 km detection tiles,
    1-6 min for a 1 km cell). Newest YEAR image first; later ones fill what it leaves empty. An image
    in another CRS than the first one is warped onto it."""
    import rasterio
    from pyproj import Transformer
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT
    from rasterio.windows import from_bounds

    from geo_anom.core.geo_utils import BBox
    from geo_anom.task1.tiles import find_naip_items, make_session, select_items

    s = make_session()
    bb = BBox.from_point(lon=lon, lat=lat, buffer_km=size_m / 2000)
    items = [it for it in find_naip_items(bb, s) if str(it["properties"].get("datetime", "")).startswith(YEAR)]
    items = select_items(items, bb)
    if not items:
        return None
    n = int(round(size_m / res))
    img = np.zeros((n, n, 3), np.uint8)
    crs = t = None
    used = []
    for it in items:
        if img.any(axis=2).all():
            break
        with rasterio.open(it["assets"]["image"]["href"]) as src:
            if crs is None:
                crs = src.crs
                x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)
                left, top = np.floor((x - size_m / 2) / res) * res, np.ceil((y + size_m / 2) / res) * res
                t = from_origin(left, top, res, res)
            if src.crs == crs:
                win = from_bounds(left, top - n * res, left + n * res, top, src.transform)
                part = src.read([1, 2, 3], window=win, out_shape=(3, n, n), boundless=True, fill_value=0,
                                resampling=Resampling.average)
            else:
                with WarpedVRT(src, crs=crs, transform=t, width=n, height=n, src_nodata=0, nodata=0,
                               resampling=Resampling.average) as vrt:
                    part = vrt.read([1, 2, 3])
        part = np.moveaxis(part, 0, -1)
        new = part.any(axis=2) & ~img.any(axis=2)
        if new.any():
            img[new] = part[new]
            used.append(it)
    if not used:
        return None
    dates = sorted({str(it["properties"]["datetime"])[:10] for it in used})
    return img, t, crs, ", ".join(dates)


def _fig(w_px, h_px):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    fig = Figure(figsize=(w_px / 100, h_px / 100), dpi=100)
    FigureCanvasAgg(fig)
    return fig


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()


def _scale_bar(ax, w, h, half, res):
    bar = 100 if 2 * half * res > 300 else 50
    ax.plot([w / 2 - half * 0.9, w / 2 - half * 0.9 + bar / res], [h / 2 + half * 0.9] * 2, color="white", lw=3)
    ax.text(w / 2 - half * 0.9, h / 2 + half * 0.82, f"{bar} m", color="white", fontsize=9)


def render_object(got, zoom_m: float = 160, px: int = 520) -> bytes:
    """Surroundings (left, 500 m) and close-up (right, zoom_m) with a crosshair at the point.
    No outline: the shape would give away whether it is a detection or a traced house."""
    from geo_anom.task1.viz import stretch
    fig = _fig(2 * px, px)
    axs = fig.subplots(1, 2)
    if got is None:
        for ax in axs:
            ax.text(0.5, 0.5, f"no {YEAR} photo", ha="center"); ax.set_axis_off()
    else:
        img, t, _, date = got
        h, w = img.shape[:2]
        shown, res = stretch(img, 1, 99.7), abs(t.a)
        for ax, half in zip(axs, (w / 2, zoom_m / res / 2)):
            ax.imshow(shown)
            g, L = half * 0.06, half * 0.18          # crosshair arms with a gap, so the centre stays visible
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ax.plot([w / 2 + dx * g, w / 2 + dx * L], [h / 2 + dy * g, h / 2 + dy * L], color="#ff2bd6", lw=2)
            ax.set_xlim(w / 2 - half, w / 2 + half); ax.set_ylim(h / 2 + half, h / 2 - half)
            ax.set_axis_off()
            _scale_bar(ax, w, h, half, res)
        axs[0].text(5, 15, f"NAIP {date}", color="white", fontsize=9)
    fig.subplots_adjust(0, 0, 1, 1, wspace=0.02)
    return _png(fig)


def render_cell(got, cell_geom, known: gpd.GeoDataFrame, px: int = 900) -> bytes:
    """The 1 km cell (white dashed square, 100 m margin around it), every known building
    (map outlines and traced houses, one neutral colour, no way to tell which is which) and a faint
    3x3 grid to help scanning."""
    from matplotlib.patches import Polygon as MplPolygon

    from geo_anom.task1.viz import stretch
    fig = _fig(px, px)
    ax = fig.subplots(1, 1)
    if got is None:
        ax.text(0.5, 0.5, f"no {YEAR} photo", ha="center"); ax.set_axis_off()
        return _png(fig)
    img, t, crs, date = got
    ax.imshow(stretch(img, 1, 99.7))
    inv = ~t
    to_px = lambda geom: np.array([inv * c[:2] for c in geom.exterior.coords])
    cg = gpd.GeoSeries([cell_geom], crs=UTM).to_crs(crs).iloc[0]
    xy = to_px(cg)
    ax.add_patch(MplPolygon(xy, closed=True, fill=False, ec="white", lw=1.5, ls="--"))
    x0, y0 = xy[:, 0].min(), xy[:, 1].min()
    x1, y1 = xy[:, 0].max(), xy[:, 1].max()
    for f in (1 / 3, 2 / 3):
        ax.plot([x0 + f * (x1 - x0)] * 2, [y0, y1], color="white", lw=0.5, alpha=0.4)
        ax.plot([x0, x1], [y0 + f * (y1 - y0)] * 2, color="white", lw=0.5, alpha=0.4)
    kk = known.to_crs(crs)
    for geom in kk.geometry:
        for poly in ([geom] if geom.geom_type == "Polygon" else list(geom.geoms)):
            ax.add_patch(MplPolygon(to_px(poly), closed=True, fill=False, ec="#00e5ff", lw=1.2))
    h, w = img.shape[:2]
    ax.set_xlim(0, w); ax.set_ylim(h, 0); ax.set_axis_off()
    _scale_bar(ax, w, h, w / 2, abs(t.a))
    ax.text(5, 15, f"NAIP {date}", color="white", fontsize=9)
    fig.subplots_adjust(0, 0, 1, 1)
    return _png(fig)


# ── labels ─────────────────────────────────────────────────────────────────────

class Store:
    """Append-only CSV of one interpreter's labels (last one per key wins)."""

    cols = ["key", "value", "low_confidence", "note", "reviewer", "phase", "labelled_at"]

    def __init__(self, folder: Path, reviewer: str):
        if not reviewer or not reviewer.strip():
            raise ValueError("set INTERPRETER to your name or initials")
        self.reviewer = reviewer.strip()
        self.path = Path(folder) / f"labels_{self.reviewer.lower().replace(' ', '_')}.csv"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            pd.DataFrame(columns=self.cols).to_csv(self.path, index=False)

    def add(self, key: str, value: str, phase: str, low_confidence: bool = False, note: str = ""):
        if value not in LABELS + CELL_COUNTS:
            raise ValueError(f"unknown label {value!r}")
        rec = {"key": key, "value": value, "low_confidence": bool(low_confidence), "note": note,
               "reviewer": self.reviewer, "phase": phase,
               "labelled_at": datetime.now(timezone.utc).isoformat(timespec="microseconds")}
        pd.DataFrame([rec], columns=self.cols).to_csv(self.path, mode="a", header=False, index=False)

    def latest(self) -> pd.DataFrame:
        return latest(pd.read_csv(self.path, dtype={"value": str, "note": str}))

    def done(self) -> set:
        return set(self.latest()["key"])


def latest(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw
    return raw.sort_values("labelled_at").groupby(["key", "reviewer"], as_index=False).last()


def load_labels(folder: Path) -> pd.DataFrame:
    files = sorted(Path(folder).glob("labels_*.csv"))
    raw = [pd.read_csv(f, dtype={"value": str, "note": str}) for f in files]
    raw = pd.concat(raw, ignore_index=True) if raw else pd.DataFrame(columns=Store.cols)
    return latest(raw)


def _ui(items: pd.DataFrame, store: Store, phase: str, values: list, render_fn, prompt: str, prefetch: int = 3):
    """Photo, label buttons, 'low confidence' tick and a note box. Skips what this interpreter has done."""
    from concurrent.futures import ThreadPoolExecutor

    import ipywidgets as W
    from IPython.display import display

    done = store.done()
    todo = [i for i, k in enumerate(items["key"]) if k not in done]
    state = {"pos": 0, "history": []}
    pool = ThreadPoolExecutor(max_workers=3)
    futures = {}

    def want(pos):
        for p in range(pos, min(pos + prefetch + 1, len(todo))):
            i = todo[p]
            if i not in futures:
                futures[i] = pool.submit(render_fn, items.iloc[i])

    img = W.Image(format="png", layout=W.Layout(width="100%", max_width="1040px"))
    status = W.HTML()
    low = W.Checkbox(description="low confidence", indent=False)
    other = W.Checkbox(description=OTHER_FORM + " (with not a house)", indent=False)
    note = W.Text(placeholder="note (optional: why, Google Earth date used, where in the cell)",
                  layout=W.Layout(width="600px"))
    buttons = [W.Button(description=v, layout=W.Layout(width="130px" if len(values) < 6 else "60px")) for v in values]
    back = W.Button(description="← back", layout=W.Layout(width="90px"))

    def show():
        p = state["pos"]
        low.value, other.value, note.value = False, False, ""
        if p >= len(todo):
            img.value = b""
            status.value = f"<b>All done</b>: {len(todo)} labelled in this phase by {store.reviewer}."
            for b in buttons + [back]:
                b.disabled = True
            return
        want(p)
        status.value = f"<b>{p + 1} / {len(todo)}</b> &nbsp; {prompt}"
        try:
            img.value = futures[todo[p]].result()
        except Exception as e:
            status.value += f"<br><span style='color:red'>could not load photo: {e} (label unsure and note it)</span>"
            img.value = b""

    def on(v):
        def f(_):
            if state["pos"] >= len(todo):
                return
            txt = "; ".join(x for x in ((OTHER_FORM if other.value else ""), note.value) if x)
            store.add(items.iloc[todo[state["pos"]]]["key"], v, phase, low.value, txt)
            state["history"].append(state["pos"])
            state["pos"] += 1
            show()
        return f

    def on_back(_):
        if state["history"]:
            state["pos"] = state["history"].pop()
            show()

    for b, v in zip(buttons, values):
        b.on_click(on(v))
    back.on_click(on_back)
    extras = [low, other, note] if values == LABELS else [low, note]
    ui = W.VBox([status, img, W.HBox(extras), W.HBox(buttons + [back])])
    show()
    display(ui)
    return ui


def label_ui(items: pd.DataFrame, store: Store, phase: str):
    return _ui(items, store, phase, LABELS, lambda r: render_object(chip2023(r["lon"], r["lat"], 500)),
               "What is at the <span style='color:#ff2bd6'>crosshair</span> on the 2023 photo? "
               "(protocol §2; left 500 m, right close-up)")


def cell_ui(items: pd.DataFrame, store: Store, known: gpd.GeoDataFrame, phase: str = "cells"):
    def fn(r):
        kk = known[known.intersects(r["geometry"].buffer(150))]
        return render_cell(chip2023(r["lon"], r["lat"], CELL_M + 200, res=1.2), r["geometry"], kk)
    return _ui(items, store, phase, CELL_COUNTS, fn,
               "How many standing poultry houses have their centre inside the "
               "<b>dashed square</b> and <b>no</b> <span style='color:#00b8cc'>outline</span>? "
               "(say where in the note)")


# ── agreement and adjudication ─────────────────────────────────────────────────

def binary(v) -> pd.Series:
    return (pd.Series(v) == "house").astype(int)


def cohen_kappa(a, b) -> float:
    a, b = pd.Series(list(a)).astype(str), pd.Series(list(b)).astype(str)
    po = float((a.values == b.values).mean())
    pe = sum(float((a == c).mean()) * float((b == c).mean()) for c in set(a) | set(b))
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def wide(labels: pd.DataFrame, reviewers: list | None = None) -> pd.DataFrame:
    """One row per key, one column per interpreter."""
    w = labels.pivot(index="key", columns="reviewer", values="value")
    return w[reviewers] if reviewers else w


def agreement(labels: pd.DataFrame, frame: pd.DataFrame, reviewers: list, keys=None,
              B: int = 2000, seed: int = 1) -> pd.DataFrame:
    """Pre-adjudication agreement between two interpreters per stratum and overall:
    share identical, Cohen's kappa on the 5 labels and on house / not house (bootstrap 95% CI)."""
    a, b = reviewers
    w = wide(labels, reviewers).dropna()
    if keys is not None:
        w = w[w.index.isin(set(keys))]
    st = frame.set_index("key")["stratum"]
    w = w.assign(stratum=st.reindex(w.index).values)
    rng = np.random.default_rng(seed)
    rows = []
    for name, g in [("all objects", w[w.stratum.isin(OBJECT_STRATA)])] + \
                   [(h, w[w.stratum == h]) for h in OBJECT_STRATA]:
        if not len(g):
            continue
        ba, bb = binary(g[a]).values, binary(g[b]).values
        boots = [cohen_kappa(ba[i], bb[i]) for i in (rng.integers(0, len(g), len(g)) for _ in range(B))]
        rows.append({"items": name, "n": len(g), "same label": float((g[a].values == g[b].values).mean()),
                     "kappa (5 labels)": cohen_kappa(g[a], g[b]), "kappa (house / not)": cohen_kappa(ba, bb),
                     "kappa low": float(np.nanpercentile(boots, 2.5)), "kappa high": float(np.nanpercentile(boots, 97.5))})
    return pd.DataFrame(rows)


def cell_agreement(labels: pd.DataFrame, reviewers: list) -> dict:
    a, b = reviewers
    w = wide(labels[labels.phase == "cells"], reviewers).dropna()
    if not len(w):
        return {}
    num = lambda s: s.str.replace("+", "", regex=False).astype(int)
    return {"cells": len(w), "same count": float((w[a] == w[b]).mean()),
            "kappa (any / none)": cohen_kappa(num(w[a]) > 0, num(w[b]) > 0),
            f"houses {a}": int(num(w[a]).sum()), f"houses {b}": int(num(w[b]).sum())}


def adjudication_queue(labels: pd.DataFrame, reviewers: list) -> pd.DataFrame:
    """Keys where the two interpreters differ (with both labels and notes) -- or where either
    said unsure, which also goes to a joint look."""
    a, b = reviewers
    L = labels[labels.reviewer.isin(reviewers)]
    v = L.pivot(index="key", columns="reviewer", values="value").dropna()
    n = L.pivot(index="key", columns="reviewer", values="note").reindex(v.index)
    out = v[(v[a] != v[b]) | (v[a] == "unsure") | (v[b] == "unsure")].copy()
    out.columns = [f"label {c}" for c in out.columns]
    for c in reviewers:
        out[f"note {c}"] = n[c].reindex(out.index)
    return out.reset_index()


def agreement_with_final(labels: pd.DataFrame, final: pd.Series, reviewer: str, frame: pd.DataFrame) -> pd.DataFrame:
    """One interpreter vs the adjudicated label, per object stratum (protocol 10.3: Monica on S7)."""
    mine = labels[labels.reviewer == reviewer].set_index("key").value
    st = frame.set_index("key").stratum
    rows = []
    for h in OBJECT_STRATA:
        k = [x for x in final.index if st.get(x) == h and x in mine.index]
        if k:
            a, b = mine.reindex(k), final.reindex(k)
            rows.append({"stratum": h, "n": len(k), "same label": float((a.values == b.values).mean()),
                         "kappa (house / not)": cohen_kappa(binary(a.values), binary(b.values))})
    return pd.DataFrame(rows)


def other_form_counts(labels: pd.DataFrame, final: pd.Series, frame: pd.DataFrame) -> pd.Series:
    """Per stratum: final 'not a house' items any interpreter noted as a poultry building of another
    form (protocol 10.3; a separate row, never in the totals)."""
    noted = set(labels[labels.note.fillna("").str.lower().str.contains(OTHER_FORM)].key)
    k = [x for x in final.index if final[x] == "not a house" and x in noted]
    return frame.set_index("key").stratum.reindex(k).value_counts().rename("poultry, other form")


ADJ_COLS = ["key", "value", "reason", "decided_by", "decided_at"]


def adjudicate(path: Path, key: str, value: str, reason: str, decided_by: str):
    if value not in LABELS + CELL_COUNTS:
        raise ValueError(f"unknown label {value!r}")
    if not reason.strip() or not decided_by.strip():
        raise ValueError("record a reason and who decided")
    path = Path(path)
    if not path.exists():
        pd.DataFrame(columns=ADJ_COLS).to_csv(path, index=False)
    rec = {"key": key, "value": value, "reason": reason, "decided_by": decided_by,
           "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    pd.DataFrame([rec], columns=ADJ_COLS).to_csv(path, mode="a", header=False, index=False)


def final_labels(labels: pd.DataFrame, reviewers: list, adjudicated: pd.DataFrame | None = None) -> pd.Series:
    """Agreed label, else the latest adjudicated one. Still split: objects -> 'unsure';
    cells -> the larger of the two counts (conservative: more missed houses, lower recall)."""
    a, b = reviewers
    v = wide(labels, reviewers).dropna()
    out = v[a].where(v[a] == v[b])
    if adjudicated is not None and len(adjudicated):
        adj = adjudicated.astype({"value": str}).sort_values("decided_at").groupby("key").value.last()
        out = adj.reindex(out.index).combine_first(out)
    cell = out.index.str.startswith("cell:") & out.isna()
    if cell.any():
        num = lambda s: s.str.replace("+", "", regex=False).astype(int)
        big = np.maximum(num(v.loc[cell, a]), num(v.loc[cell, b]))
        out[cell] = [CELL_COUNTS[min(x, 6)] for x in big]
    return out.fillna("unsure")


# ── estimators ─────────────────────────────────────────────────────────────────

def _y(values: pd.Series, unsure_as_house: bool, uc_as_house: bool) -> np.ndarray:
    ok = {"house"} | ({"unsure"} if unsure_as_house else set()) | ({"under construction"} if uc_as_house else set())
    return values.isin(ok).astype(float).values


def _cell_y(values: pd.Series) -> np.ndarray:
    return values.astype(str).str.replace("+", "", regex=False).astype(float).values


def groups(frame: pd.DataFrame, final: pd.Series, unsure_as_house: bool = False,
           uc_as_house: bool = False) -> list:
    """[(stratum, county, N, y array, area array)] for every (stratum, county) with labels.
    For objects y = 1 if a standing house; for cells y = houses counted."""
    out = []
    lab = final.reindex(frame.key)
    f = frame.assign(value=lab.values)
    for (h, c), g in f.groupby(["stratum", "county"]):
        N = len(g)
        s = g[(g.role == "sample") & g.value.notna()]
        if not len(s):
            continue
        y = _cell_y(s.value) if h in CELL_STRATA else _y(s.value, unsure_as_house, uc_as_house)
        out.append((h, c, N, y, s.area_m2.values.astype(float)))
    return out


def _totals(M: list, k: dict, west: set, k_f: float = 1.0) -> dict:
    """Totals from per-group means [(stratum, county, N, mean y, mean y*area)]."""
    t = dict.fromkeys(["C_es", "C_west", "C_off_es", "A_es", "A_west", "M", "A_M", "R_W", "A_R",
                       "F_es", "F_w", "F_wr", "F_wd", "A_F_es", "A_F_w", "P_W", "Y", "Y_W"], 0.0)
    for h, c, N, my, mya in M:
        if h in ("S1", "S2", "S3"):
            w = "west" if c in west else "es"
            t[f"C_{w}"] += N * my
            t[f"A_{w}"] += N * mya
            if w == "es" and h in ("S2", "S3"):
                t["C_off_es"] += N * my
        elif h == "S4":
            t["M"] += N * my
            t["A_M"] += N * mya * k.get(c, 1.0)
        elif h == "S7":
            t["R_W"] += N * my
            t["A_R"] += N * mya
        elif h in ("S5ES", "S5WR", "S5WD"):
            r = "es" if h == "S5ES" else "w"
            t[f"F_{r}"] += N * my
            t[f"A_F_{r}"] += N * mya * k_f
            if h != "S5ES":
                t["F_wr" if h == "S5WR" else "F_wd"] += N * my
        elif h == "S8":
            t["P_W"] += N * my
        elif h in ("S6A", "S6B", "S6C"):
            t["Y"] += N * my
        elif h in ("S6WA", "S6WB"):
            t["Y_W"] += N * my
    return t


def _derived(t: dict, mapped_es: int, mapped_all: int) -> dict:
    """Protocol 10.4 (list frames) and 10.5 (residual, own rows)."""
    T_L = t["C_es"] + t["C_west"] + t["M"] + t["R_W"] + t["F_es"] + t["F_w"] + t["P_W"]
    T_es = t["C_es"] + t["M"] + t["F_es"]
    n_w = t["C_west"] + t["R_W"]
    roof_w_house = (t["A_west"] + t["A_R"]) / n_w if n_w > 0 else (t["A_M"] / t["M"] if t["M"] > 0 else 0.0)
    roof_es = t["A_es"] + t["A_M"] + t["A_F_es"]
    roof_md = roof_es + t["A_west"] + t["A_R"] + t["A_F_w"] + t["P_W"] * roof_w_house
    return {
        "precision (Maryland)": (t["C_es"] + t["C_west"]) / mapped_all,
        "precision (Eastern Shore)": t["C_es"] / mapped_es,
        "correct map houses (ES)": t["C_es"],
        "correct map houses (west)": t["C_west"],
        "missed traced houses standing": t["M"],
        "western detections not on map, houses (S7)": t["R_W"],
        "footprint houses (ES)": t["F_es"],
        "footprint houses (west)": t["F_w"],
        "footprint houses (west, rural)": t["F_wr"],
        "footprint houses (west, developed)": t["F_wd"],
        "permit-cell houses (west, S8)": t["P_W"],
        "houses on a list (Maryland)": T_L,
        "houses on a list (ES)": T_es,
        "recall (Maryland)": (t["C_es"] + t["C_west"]) / T_L if T_L else np.nan,
        "recall (ES)": t["C_es"] / T_es if T_es else np.nan,
        "roof km2 (Maryland)": roof_md / 1e6,
        "roof km2 (ES)": roof_es / 1e6,
        "list houses off the tracing (ES), L_ES": t["C_off_es"] + t["F_es"],
        "list houses (west), L_W": t["C_west"] + t["R_W"] + t["F_w"] + t["P_W"],
        "residual: cell expansion (ES)": t["Y"],
        "residual: cell expansion (west)": t["Y_W"],
        "residual: cell expansion (total)": t["Y"] + t["Y_W"],
    }


def _cp_one_sided(n: int, all_house: bool) -> float:
    """Exact one-sided 95% bound when all n sampled items are houses (lower) or none are (upper)."""
    b = 0.05 ** (1.0 / n)
    return b if all_house else 1.0 - b


def mean_per_positive_cell(G: list) -> float:
    """Mean house count per positive cell over S6, S6W and S8 (3 if there are none: an assumption)."""
    ys = np.concatenate([g[3] for g in G if g[0] in RESIDUAL_CELLS + ["S8"]] or [np.array([])])
    pos = ys[ys > 0]
    return float(pos.mean()) if len(pos) else 3.0


def estimate(frame: pd.DataFrame, final: pd.Series, k: dict, unsure_as_house: bool = False,
             uc_as_house: bool = False, B: int = 2000, seed: int = 2, es: list | None = None,
             k_f: float = 1.0) -> pd.DataFrame:
    """Stratified estimates, 95% CIs from a rescaled stratified bootstrap (resample within each
    stratum x county, finite-population corrected), widened for constant strata (protocol 10.4): a
    sampled (not census) stratum whose every y is equal moves to its exact one-sided 95% bound, one
    stratum at a time, the others at their point estimates; the wider interval is kept.
    Column `widened by` names the strata that set a bound. Strata in ASSUMED_ZERO (developed western
    footprints) are not widened: the protocol states that developed land holds no poultry houses and
    reports their exact bound on its own row ('assumption check ...') instead."""
    es = set(es or C.EASTERN_SHORE)
    obj = frame[frame.kind == "object"]
    mapped = obj[obj.stratum.isin(["S1", "S2", "S3"])]
    mapped_all, mapped_es = len(mapped), int(mapped.county.isin(es).sum())
    west = set(mapped.county) - es
    G = groups(frame, final, unsure_as_house, uc_as_house)
    means = [(h, c, N, y.mean(), (y * area).mean()) for h, c, N, y, area in G]
    point = _derived(_totals(means, k, west, k_f), mapped_es, mapped_all)
    rng = np.random.default_rng(seed)
    scale = [np.sqrt(max(0.0, 1 - len(y) / N) * len(y) / (len(y) - 1)) if len(y) > 1 else 0.0
             for h, c, N, y, area in G]
    boots = []
    for _ in range(B):
        Mb = []
        for (h, c, N, y, area), (_, _, _, my, mya), f in zip(G, means, scale):
            i = rng.integers(0, len(y), len(y))
            Mb.append((h, c, N, my + f * (y[i].mean() - my), mya + f * ((y[i] * area[i]).mean() - mya)))
        boots.append(_derived(_totals(Mb, k, west, k_f), mapped_es, mapped_all))
    Bt = pd.DataFrame(boots)
    out = pd.DataFrame({"estimate": pd.Series(point), "low": Bt.quantile(0.025), "high": Bt.quantile(0.975)})
    out["widened by"] = ""
    mpp = mean_per_positive_cell(G)
    for h in sorted({g[0] for g in G}):
        gh = [g for g in G if g[0] == h]
        n = sum(len(g[3]) for g in gh)
        if all(len(g[3]) == g[2] for g in gh):            # census: no sampling error
            continue
        if h in ASSUMED_ZERO:
            ys = np.concatenate([g[3] for g in gh]); Nh = sum(g[2] for g in gh)
            k_ = int(ys.sum())
            out.loc[f"assumption check: {h} houses found in sample", ["estimate", "low", "high"]] = [k_, k_, k_]
            out.loc[f"assumption check: {h} exact 95% upper bound (houses)", ["estimate", "low", "high"]] = \
                [np.nan, 0.0, Nh * (1 - 0.05 ** (1.0 / n)) if k_ == 0 else np.nan]
            out.loc[out.index.str.startswith("assumption check"), "widened by"] = ""
            continue
        ys = np.concatenate([g[3] for g in gh])
        if h in CELL_STRATA:
            if ys.any():
                continue
            val = (1.0 - 0.05 ** (1.0 / n)) * mpp        # houses per cell at the bound
            swap = {(g[0], g[1]): (val, val * g[4].mean() if len(g[4]) else 0.0) for g in gh}
        else:
            if not (ys.all() or not ys.any()):
                continue
            b = _cp_one_sided(n, bool(ys.all()))
            swap = {(g[0], g[1]): (b, b * g[4].mean()) for g in gh}
        Ms = [(hh, c, N, *swap[(hh, c)]) if (hh, c) in swap else (hh, c, N, my, mya) for hh, c, N, my, mya in means]
        alt = pd.Series(_derived(_totals(Ms, k, west, k_f), mapped_es, mapped_all))
        lower, higher = alt < out["low"] - 1e-12, alt > out["high"] + 1e-12
        out.loc[lower, "low"] = alt[lower]
        out.loc[higher, "high"] = alt[higher]
        out.loc[lower | higher, "widened by"] += (h + " ")
    out["widened by"] = out["widened by"].str.strip()
    return out


def residual_table(frame: pd.DataFrame, final: pd.Series, est: pd.DataFrame, q: pd.DataFrame | None = None) -> pd.DataFrame:
    """Protocol 10.5, its own table (never inside the CI of houses on a list).
    Design: cell expansion with its bootstrap CI (from `est`), plus, for each zero-hit cell stratum,
    its exact one-sided 95% bound in houses (cells x mean count per positive cell).
    Model: R = L q / (1 - q) per region, q from capture_rates (with its CI)."""
    G = groups(frame, final)
    mpp = mean_per_positive_cell(G)
    rows = []
    for r in ("ES", "west", "total"):
        e = est.loc[f"residual: cell expansion ({r})"]
        rows.append({"residual": f"cell expansion ({r})", "estimate": e.estimate, "low": e.low, "high": e.high,
                     "note": "S6A/B/C" if r == "ES" else "S6W-A/B; far western cells not covered" if r == "west" else ""})
    for h in RESIDUAL_CELLS:
        gh = [g for g in G if g[0] == h]
        if not gh:
            continue
        N, n = sum(g[2] for g in gh), sum(len(g[3]) for g in gh)
        if not any(g[3].any() for g in gh):
            cells_ = N * (1 - 0.05 ** (1.0 / n))
            rows.append({"residual": f"zero-hit bound {h}", "estimate": 0.0, "low": 0.0, "high": cells_ * mpp,
                         "note": f"{cells_:.0f} cells x {mpp:.2f} houses per positive cell"
                                 + (" (assumed: no positive cell yet)" if mpp == 3.0 else "")})
    if q is not None:
        for region_, Lrow, qrow in (("ES", "list houses off the tracing (ES), L_ES", "q_ES (no footprint, no release outline)"),
                                    ("west", "list houses (west), L_W", "q_W (no footprint, no step-0 detection)")):
            L = est.loc[Lrow, "estimate"]
            qq = q.loc[qrow]
            f = lambda x: L * x / (1 - x) if x < 1 else np.inf
            rows.append({"residual": f"model ({region_})", "estimate": f(qq.q), "low": f(qq.low), "high": f(qq.high),
                         "note": "assumes traced houses represent houses off the tracing"
                                 + ("; and that ES capture rates transfer west" if region_ == "west" else "")})
    return pd.DataFrame(rows).set_index("residual")


def stratum_table(frame: pd.DataFrame, final: pd.Series, unsure_as_house: bool = False,
                  uc_as_house: bool = False) -> pd.DataFrame:
    """Per stratum: N, n labelled, share standing house (objects; Wilson + exact 95%) or houses per cell."""
    from scipy.stats import beta

    from geo_anom.task1.review import wilson
    rows = []
    G = groups(frame, final, unsure_as_house, uc_as_house)
    for h in OBJECT_STRATA + CELL_STRATA:
        gh = [g for g in G if g[0] == h]
        N = int((frame.stratum == h).sum())
        if not gh:
            rows.append({"stratum": h, "what": STRATUM_NAMES[h], "N": N, "n": 0})
            continue
        n = sum(len(g[3]) for g in gh)
        est = sum(g[2] * g[3].mean() for g in gh) / sum(g[2] for g in gh)   # stratified share / mean
        r = {"stratum": h, "what": STRATUM_NAMES[h], "N": N, "n": n, "estimate": est}
        if h in OBJECT_STRATA:
            kk = int(sum(g[3].sum() for g in gh))
            r["houses in sample"] = kk
            r["wilson low"], r["wilson high"] = wilson(kk, n)
            r["exact low"] = beta.ppf(0.025, kk, n - kk + 1) if kk > 0 else 0.0
            r["exact high"] = beta.ppf(0.975, kk + 1, n - kk) if kk < n else 1.0
        else:
            r["houses in sample"] = int(sum(g[3].sum() for g in gh))
            if r["houses in sample"] == 0 and n < N:
                r["exact high"] = N * (1 - 0.05 ** (1.0 / n))     # positive cells, one-sided 95%
        rows.append(r)
    return pd.DataFrame(rows).set_index("stratum")


# ── meta ───────────────────────────────────────────────────────────────────────

def meta(release_dir: Path, traced_path: Path, seed: int, extra: dict | None = None) -> dict:
    from geo_anom.task1.pipeline import git_commit
    return {"made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "version": VERSION,
            "git_commit": git_commit(), "protocol": str(PROTOCOL.relative_to(ROOT)),
            "protocol_sha256": sha256_file(PROTOCOL),
            "release_manifest_sha256": sha256_file(Path(release_dir) / "MANIFEST.json"),
            "traced_sha256": sha256_file(Path(traced_path)), "seed": seed, "year": YEAR,
            "sizes": SIZES, "pilot": PILOT, "calibration": CALIBRATION, **(extra or {})}
