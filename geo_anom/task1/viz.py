"""
Matplotlib helpers for checking detections by eye in the notebooks.

Everything is drawn in tile pixel coordinates, so what you see is exactly
the image the model was given (1 m/pixel, 4-band NAIP resampled from 0.3 m).
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon as MplPolygon

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
