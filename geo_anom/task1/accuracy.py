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

Keys: "map:<house_id>", "usgs:<row in the SHA-checked tracing>", "cell:<x>_<y>" (UTM 18N km).
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
OBJECT_STRATA = ["S1", "S2", "S3", "S4"]
CELL_STRATA = ["S6A", "S6B", "S6C"]
STRATUM_NAMES = {
    "S1": "map outline on a traced house", "S2": "map outline, not traced", "S3": "map outline outside tracing",
    "S4": "traced house, not mapped", "S6A": "cell with a known house", "S6B": "cell within 1 km",
    "S6C": "cell farther than 1 km",
}
# protocol v1 sample sizes (S3 = all); pilot items per object stratum; calibration items
SIZES = {"S1": 100, "S2": 150, "S3": None, "S4": 150, "S6A": 150, "S6B": 150, "S6C": 100}
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


# ── sample ─────────────────────────────────────────────────────────────────────

def allocate(counts: pd.Series, n: int | None, min_per: int = MIN_PER_COUNTY) -> pd.Series:
    """Proportional allocation of n over counties (largest remainder), at least min_per per county
    (or all its items if fewer); n=None = take everything (census)."""
    counts = counts[counts > 0]
    if n is None or n >= counts.sum():
        return counts.copy()
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


def queue(frame: pd.DataFrame, reviewer: str, phase: str, seed: int = 20261105) -> pd.DataFrame:
    """Items for one interpreter and phase, in that interpreter's own random order.
    phase: 'calibration' | 'pilot' | 'main' (sampled objects not in the pilot) | 'cells'."""
    if phase == "calibration":
        q = frame[frame.role == "calibration"]
    elif phase == "pilot":
        q = frame[(frame.role == "sample") & frame.pilot]
    elif phase == "main":
        q = frame[(frame.role == "sample") & ~frame.pilot & (frame.kind == "object")]
    elif phase == "cells":
        q = frame[(frame.role == "sample") & (frame.kind == "cell")]
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
    note = W.Text(placeholder="note (optional: why, Google Earth date used, where in the cell)",
                  layout=W.Layout(width="600px"))
    buttons = [W.Button(description=v, layout=W.Layout(width="130px" if len(values) < 6 else "60px")) for v in values]
    back = W.Button(description="← back", layout=W.Layout(width="90px"))

    def show():
        p = state["pos"]
        low.value, note.value = False, ""
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
            store.add(items.iloc[todo[state["pos"]]]["key"], v, phase, low.value, note.value)
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
    ui = W.VBox([status, img, W.HBox([low, note]), W.HBox(buttons + [back])])
    show()
    display(ui)
    return ui


def label_ui(items: pd.DataFrame, store: Store, phase: str):
    return _ui(items, store, phase, LABELS, lambda r: render_object(chip2023(r["lon"], r["lat"], 500)),
               "What is at the <span style='color:#ff2bd6'>crosshair</span> on the 2023 photo? "
               "(protocol §2; left 500 m, right close-up)")


def cell_ui(items: pd.DataFrame, store: Store, known: gpd.GeoDataFrame):
    def fn(r):
        kk = known[known.intersects(r["geometry"].buffer(150))]
        return render_cell(chip2023(r["lon"], r["lat"], CELL_M + 200, res=1.2), r["geometry"], kk)
    return _ui(items, store, "cells", CELL_COUNTS, fn,
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


def _totals(M: list, k: dict, west: set) -> dict:
    """Point estimates from per-group means [(stratum, county, N, mean y, mean y*area)]."""
    t = {"C_es": 0.0, "C_west": 0.0, "A_es": 0.0, "A_west": 0.0, "M": 0.0, "A_M": 0.0, "Y": 0.0}
    for h, c, N, my, mya in M:
        if h in ("S1", "S2", "S3"):
            w = "west" if c in west else "es"
            t[f"C_{w}"] += N * my
            t[f"A_{w}"] += N * mya
        elif h == "S4":
            t["M"] += N * my
            t["A_M"] += N * mya * k.get(c, 1.0)
        else:
            t["Y"] += N * my
    return t


def _derived(t: dict, mapped_es: int, mapped_all: int) -> dict:
    T = t["C_es"] + t["M"] + t["Y"]
    a_m = t["A_M"] / t["M"] if t["M"] > 0 else np.nan          # mean roof of a missed standing house
    a_y = t["Y"] * a_m if t["Y"] > 0 else 0.0
    return {
        "precision (Maryland)": (t["C_es"] + t["C_west"]) / mapped_all,
        "precision (Eastern Shore)": t["C_es"] / mapped_es,
        "correct map houses (ES)": t["C_es"],
        "missed traced houses standing": t["M"],
        "houses on neither source": t["Y"],
        "houses standing (ES)": T,
        "recall (ES)": t["C_es"] / T if T else np.nan,
        "roof km2 (ES)": (t["A_es"] + t["A_M"] + a_y) / 1e6,
        "roof km2 (Maryland)": (t["A_es"] + t["A_west"] + t["A_M"] + a_y) / 1e6,
    }


def estimate(frame: pd.DataFrame, final: pd.Series, k: dict, unsure_as_house: bool = False,
             uc_as_house: bool = False, B: int = 2000, seed: int = 2, es: list | None = None) -> pd.DataFrame:
    """Stratified estimates with 95% CIs from a rescaled stratified bootstrap (resample within each
    stratum x county, finite-population corrected)."""
    es = set(es or C.EASTERN_SHORE)
    obj = frame[frame.kind == "object"]
    mapped = obj[obj.stratum.isin(["S1", "S2", "S3"])]
    mapped_all, mapped_es = len(mapped), int(mapped.county.isin(es).sum())
    west = set(mapped.county) - es
    G = groups(frame, final, unsure_as_house, uc_as_house)
    means = [(h, c, N, y.mean(), (y * area).mean()) for h, c, N, y, area in G]
    point = _derived(_totals(means, k, west), mapped_es, mapped_all)
    rng = np.random.default_rng(seed)
    # rescaled bootstrap: a resampled mean's deviation is scaled by sqrt((1 - n/N) n/(n-1)), so the
    # spread matches the without-replacement variance (a census, n = N, has none)
    scale = [np.sqrt(max(0.0, 1 - len(y) / N) * len(y) / (len(y) - 1)) if len(y) > 1 else 0.0
             for h, c, N, y, area in G]
    boots = []
    for _ in range(B):
        Mb = []
        for (h, c, N, y, area), (_, _, _, my, mya), f in zip(G, means, scale):
            i = rng.integers(0, len(y), len(y))
            Mb.append((h, c, N, my + f * (y[i].mean() - my), mya + f * ((y[i] * area[i]).mean() - mya)))
        boots.append(_derived(_totals(Mb, k, west), mapped_es, mapped_all))
    Bt = pd.DataFrame(boots)
    return pd.DataFrame({"estimate": pd.Series(point), "low": Bt.quantile(0.025), "high": Bt.quantile(0.975)})


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
