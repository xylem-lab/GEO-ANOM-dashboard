"""
Matplotlib helpers for checking detections by eye in the notebooks.

Everything is drawn in tile pixel coordinates, so what you see is exactly
the image the model was given (1 m/pixel, 4-band NAIP resampled from 0.3 m).
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import box

KEPT_COLOR = "#2ecc40"
REJECT_COLOR = "#ff4136"


def stretch(band_stack: np.ndarray, lo: float = 2, hi: float = 98) -> np.ndarray:
    """Percentile contrast stretch to 0-1 for display only."""
    out = np.zeros(band_stack.shape, dtype=np.float32)
    for i in range(band_stack.shape[2]):
        b = band_stack[..., i].astype(np.float32)
        p1, p2 = np.percentile(b, (lo, hi))
        out[..., i] = np.clip((b - p1) / max(p2 - p1, 1e-6), 0, 1)
    return out


def rgb(img: np.ndarray) -> np.ndarray:
    return stretch(img[..., :3])


def false_color(img: np.ndarray) -> np.ndarray:
    """NIR-R-G: vegetation red, roofs/pavement grey-cyan, water dark."""
    return stretch(img[..., [3, 0, 1]])


def _to_px(poly, transform) -> np.ndarray:
    inv = ~transform
    return np.array([inv * (x, y) for x, y in poly.exterior.coords])


def show_tile(img: np.ndarray, title: str = "", size: float = 7):
    fig, ax = plt.subplots(1, 2, figsize=(2 * size, size))
    ax[0].imshow(rgb(img)); ax[0].set_title("True color (R,G,B)")
    ax[1].imshow(false_color(img)); ax[1].set_title("False color (NIR,R,G)")
    for a in ax:
        a.set_axis_off()
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def show_model_output(img: np.ndarray, prob: np.ndarray, mask: np.ndarray, size: float = 6):
    fig, ax = plt.subplots(1, 3, figsize=(3 * size, size))
    ax[0].imshow(rgb(img)); ax[0].set_title("Image")
    im = ax[1].imshow(prob, vmin=0, vmax=1, cmap="magma"); ax[1].set_title("U-Net building probability")
    fig.colorbar(im, ax=ax[1], fraction=0.046)
    ax[2].imshow(rgb(img)); ax[2].imshow(np.ma.masked_equal(mask, 0), cmap="autumn", alpha=0.6)
    ax[2].set_title(f"Hard mask (prob > 0.5): {int(mask.sum()):,} px")
    for a in ax:
        a.set_axis_off()
    fig.tight_layout()
    return fig


def show_boxes(result, show_rejected: bool = True, label: bool = True, size: float = 10,
               zoom="auto", boxes: bool = True):
    """Detections over the image: green = kept, red dashed = rejected.

    `boxes=True` draws each candidate's minimum rotated rectangle (the shape
    the length/width/aspect filter actually measures); the footprint outline
    is drawn too. `zoom=(x0, y0, x1, y1)` in pixels crops the view;
    "auto" (default) frames all candidates plus 120 m; None shows the whole tile.
    """
    t = result.meta["transform"]
    fig, ax = plt.subplots(figsize=(size, size))
    ax.imshow(rgb(result.img))
    for n, c in enumerate(result.candidates):
        if not c["kept"] and not show_rejected:
            continue
        color = KEPT_COLOR if c["kept"] else REJECT_COLOR
        ls = "-" if c["kept"] else "--"
        ax.add_patch(MplPolygon(_to_px(c["poly"], t), closed=True, fill=False, ec=color, lw=1, ls=ls))
        if boxes:
            ax.add_patch(MplPolygon(_to_px(c["poly"].minimum_rotated_rectangle, t), closed=True,
                                    fill=False, ec=color, lw=2 if c["kept"] else 1, ls=ls))
        if label:
            cx, cy = ~t * (c["poly"].centroid.x, c["poly"].centroid.y)
            ax.text(cx, cy, str(n), color="white", fontsize=8, ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.15", fc=color, ec="none", alpha=0.85))
    if zoom == "auto":
        zoom = None
        if result.candidates:
            pts = np.vstack([_to_px(c["poly"], t) for c in result.candidates])
            pad = 120 / result.meta["res_m"]
            zoom = (*(pts.min(0) - pad), *(pts.max(0) + pad))
    if zoom:
        x0, y0, x1, y1 = zoom
        ax.set_xlim(x0, x1); ax.set_ylim(y1, y0)
    ax.set_axis_off()
    ax.set_title(f"{result.site['farm_name']}: {len(result.kept)} kept (green), "
                 f"{len(result.rejected)} rejected (red dashed)")
    fig.tight_layout()
    return fig


def show_candidate(result, n: int, pad_m: float = 40, size: float = 5):
    """Close-up of one candidate by its number in show_boxes()."""
    c = result.candidates[n]
    t = result.meta["transform"]
    px = _to_px(c["poly"], t)
    pad = pad_m / result.meta["res_m"]
    x0, y0 = px.min(0) - pad
    x1, y1 = px.max(0) + pad
    fig, ax = plt.subplots(1, 2, figsize=(2 * size, size))
    for a, im in zip(ax, (rgb(result.img), false_color(result.img))):
        a.imshow(im)
        a.add_patch(MplPolygon(px, closed=True, fill=False,
                               ec=KEPT_COLOR if c["kept"] else REJECT_COLOR, lw=2))
        a.set_xlim(x0, x1); a.set_ylim(y1, y0); a.set_axis_off()
    s = c["stats"]
    fig.suptitle(f"#{n} {'KEPT' if c['kept'] else 'REJECTED'} -- {s['area_m2']:.0f} m², "
                 f"{s['length_m']:.0f} x {s['width_m']:.0f} m, aspect {s['aspect']:.1f}"
                 + (f"\n{'; '.join(c['reasons'])}" if c["reasons"] else ""))
    fig.tight_layout()
    return fig


def _auto_zoom(result, pad_m: float = 120):
    if not result.candidates:
        return None
    t = result.meta["transform"]
    pts = np.vstack([_to_px(c["poly"], t) for c in result.candidates])
    pad = pad_m / result.meta["res_m"]
    return (*(pts.min(0) - pad), *(pts.max(0) + pad))


def show_area(result, size: float = 10, title: str | None = None):
    """The same view as show_boxes(), with no detections drawn -- for
    counting the buildings yourself before looking at the model's answer."""
    fig, ax = plt.subplots(figsize=(size, size))
    ax.imshow(rgb(result.img))
    zoom = _auto_zoom(result)
    if zoom:
        x0, y0, x1, y1 = zoom
        ax.set_xlim(x0, x1); ax.set_ylim(y1, y0)
    ax.set_axis_off()
    ax.set_title(title or result.site["farm_name"])
    fig.tight_layout()
    return fig


# --- Whole-dataset views (read a saved run; no model needed) --------------

def farm_thumbnail(ax, site: dict, buildings, pad_m: float = 150, half_m: float = 500):
    """One farm from a saved run: its own buildings in the species colour,
    neighbours' buildings in thin white, the registry point as a yellow x."""
    import rasterio
    from pyproj import Transformer
    from rasterio.windows import Window

    from geo_anom.task1.species import GROUPS, species_group
    from geo_anom.task1.tiles import site_id, tile_path

    with rasterio.open(tile_path(site)) as src:
        crs, t, b = src.crs, src.transform, src.bounds
        to_tile = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
        px, py = to_tile(site["lon"], site["lat"])
        sid = site_id(site)
        in_tile = buildings.to_crs(crs).cx[b.left:b.right, b.bottom:b.top]
        own = in_tile[in_tile["assigned_site_id"] == sid]
        frame = own if len(own) else in_tile
        if len(frame):
            x0, y0, x1, y1 = frame.total_bounds
            x0, y0, x1, y1 = x0 - pad_m, y0 - pad_m, x1 + pad_m, y1 + pad_m
        else:
            x0, y0, x1, y1 = px - half_m, py - half_m, px + half_m, py + half_m
        c0, r0 = ~t * (x0, y1)
        c1, r1 = ~t * (x1, y0)
        c0, r0 = max(int(c0), 0), max(int(r0), 0)
        c1, r1 = min(int(c1), src.width), min(int(r1), src.height)
        win = Window(c0, r0, max(c1 - c0, 1), max(r1 - r0, 1))
        img = np.moveaxis(src.read([1, 2, 3], window=win), 0, -1)
        wt = src.window_transform(win)

    ax.imshow(stretch(img))
    color = np.array(GROUPS[species_group(site.get("animal_type"))][1]) / 255
    for geom, mine in [(g, True) for g in own.geometry] + \
                      [(g, False) for g in in_tile[in_tile["assigned_site_id"] != sid].geometry]:
        for poly in ([geom] if geom.geom_type == "Polygon" else geom.geoms):
            xy = np.array([~wt * p for p in poly.exterior.coords])
            ax.add_patch(MplPolygon(xy, closed=True, fill=mine, fc=(*color, 0.35) if mine else None,
                                    ec=color if mine else "white", lw=1.6 if mine else 0.6))
    rx, ry = ~wt * (px, py)
    if 0 <= rx <= img.shape[1] and 0 <= ry <= img.shape[0]:
        ax.plot(rx, ry, "x", color="yellow", ms=9, mew=2.5)
    ax.set_xlim(0, img.shape[1]); ax.set_ylim(img.shape[0], 0)
    ax.set_axis_off()
    name = site["farm_name"] if len(site["farm_name"]) <= 34 else site["farm_name"][:32] + "…"
    ax.set_title(f"{name}\n{site.get('county')} · {GROUPS[species_group(site.get('animal_type'))][0].split(' (')[0]}"
                 f" · {len(own)} bldg", fontsize=9)


def gallery(sites: list[dict], buildings, cols: int = 4, size: float = 4.2, title: str = ""):
    """Grid of farm_thumbnail() for a list of sites (one page)."""
    if not sites:
        print("No farms to show.")
        return None
    rows = int(np.ceil(len(sites) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * size, rows * size))
    axes = np.atleast_1d(axes).ravel()
    for ax, s in zip(axes, sites):
        try:
            farm_thumbnail(ax, s, buildings)
        except Exception as e:  # a bad tile shouldn't kill the whole page
            ax.set_axis_off(); ax.set_title(f"{s['farm_name'][:30]}\n(error: {type(e).__name__})", fontsize=9)
    for ax in axes[len(sites):]:
        ax.set_axis_off()
    if title:
        fig.suptitle(title, fontsize=14)
    fig.tight_layout()
    return fig


def state_map(buildings, farms, sites: list[dict], satellite: bool = True):
    """Interactive map (folium): one dot per building coloured by species,
    registry pins for farms with no detected building. Needs internet for
    the basemap only."""
    import folium

    from geo_anom.task1.species import GROUPS, species_group
    from geo_anom.task1.tiles import site_id

    m = folium.Map(location=[38.6, -76.0], zoom_start=8, tiles=None, control_scale=True)
    if satellite:
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery", name="Satellite").add_to(m)
    folium.TileLayer("OpenStreetMap", name="Streets").add_to(m)

    def hexc(rgb):
        return "#%02x%02x%02x" % tuple(rgb)

    layers = {g: folium.FeatureGroup(name=f"{label}", show=True) for g, (label, _) in GROUPS.items()}
    cent = buildings.to_crs("EPSG:32618").centroid.to_crs("EPSG:4326")
    for (_, b), c in zip(buildings.iterrows(), cent):
        g = b.get("species_group") or "unknown"
        folium.CircleMarker(
            [c.y, c.x], radius=3, color=hexc(GROUPS[g][1]), fill=True, fill_opacity=0.9, weight=1,
            tooltip=f"{b['assigned_farm']} · {GROUPS[g][0]} · {b['area_m2']:.0f} m² · conf {b.get('mean_prob', 0):.2f}",
        ).add_to(layers[g])
    for lyr in layers.values():
        lyr.add_to(m)

    missing = folium.FeatureGroup(name="Registry farms with NO detected building", show=True)
    zero = set(farms.loc[farms["buildings"] == 0, "site_id"])
    for s in sites:
        if site_id(s) in zero:
            g = species_group(s.get("animal_type"))
            folium.Marker([s["lat"], s["lon"]],
                          tooltip=f"NO BUILDING DETECTED: {s['farm_name']} ({GROUPS[g][0]}, {s.get('headcount') or 0:,} head)",
                          icon=folium.Icon(color="red", icon="question-sign")).add_to(missing)
    missing.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


def location_gallery(points, sites: list[dict], buildings=None, ground_truth=None, size_m: float = 300,
                     cols: int = 4, size: float = 4.0, titles: list[str] | None = None, suptitle: str = ""):
    """Crops around arbitrary locations from whichever tile covers them.

    points: GeoSeries (any CRS) of locations to look at. Each crop is
    size_m x size_m, from the site whose tile centre is nearest (tiles are
    2 km wide, so the nearest centre always contains the point). Our
    buildings are drawn green, ground-truth houses orange.
    """
    import rasterio
    from pyproj import Transformer
    from rasterio.windows import from_bounds

    from geo_anom.task1.tiles import tile_path

    pts = points.to_crs("EPSG:4326")
    if not len(pts):
        print("Nothing to show.")
        return None
    centres = np.array([(s["lon"], s["lat"]) for s in sites])
    rows = int(np.ceil(len(pts) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * size, rows * size))
    axes = np.atleast_1d(axes).ravel()
    for k, (ax, p) in enumerate(zip(axes, pts)):
        s = sites[int(np.argmin(((centres - (p.x, p.y)) ** 2).sum(1)))]
        with rasterio.open(tile_path(s)) as src:
            x, y = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform(p.x, p.y)
            h = size_m / 2
            win = from_bounds(x - h, y - h, x + h, y + h, src.transform).round_offsets().round_lengths()
            img = np.moveaxis(src.read([1, 2, 3], window=win, boundless=True, fill_value=0), 0, -1)
            wt = src.window_transform(win)
            crs = src.crs
        ax.imshow(stretch(img))
        frame = box(x - h, y - h, x + h, y + h)
        for layer, color, lw in ((ground_truth, "#ff9f1c", 2.5), (buildings, "#2ecc40", 1.5)):
            if layer is None:
                continue
            for g in layer.to_crs(crs).geometry:
                if g is None or not g.intersects(frame):
                    continue
                for poly in ([g] if g.geom_type == "Polygon" else g.geoms):
                    xy = np.array([~wt * c[:2] for c in poly.exterior.coords])
                    ax.add_patch(MplPolygon(xy, closed=True, fill=False, ec=color, lw=lw))
        ax.plot(img.shape[1] / 2, img.shape[0] / 2, "+", color="yellow", ms=12, mew=2)
        ax.set_xlim(0, img.shape[1]); ax.set_ylim(img.shape[0], 0); ax.set_axis_off()
        ax.set_title(titles[k] if titles else s.get("grid_id", s["farm_name"]), fontsize=9)
    for ax in axes[len(pts):]:
        ax.set_axis_off()
    if suptitle:
        fig.suptitle(suptitle, fontsize=13)
    fig.tight_layout()
    return fig
