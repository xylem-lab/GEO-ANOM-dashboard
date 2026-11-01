"""
Training data for fine-tuning the poultry-house U-Net (notebook 09; used by notebook 10).

Why: the published model (Robinson et al. 2022) misses about a third of the houses on the
darker 2023 NAIP photos and finds most of the same houses on 2017-2021 photos. Fine-tuning on
2023 photos (plus older years, with brightness/contrast changes) is the planned fix.

    plan_windows(...)    which 512 m windows to download, one per (grid cell, year), with the
                         train / val / test split by whole county
    label_layer(...)     the label polygons and what each means in each year
    download_windows()   NAIP photo of each window, 1 m, 4 bands, resumable  (slow, once)
    build_masks()        0 / 1 / 255 mask for every window from the label layer  (fast;
                         re-run whenever notebook 07 labels change -- no new downloads)
    ChipDataset          random 256 px crops with flips, rotations, scale and colour changes

Mask values: 0 = not a poultry house, 1 = poultry house, 255 = ignore (not used in the loss).
Ignored: a thin band along every traced roof edge (photos of different years are a few
metres apart), no-data pixels, and houses we can't vouch for in that year (below).

Label rules (USGS tracing = Soroka & Duren, 2016/17 photos, every Delmarva house):
    traced          1 in every year  (a few may be gone by 2023 -- by eye ~1 in 8 of the
                                      missed ones; accepted as label noise)
    new_confirmed   our detection, not traced, every 07 reviewer said "poultry house":
                    1 in 2023 (the photo it was found on), ignore in earlier years
    new_unchecked   our detection, not traced, not yet labelled in 07: ignore
    rejected        every 07 reviewer said "not poultry": 0 (a hard negative)
Houses that neither the tracing nor our map has are labelled 0 -- the main remaining
label noise; small because the tracing plus our map covers ~all houses.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from geo_anom.task1 import region, tiles

UTM = region.UTM
WINDOW_M = 512          # houses are up to ~300 m long; a 512 m window holds a whole one at any angle
CROP_PX = 256           # the model's chip size (detect.CHIP_SIZE)
BORDER_M = 2.0          # ignore band on each side of a traced roof edge
YEARS = ["2017", "2021", "2023"]
# whole counties held out: test = never seen in training or model choice; val = picks the epoch
SPLITS = {"test": ["Wicomico", "Queen Anne's"], "val": ["Dorchester"]}

POSITIVE, NEGATIVE, IGNORE = 1, 0, 255
RULES = {  # label value per year; "*" = every year not listed
    "traced": {"*": POSITIVE},
    "new_confirmed": {"2023": POSITIVE, "*": IGNORE},
    "new_unchecked": {"*": IGNORE},
    "rejected": {"*": NEGATIVE},
}


def split_of(county: str, splits: dict = SPLITS) -> str:
    for s, names in splits.items():
        if county in names:
            return s
    return "train"


def value_for(source: str, year: str) -> int:
    r = RULES[source]
    return r.get(str(year), r["*"])


# ── labels ─────────────────────────────────────────────────────────────────────

def label_layer(gt: gpd.GeoDataFrame, houses: gpd.GeoDataFrame | None = None,
                confirmed: gpd.GeoDataFrame | None = None, rejected: gpd.GeoDataFrame | None = None) -> gpd.GeoDataFrame:
    """All label polygons (UTM) with a `source` column (see RULES).

    gt        USGS tracing
    houses    our map (e.g. the final Eastern Shore layer); those not touching a traced
              house become new_unchecked unless 07 settled them
    confirmed / rejected   07 detections every reviewer called poultry / not poultry
    """
    parts = [gpd.GeoDataFrame({"source": ["traced"] * len(gt)}, geometry=gt.to_crs(UTM).geometry.values, crs=UTM)]
    t = parts[0]
    settled = []
    for frame, src in [(confirmed, "new_confirmed"), (rejected, "rejected")]:
        if frame is not None and len(frame):
            f = frame.to_crs(UTM)
            f = f[~f.intersects(t.unary_union)] if src == "new_confirmed" else f
            parts.append(gpd.GeoDataFrame({"source": [src] * len(f)}, geometry=f.geometry.values, crs=UTM))
            settled.append(f.unary_union)
    if houses is not None and len(houses):
        h = houses.to_crs(UTM)
        h = h[~h.intersects(t.unary_union)]
        for s in settled:
            h = h[~h.intersects(s)]
        parts.append(gpd.GeoDataFrame({"source": ["new_unchecked"] * len(h)}, geometry=h.geometry.values, crs=UTM))
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=UTM)


def rasterize_mask(labels: gpd.GeoDataFrame, year: str, transform, shape: tuple, crs,
                   border_m: float = BORDER_M, nodata: np.ndarray | None = None) -> np.ndarray:
    """uint8 mask (0 / 1 / 255) on a window's pixel grid."""
    from rasterio.features import rasterize

    mask = np.zeros(shape, dtype=np.uint8)
    lab = labels.to_crs(crs)
    x0, y1 = transform.c, transform.f
    win = box(x0, y1 + transform.e * shape[0], x0 + transform.a * shape[1], y1)
    lab = lab[lab.intersects(win.buffer(border_m + 1))]
    if len(lab):
        vals = np.array([value_for(s, year) for s in lab.source])
        # order: negatives, then positives, then ignore on top (ignore wins where they overlap)
        for v in (NEGATIVE, POSITIVE):
            g = lab.geometry[vals == v]
            if len(g):
                rasterize(((geom, v) for geom in g), out=mask, transform=transform)
        traced = lab.geometry[lab.source.values == "traced"]
        if border_m > 0 and len(traced):
            ring = [gg.buffer(border_m).difference(gg.buffer(-border_m)) for gg in traced]
            rasterize(((r, IGNORE) for r in ring if not r.is_empty), out=mask, transform=transform)
        ig = lab.geometry[vals == IGNORE]
        if len(ig):
            rasterize(((gg.buffer(border_m), IGNORE) for gg in ig), out=mask, transform=transform)
    if nodata is not None:
        mask[nodata] = IGNORE
    return mask


# ── which windows ──────────────────────────────────────────────────────────────

def house_windows(houses: gpd.GeoDataFrame, window_m: float = WINDOW_M, margin_m: float = 20.0) -> list:
    """Window centres (UTM x, y) so that every house lies whole inside at least one window.

    Greedy: take the first house not yet covered, centre a window on the middle of the
    houses within reach of it, mark every house that now lies whole inside (with margin_m
    to spare) as covered, repeat. Houses come in rows on one farm, so one window usually
    holds a whole farm.
    """
    g = houses.to_crs(UTM).geometry.reset_index(drop=True)
    cen = np.c_[g.centroid.x, g.centroid.y]
    order = np.lexsort((cen[:, 0], -cen[:, 1]))
    covered = np.zeros(len(g), bool)
    half = window_m / 2 - margin_m
    centres = []
    for i in order:
        if covered[i]:
            continue
        near = np.where((np.abs(cen[:, 0] - cen[i, 0]) < half) & (np.abs(cen[:, 1] - cen[i, 1]) < half))[0]
        cx, cy = cen[near].mean(axis=0)
        inner = box(cx - half, cy - half, cx + half, cy + half)
        inside = g.within(inner).values
        if not inside[i]:                      # the middle drifted off this house: centre on it instead
            cx, cy = cen[i]
            inner = box(cx - half, cy - half, cx + half, cy + half)
            inside = g.within(inner).values
        inside[i] = True                       # a house too long for the window still gets one
        covered |= inside
        centres.append((round(float(cx)), round(float(cy))))
    return centres


def plan_windows(counties: list[str], labels: gpd.GeoDataFrame, years: list[str] = YEARS,
                 neg_ratio: float = 0.5, splits: dict = SPLITS, seed: int = 0,
                 window_m: float = WINDOW_M, clear_m: float = 300.0) -> gpd.GeoDataFrame:
    """One row per (window, year).

    positive      windows centred on groups of traced / 07-confirmed houses, every house whole
                  inside at least one window (house_windows)
    hard_negative windows centred on 07-rejected detections that aren't in a house window
    negative      random land squares of the county with no label polygon within clear_m,
                  neg_ratio x the county's positive windows, drawn afresh for each year
    A window belongs to the county its centre falls in, so the split is by whole county.
    """
    rng = np.random.default_rng(seed)
    lab = labels.to_crs(UTM)
    near = lab.unary_union.buffer(clear_m) if len(lab) else None
    if near is not None:
        import shapely
        shapely.prepare(near)
    pos_all = house_windows(lab[lab.source.isin(["traced", "new_confirmed"])], window_m)
    pos_boxes = [box(x - window_m / 2, y - window_m / 2, x + window_m / 2, y + window_m / 2) for x, y in pos_all]
    rej = lab[lab.source == "rejected"]
    hard_all = []
    if len(rej):
        rc = rej.geometry.centroid
        hard_all = [(round(p.x), round(p.y)) for p in rc if not any(b.contains(p) for b in pos_boxes)]

    def sq(x, y):
        return box(x - window_m / 2, y - window_m / 2, x + window_m / 2, y + window_m / 2)

    rows = []
    for name in counties:
        geom = region.county_boundary(name).to_crs(UTM).unary_union
        import shapely
        shapely.prepare(geom)
        pts = lambda cs: [c for c in cs if geom.contains(gpd.points_from_xy([c[0]], [c[1]])[0])]
        pos, hard = pts(pos_all), pts(hard_all)
        x0, y0, x1, y1 = geom.bounds
        land = []
        for a in range(int(x0 // window_m), int(x1 // window_m) + 1):
            for b in range(int(y0 // window_m), int(y1 // window_m) + 1):
                c = ((a + 0.5) * window_m, (b + 0.5) * window_m)
                s = sq(*c)
                if s.intersection(geom).area > 0.9 * s.area and (near is None or not s.intersects(near)):
                    land.append((round(c[0]), round(c[1])))
        n_neg = int(round(neg_ratio * len(pos)))
        for y in years:
            pick = rng.choice(len(land), size=min(n_neg, len(land)), replace=False) if land else []
            negs = [land[k] for k in sorted(pick)]
            for kind, cs in [("positive", pos), ("hard_negative", hard), ("negative", negs)]:
                for cx, cy in cs:
                    cell = f"e{cx}_n{cy}"
                    rows.append({"window_id": f"{y}_{cell}", "cell": cell, "year": str(y), "county": name,
                                 "split": split_of(name, splits), "kind": kind, "geometry": sq(cx, cy)})
    plan = gpd.GeoDataFrame(rows, geometry="geometry", crs=UTM).drop_duplicates("window_id").reset_index(drop=True)
    c = plan.geometry.centroid.to_crs(4326)
    plan["lon"], plan["lat"] = c.x.round(6), c.y.round(6)
    return plan


def extra_windows(plan: gpd.GeoDataFrame, labels: gpd.GeoDataFrame, years: list[str] = YEARS,
                  splits: dict = SPLITS, window_m: float = WINDOW_M) -> gpd.GeoDataFrame:
    """Windows to add after notebook 07 labels arrive, leaving the saved plan untouched
    (so nothing already downloaded is fetched again):
      positive      07-confirmed new houses not whole inside any planned window
      hard_negative 07-rejected detections not inside any planned window (any county;
                    western ones go to the split of their county, i.e. train)
    """
    lab = labels.to_crs(UTM)
    have = plan.to_crs(UTM).drop_duplicates("cell").geometry
    import shapely
    covered = have.unary_union if len(have) else None
    new = lab[(lab.source == "new_confirmed")]
    if covered is not None and len(new):
        new = new[[not any(w.contains(g) for w in have[have.intersects(g)]) for g in new.geometry]]
    rej = lab[lab.source == "rejected"]
    if covered is not None and len(rej):
        rej = rej[~rej.centroid.within(covered)]
    cs = [("positive", c) for c in house_windows(new, window_m)] if len(new) else []
    cs += [("hard_negative", (round(p.x), round(p.y))) for p in rej.centroid]
    if not cs:
        return plan.iloc[0:0]
    pts = gpd.GeoDataFrame({"kind": [k for k, _ in cs]}, geometry=gpd.points_from_xy([c[0] for _, c in cs], [c[1] for _, c in cs]), crs=UTM)
    md = region.md_counties().to_crs(UTM)
    names = md["NAME"].where(~md["NAME"].duplicated(keep=False), md["NAMELSAD"])
    pts = gpd.sjoin(pts, md.assign(county=names)[["county", "geometry"]], predicate="within", how="left")
    rows = []
    for _, r in pts.iterrows():
        cx, cy = round(r.geometry.x), round(r.geometry.y)
        cell = f"e{cx}_n{cy}"
        for y in years:
            rows.append({"window_id": f"{y}_{cell}", "cell": cell, "year": str(y), "county": r["county"],
                         "split": split_of(r["county"], splits), "kind": r["kind"],
                         "geometry": box(cx - window_m / 2, cy - window_m / 2, cx + window_m / 2, cy + window_m / 2)})
    ex = gpd.GeoDataFrame(rows, geometry="geometry", crs=UTM)
    ex = ex[~ex.window_id.isin(set(plan.window_id))].drop_duplicates("window_id")
    c = ex.geometry.centroid.to_crs(4326)
    ex["lon"], ex["lat"] = c.x.round(6), c.y.round(6)
    return ex.reset_index(drop=True)


def review_polygons(review_dir: Path, counties: list[str], root: Path | None = None):
    """(confirmed, rejected) detection outlines from notebook 07 labels, as rectangles (UTM).

    confirmed = every reviewer said "poultry house"; rejected = every reviewer said
    "not poultry". "unsure" or split votes are left out (their houses stay ignored).
    """
    from geo_anom.task1 import county as C
    from geo_anom.task1 import review as R
    from geo_anom.task1.refine import rectangle

    labels = R.load_labels(review_dir)
    empty = gpd.GeoDataFrame(geometry=[], crs=UTM)
    if labels.empty:
        return empty, empty, labels
    conf = R.confirmed_keys(labels)
    bad = labels.groupby("key")["label"].agg(lambda x: (x == "not poultry").all())
    rej = set(bad[bad].index)
    parts = []
    for n in counties:
        out = C.county_out(n, root)
        if not (out / "buildings.geojson").exists():
            continue
        _, _, b = C.load_county_run(out)
        if len(b):
            parts.append(b.to_crs(UTM)[["candidate_id", "geometry"]])
    if not parts:
        return empty, empty, labels
    b = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=UTM)
    b["geometry"] = b.geometry.apply(rectangle)
    return b[b.candidate_id.isin(conf)], b[b.candidate_id.isin(rej)], labels


# ── photos ─────────────────────────────────────────────────────────────────────

def _paths(out: Path, row) -> tuple[Path, Path]:
    base = Path(out) / row["split"] / row["year"]
    return base / "images" / f"{row['window_id']}.npz", base / "masks" / f"{row['window_id']}.npz"


def fetch_window_year(lon: float, lat: float, year: str, window_m: float = WINDOW_M, session=None):
    """The `year` NAIP photo of a window_m square (HWC uint8, profile, items), or None."""
    got = tiles.reference_mosaic(lon, lat, str(year), buffer_km=window_m / 2000, session=session)
    if got is None:
        return None
    data, profile, used = got
    return np.moveaxis(data, 0, -1), profile, used


def download_windows(plan: pd.DataFrame, out: Path, max_workers: int = 8, progress=None) -> pd.DataFrame:
    """Photo of every planned window -> <out>/<split>/<year>/images/<window_id>.npz.

    Resumable: windows already on disk, or recorded as having no photo for that year,
    are skipped. Each finished window is appended to <out>/images.jsonl (item ids,
    flight date, grid) by one thread, so the log stays whole after a crash.
    """
    out = Path(out)
    log_path = out / "images.jsonl"
    seen = set()
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            try:
                seen.add(json.loads(line)["window_id"])
            except Exception:
                pass
    todo = [r for _, r in plan.iterrows() if r["window_id"] not in seen and not _paths(out, r)[0].exists()]
    lock = threading.Lock()
    local = threading.local()

    def one(r):
        if not hasattr(local, "s"):
            local.s = tiles.make_session()
        try:
            got = fetch_window_year(r["lon"], r["lat"], r["year"], session=local.s)
        except Exception as e:
            return r, None, f"error: {type(e).__name__}: {e}"[:200]
        if got is None:
            return r, None, "no photo"
        img, prof, used = got
        p, _ = _paths(out, r)
        p.parent.mkdir(parents=True, exist_ok=True)
        t = prof["transform"]
        np.savez_compressed(p, img=img, transform=np.array([t.a, t.b, t.c, t.d, t.e, t.f]),
                            crs=np.array(str(prof["crs"])))
        return r, {"item_ids": [i["id"] for i in used],
                   "dates": sorted({i["properties"].get("datetime", "")[:10] for i in used}),
                   "gsd_m": [i["properties"].get("gsd") for i in used],
                   "shape": list(img.shape[:2])}, "ok"

    status = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(one, r) for r in todo]
        it = as_completed(futs)
        for f in (progress(it, total=len(futs)) if progress else it):
            r, info, st = f.result()
            k = st.split(":")[0]
            status[k] = status.get(k, 0) + 1
            if st.startswith("error"):
                continue                      # not logged -> retried on the next run
            rec = {"window_id": r["window_id"], "status": st, **(info or {})}
            with lock, open(log_path, "a") as fh:
                fh.write(json.dumps(rec) + "\n")
    print("windows:", status or "nothing to do", f"| {len(plan) - len(todo)} already done")
    return image_log(out)


def image_log(out: Path) -> pd.DataFrame:
    p = Path(out) / "images.jsonl"
    if not p.exists():
        return pd.DataFrame(columns=["window_id", "status"])
    recs = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return pd.DataFrame(recs).drop_duplicates("window_id", keep="last")


def load_window(path: Path):
    from affine import Affine
    z = np.load(path, allow_pickle=False)
    return z["img"], Affine(*z["transform"]), str(z["crs"])


def build_masks(plan: pd.DataFrame, labels: gpd.GeoDataFrame, out: Path, border_m: float = BORDER_M,
                progress=None) -> pd.DataFrame:
    """Mask for every downloaded window (overwrites). Returns per-window pixel counts."""
    rows = []
    it = list(plan.iterrows())
    for _, r in (progress(it) if progress else it):
        ip, mp = _paths(out, r)
        if not ip.exists():
            continue
        img, t, crs = load_window(ip)
        m = rasterize_mask(labels, r["year"], t, img.shape[:2], crs, border_m, nodata=~img.any(axis=2))
        mp.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(mp, mask=m)
        rows.append({"window_id": r["window_id"], "split": r["split"], "year": r["year"], "kind": r["kind"],
                     "county": r["county"], "house_px": int((m == POSITIVE).sum()),
                     "ignore_px": int((m == IGNORE).sum()), "px": int(m.size)})
    return pd.DataFrame(rows)


# ── crops for training ─────────────────────────────────────────────────────────

def augment(img: np.ndarray, mask: np.ndarray, rng: np.random.Generator,
            scale=(0.8, 1.25), gain=(0.6, 1.25), nir_gain=(0.7, 1.3), gamma=(0.8, 1.25),
            contrast=(0.75, 1.25), crop: int = CROP_PX, focus: float = 0.7):
    """Random crop of `crop` px with flip/rotate, rescale and colour changes.

    The colour range is wide on purpose: 2023 photos average ~71 on RGB vs ~100 in 2021,
    so darkening by up to ~40% teaches the model the 2023 look on every year's photo.
    With probability `focus` the crop is placed to contain a house pixel (when the window
    has one); otherwise anywhere. No-data pixels stay 0 (and are ignored in the mask).
    """
    import cv2

    s = rng.uniform(*scale)
    if abs(s - 1) > 0.02:
        h, w = mask.shape
        size = (max(crop, int(round(w * s))), max(crop, int(round(h * s))))
        img = cv2.resize(img, size, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        mask = cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
    h, w = mask.shape
    ys, xs = np.nonzero(mask == POSITIVE) if rng.random() < focus else ((), ())
    if len(ys):
        k = rng.integers(len(ys))
        y = int(np.clip(ys[k] - rng.integers(crop // 8, crop - crop // 8), 0, h - crop))
        x = int(np.clip(xs[k] - rng.integers(crop // 8, crop - crop // 8), 0, w - crop))
    else:
        y = int(rng.integers(0, h - crop + 1))
        x = int(rng.integers(0, w - crop + 1))
    img, mask = img[y:y + crop, x:x + crop], mask[y:y + crop, x:x + crop]
    k = int(rng.integers(0, 4))
    img, mask = np.rot90(img, k), np.rot90(mask, k)
    if rng.random() < 0.5:
        img, mask = img[:, ::-1], mask[:, ::-1]
    nodata = ~img.any(axis=2)
    f = img.astype(np.float32) / 255.0
    g = np.array([rng.uniform(*gain)] * 3 + [rng.uniform(*nir_gain)], dtype=np.float32)
    g[:3] *= rng.uniform(0.93, 1.07, size=3)              # small colour cast
    f = f * g
    mean = f.reshape(-1, 4).mean(axis=0)
    f = (f - mean) * rng.uniform(*contrast) + mean
    f = np.clip(f, 0, 1) ** rng.uniform(*gamma)
    out = np.clip(np.round(f * 255), 1, 255).astype(np.uint8)
    out[nodata] = 0
    return np.ascontiguousarray(out), np.ascontiguousarray(mask)


def center_crop(img: np.ndarray, mask: np.ndarray, crop: int = CROP_PX):
    h, w = mask.shape
    y, x = (h - crop) // 2, (w - crop) // 2
    return img[y:y + crop, x:x + crop], mask[y:y + crop, x:x + crop]


class ChipDataset:
    """torch-style dataset over downloaded windows of one split.

    train=True: a fresh random crop + augmentation each time; train=False: the window's
    centre crop, unchanged (for validation loss -- the real test is notebook 10 running the
    whole pipeline on the held-out counties' 2023 tiles).
    Returns (CHW float32 in [0, 1], HW int64 mask with 255 = ignore).
    """

    def __init__(self, out: Path, plan: pd.DataFrame, split: str, train: bool = True, seed: int = 0,
                 years: list[str] | None = None, cache: bool = True):
        rows = plan[plan.split == split]
        if years:
            rows = rows[rows.year.isin([str(y) for y in years])]
        self.items = [(p, m) for p, m in (_paths(out, r) for _, r in rows.iterrows()) if p.exists() and m.exists()]
        self.train, self.seed, self.cache = train, seed, cache
        self._mem = {}

    def __len__(self):
        return len(self.items)

    def _load(self, i):
        if i in self._mem:
            return self._mem[i]
        ip, mp = self.items[i]
        img = np.load(ip)["img"]
        mask = np.load(mp)["mask"]
        if self.cache:
            self._mem[i] = (img, mask)
        return img, mask

    def __getitem__(self, i):
        import torch
        img, mask = self._load(i)
        if self.train:
            rng = np.random.default_rng()
            img, mask = augment(img, mask, rng)
        else:
            img, mask = center_crop(img, mask)
        x = torch.from_numpy(np.ascontiguousarray(np.moveaxis(img, 2, 0)).astype(np.float32) / 255.0)
        return x, torch.from_numpy(mask.astype(np.int64))
