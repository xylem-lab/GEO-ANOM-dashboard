"""
Checking detections by eye: is this a poultry house or not? (notebook 07)

    build_queue(counties)        what to look at, shuffled:
                                   es_unmatched  Delmarva detections with no USGS hand-traced
                                                 house under them (new since 2016/17, or wrong)
                                   unverified    every detection outside the hand-traced area
                                   control       detections on a traced house -- known real, mixed
                                                 in blind to check the reviewer
    LabelStore(path, reviewer)   one CSV per reviewer on the shared drive; append-only,
                                 the latest label per detection wins (so "back" = relabel)
    review_ui(queue, store)      photo + buttons (ipywidgets), next photos prefetched
    load_labels / summarize      precision per county with unsure/unlabelled as a range,
                                 control agreement, agreement between reviewers
    confirmed_keys(labels)       detections every reviewer called a poultry house

The reviewer sees only the photo and the outline in question -- no county, no
group, no model score -- so labels can't lean on what we expect.

Key = `candidate_id` from buildings.geojson (e.g. "wicomico/r000_c011_000"):
county + tile + index, stable as long as a county isn't re-run.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from geo_anom.task1 import county as C
from geo_anom.task1 import region

LABELS = ["poultry house", "not poultry", "unsure"]
GROUPS = ["es_unmatched", "unverified", "control"]
UTM = region.UTM


def build_queue(counties: list[str], root: Path | None = None, gt: gpd.GeoDataFrame | None = None,
                n_controls: int = 40, seed: int = 0) -> gpd.GeoDataFrame:
    """Every detection to review, one row each, in a fixed random order."""
    from geo_anom.task1.evaluate import load_ground_truth

    gt = gt if gt is not None else load_ground_truth()
    gt_area = gpd.GeoSeries([gt.to_crs(UTM).unary_union.convex_hull.buffer(500)], crs=UTM).iloc[0]
    parts, matched = [], []
    for n in counties:
        out = C.county_out(n, root)
        summary = json.loads((out / "county_summary.json").read_text())
        _, sites_run, bld = C.load_county_run(out)
        cty = region.county_boundary(n)
        b = C.county_buildings(bld, cty)
        if not len(b):
            continue
        items = {s["tile_path"]: s.get("naip_item_ids") for s in sites_run}
        b["naip_item_ids"] = b["tile_path"].map(items)
        b["county"] = n
        if summary["accuracy"] is None:
            b["group"] = "unverified"
            parts.append(b)
        else:
            hit = C.compare_with_ground_truth(b, gt, cty)["hit_b"]
            # outside the area USGS traced (e.g. part of Cecil) a detection isn't "missing from
            # the tracing" -- it's simply unverified (same extent rule as evaluate.evaluate_run)
            traced = gt_area.contains(b.centroid)
            b["group"] = np.where(b.index.isin(hit), "control", np.where(traced, "es_unmatched", "unverified"))
            parts.append(b[b.group != "control"])
            matched.append(b[b.group == "control"])
    rng = np.random.default_rng(seed)
    if matched:
        m = pd.concat(matched)
        parts.append(m.iloc[rng.choice(len(m), size=min(n_controls, len(m)), replace=False)])
    if not parts:
        return gpd.GeoDataFrame(columns=["key", "county", "group", "geometry"], geometry="geometry", crs=UTM)
    q = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=UTM)
    c = q.geometry.centroid.to_crs(4326)
    q["lon"], q["lat"] = c.x, c.y
    q = q.rename(columns={"candidate_id": "key"})
    keep = ["key", "county", "group", "area_m2", "length_m", "width_m", "mean_prob", "tile_path",
            "naip_item_ids", "lon", "lat", "geometry"]
    q = q[[k for k in keep if k in q.columns]]
    if q["key"].duplicated().any():
        raise ValueError("candidate_id is not unique across the queue")
    return q.iloc[rng.permutation(len(q))].reset_index(drop=True)


# ── photos ─────────────────────────────────────────────────────────────────────

def chip(row, size_m: float = 500):
    """(RGB uint8 HWC, transform, crs) of a size_m square centred on the detection,
    from the same NAIP images the run used (streamed; a local tile if there is one)."""
    from geo_anom.task1.tiles import ROOT, fetch_window

    tp = ROOT / row["tile_path"] if isinstance(row.get("tile_path"), str) else None
    if tp is not None and tp.exists():
        import rasterio
        from pyproj import Transformer
        from rasterio.windows import from_bounds
        with rasterio.open(tp) as src:
            x, y = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform(row["lon"], row["lat"])
            h = size_m / 2
            win = from_bounds(x - h, y - h, x + h, y + h, src.transform).round_offsets().round_lengths()
            img = np.moveaxis(src.read([1, 2, 3], window=win, boundless=True, fill_value=0), 0, -1)
            return img, src.window_transform(win), src.crs
    ids = row.get("naip_item_ids")
    got = fetch_window(row["lon"], row["lat"], size_m, item_ids=list(ids) if ids is not None else None)
    if got is None:
        return None
    img4, t, crs = got
    return img4[..., :3], t, crs


def render(row, got, zoom_m: float = 160, px: int = 520) -> bytes:
    """PNG: the surroundings (left) and a close-up (right), outline in yellow."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import Polygon as MplPolygon

    from geo_anom.task1.viz import stretch

    # Figure API, not pyplot: safe in the prefetch threads and leaves the notebook's backend alone
    fig = Figure(figsize=(2 * px / 100, px / 100), dpi=100)
    FigureCanvasAgg(fig)
    axs = fig.subplots(1, 2)
    if got is None:
        for ax in axs:
            ax.text(0.5, 0.5, "no imagery", ha="center"); ax.set_axis_off()
    else:
        img, t, crs = got
        geom = gpd.GeoSeries([row["geometry"]], crs=UTM).to_crs(crs).iloc[0]
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        h, w = img.shape[:2]
        shown = stretch(img)
        res = abs(t.a)
        for ax, half in zip(axs, (w / 2, zoom_m / res / 2)):
            ax.imshow(shown)
            for poly in polys:
                xy = np.array([~t * c[:2] for c in poly.exterior.coords])
                ax.add_patch(MplPolygon(xy, closed=True, fill=False, ec="yellow", lw=1.6))
            ax.set_xlim(w / 2 - half, w / 2 + half); ax.set_ylim(h / 2 + half, h / 2 - half)
            ax.set_axis_off()
            bar = 100 if 2 * half * res > 300 else 50
            ax.plot([w / 2 - half * 0.9, w / 2 - half * 0.9 + bar / res], [h / 2 + half * 0.9] * 2, color="white", lw=3)
            ax.text(w / 2 - half * 0.9, h / 2 + half * 0.82, f"{bar} m", color="white", fontsize=9)
    fig.subplots_adjust(0, 0, 1, 1, wspace=0.02)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()


# ── labels ─────────────────────────────────────────────────────────────────────

class LabelStore:
    """Append-only CSV of one reviewer's labels."""

    cols = ["key", "label", "reviewer", "labelled_at", "county", "group", "code"]

    def __init__(self, path: Path, reviewer: str, code: str = ""):
        if not reviewer.strip():
            raise ValueError("set REVIEWER to your name or initials")
        self.path, self.reviewer, self.code = Path(path), reviewer.strip(), code
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            pd.DataFrame(columns=self.cols).to_csv(self.path, index=False)

    def add(self, row, label: str):
        if label not in LABELS:
            raise ValueError(f"label must be one of {LABELS}")
        rec = {"key": row["key"], "label": label, "reviewer": self.reviewer,
               "labelled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "county": row["county"], "group": row["group"], "code": self.code}
        pd.DataFrame([rec], columns=self.cols).to_csv(self.path, mode="a", header=False, index=False)

    def latest(self) -> pd.DataFrame:
        return latest(pd.read_csv(self.path))

    def done(self) -> set:
        return set(self.latest()["key"])


def latest(raw: pd.DataFrame) -> pd.DataFrame:
    """Last label per (key, reviewer)."""
    if raw.empty:
        return raw
    return raw.sort_values("labelled_at").groupby(["key", "reviewer"], as_index=False).last()


def load_labels(folder: Path) -> pd.DataFrame:
    """Every reviewer's latest labels from labels_<reviewer>.csv files."""
    files = sorted(Path(folder).glob("labels_*.csv"))
    raw = pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame(columns=LabelStore.cols)
    return latest(raw)


def confirmed_keys(labels: pd.DataFrame) -> set:
    """Detections that every reviewer who saw them called a poultry house."""
    if labels.empty:
        return set()
    ok = labels.groupby("key")["label"].agg(lambda s: (s == "poultry house").all())
    return set(ok[ok].index)


def cohen_kappa(a, b) -> float:
    a, b = pd.Series(list(a)), pd.Series(list(b))
    po = float((a.values == b.values).mean())
    cats = set(a) | set(b)
    pe = sum(float((a == c).mean()) * float((b == c).mean()) for c in cats)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def summarize(queue: pd.DataFrame, labels: pd.DataFrame, summaries: dict) -> dict:
    """Tables for notebook 07 (one reviewer's labels per key: the consensus is
    'poultry house' only if all reviewers agree, 'not poultry' if any says so,
    else 'unsure')."""
    if labels.empty:
        cons = pd.Series(dtype=object)
    else:
        def one(s):
            if (s == "poultry house").all():
                return "poultry house"
            return "not poultry" if (s == "not poultry").any() else "unsure"
        cons = labels.groupby("key")["label"].agg(one)
    q = queue[["key", "county", "group"]].copy()
    q["label"] = q["key"].map(cons).fillna("not yet")

    counts = q.pivot_table(index=["group", "county"], columns="label", values="key", aggfunc="count", fill_value=0)

    rows = []
    for n, s in summaries.items():
        a = s["accuracy"]
        if not a:
            continue
        qq = q[(q.county == n) & (q.group == "es_unmatched")]
        real, unsure, todo = (qq.label == "poultry house").sum(), (qq.label == "unsure").sum(), (qq.label == "not yet").sum()
        det = a["detections"]
        rows.append({"county": n, "detections": det, "on a traced house": a["tp"], "not traced: checked real": real,
                     "checked not poultry": (qq.label == "not poultry").sum(), "unsure": unsure, "not yet checked": todo,
                     "precision (traced only)": a["tp"] / det,
                     "precision low": (a["tp"] + real) / det,
                     "precision high": 1 - (qq.label == "not poultry").sum() / det})
    precision = pd.DataFrame(rows).set_index("county") if rows else pd.DataFrame()

    ctrl = q[(q.group == "control") & (q.label != "not yet")]
    control = {"checked": len(ctrl), "called poultry house": int((ctrl.label == "poultry house").sum()),
               "agreement": float((ctrl.label == "poultry house").mean()) if len(ctrl) else None}

    unv = q[q.group == "unverified"]
    unverified = unv.pivot_table(index="county", columns="label", values="key", aggfunc="count", fill_value=0) if len(unv) else pd.DataFrame()

    agreement = None
    if not labels.empty and labels.reviewer.nunique() > 1:
        w = labels.pivot(index="key", columns="reviewer", values="label").dropna()
        r = list(w.columns)
        agreement = pd.DataFrame([{"reviewers": f"{r[i]} vs {r[j]}", "both labelled": len(w),
                                   "same label": float((w[r[i]] == w[r[j]]).mean()),
                                   "cohen kappa": cohen_kappa(w[r[i]], w[r[j]])}
                                  for i in range(len(r)) for j in range(i + 1, len(r))])
    return {"by_key": q, "counts": counts, "precision": precision, "control": control,
            "unverified": unverified, "agreement": agreement}


# ── the review screen ──────────────────────────────────────────────────────────

def review_ui(queue: gpd.GeoDataFrame, store: LabelStore, prefetch: int = 4, size_m: float = 500):
    """Photo + buttons. Skips what this reviewer has already labelled; fetches the
    next photos in the background while you look at this one."""
    from concurrent.futures import ThreadPoolExecutor

    import ipywidgets as W
    from IPython.display import display

    todo = [i for i, k in enumerate(queue["key"]) if k not in store.done()]
    state = {"pos": 0, "history": []}
    pool = ThreadPoolExecutor(max_workers=3)
    futures = {}

    def want(pos):
        for p in range(pos, min(pos + prefetch + 1, len(todo))):
            i = todo[p]
            if i not in futures:
                futures[i] = pool.submit(lambda r: render(r, chip(r, size_m)), queue.iloc[i])

    img = W.Image(format="png", layout=W.Layout(width="100%", max_width="1040px"))
    status = W.HTML()
    buttons = [W.Button(description=l, button_style=s, layout=W.Layout(width="150px"))
               for l, s in zip(LABELS, ["success", "danger", "warning"])]
    back = W.Button(description="← back", layout=W.Layout(width="90px"))

    def show():
        p = state["pos"]
        if p >= len(todo):
            img.value = b""
            status.value = f"<b>All done</b> — {len(todo)} labelled in this queue by {store.reviewer}. Run the summary cells."
            for b in buttons + [back]:
                b.disabled = True
            return
        want(p)
        status.value = (f"<b>{p + 1} / {len(todo)}</b> &nbsp; Is the <span style='color:#d4b000'>yellow outline</span> "
                        f"a poultry house? (left: 500 m around it, right: close-up)")
        try:
            img.value = futures[todo[p]].result()
        except Exception as e:     # imagery hiccup: say so, the reviewer can mark unsure
            status.value += f"<br><span style='color:red'>could not load photo: {e}</span>"
            img.value = b""

    def on(label):
        def f(_):
            if state["pos"] >= len(todo):
                return
            store.add(queue.iloc[todo[state["pos"]]], label)
            state["history"].append(state["pos"])
            state["pos"] += 1
            show()
        return f

    def on_back(_):
        if state["history"]:
            state["pos"] = state["history"].pop()
            show()

    for b, l in zip(buttons, LABELS):
        b.on_click(on(l))
    back.on_click(on_back)
    ui = W.VBox([status, img, W.HBox(buttons + [back])])
    show()
    display(ui)
    return ui
