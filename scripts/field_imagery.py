#!/usr/bin/env python3
"""
Satellite crops with detection overlays, for the field labeling guide and the
field KMZ balloons.

Each overlay polygon must be drawn on the imagery source it was registered
against: building detections use the Planetary Computer 4-band NAIP tiles
(data/raw/naip_tiles_pc_4band_full, ~1 m/px, UTM 18N); the 7 hand-labeled
lagoons in full_registry_sam_lagoon_detections.geojson were registered on the
older MD iMAP RGB tiles (data/raw/naip_tiles_full, lon/lat), which are offset
from Planetary Computer by ~70-100 m in places (docs/NEXT_SESSION.md).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer
from rasterio.transform import rowcol
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parent.parent
PC_MANIFEST = ROOT / "data/raw/naip_tiles_pc_4band_full/manifest.json"
IMAP_MANIFEST = ROOT / "data/raw/naip_tiles_full/manifest.json"

PANEL_PX = 760
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

COLORS = {
    "detected": (60, 255, 90),      # building kept by the filter
    "rejected": (255, 150, 0),      # raw model candidate the filter dropped
    "lagoon_confirmed": (30, 144, 255),
    "lagoon_corroborated": (120, 220, 255),
    "lagoon_uncertain": (255, 225, 0),
    "lagoon_false": (255, 60, 60),
    "lagoon_candidate": (200, 150, 255),
    "false_building": (255, 60, 60),
    "point": (255, 255, 255),
}


def _font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def load_manifest(source: str) -> dict:
    path = PC_MANIFEST if source == "pc" else IMAP_MANIFEST
    return {f["farm_name"]: f for f in json.loads(path.read_text())}


def _abs(p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else ROOT / q


class TileView:
    """A tile plus lon/lat <-> panel-pixel mapping for one square crop.

    Uses each file's own embedded georeference. (Tested 2026-09-23: rebuilding
    the MD iMAP transform from the manifest bbox instead displaced a confirmed
    lagoon by ~90 m, so the file georeference is the one the detections used.)
    """

    def __init__(self, tile_path: str, center_lonlat: tuple[float, float], half_m: float):
        self.src = rasterio.open(_abs(tile_path))
        self.crs = self.src.crs
        self.transform = self.src.transform
        self.geographic = self.crs.to_epsg() == 4326
        self.to_tile = None if self.geographic else Transformer.from_crs("EPSG:4326", self.crs, always_xy=True)
        self.from_tile = None if self.geographic else Transformer.from_crs(self.crs, "EPSG:4326", always_xy=True)
        lon, lat = center_lonlat
        cx, cy = self.to_tile.transform(lon, lat) if self.to_tile else (lon, lat)
        row, col = rowcol(self.transform, cx, cy, op=float)
        if self.geographic:
            hx = half_m / (111320.0 * math.cos(math.radians(lat))) / abs(self.transform.a)
            hy = half_m / 111320.0 / abs(self.transform.e)
        else:
            hx = half_m / abs(self.transform.a)
            hy = half_m / abs(self.transform.e)
        self.col0, self.row0 = col - hx, row - hy
        self.win_w, self.win_h = 2 * hx, 2 * hy
        self.half_m = half_m
        self.m_per_px = 2 * half_m / PANEL_PX

    def image(self) -> Image.Image:
        win = Window(round(self.col0), round(self.row0), round(self.win_w), round(self.win_h))
        arr = self.src.read([1, 2, 3], window=win, boundless=True, fill_value=0)
        img = Image.fromarray(np.transpose(arr, (1, 2, 0)).astype("uint8"), "RGB")
        return img.resize((PANEL_PX, PANEL_PX), Image.LANCZOS)

    def px(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = self.to_tile.transform(lon, lat) if self.to_tile else (lon, lat)
        col, row = ~self.transform * (x, y)
        return ((col - self.col0) / self.win_w * PANEL_PX, (row - self.row0) / self.win_h * PANEL_PX)

    def lonlat(self, px: float, py: float) -> tuple[float, float]:
        """Inverse of px(): panel pixel -> (lon, lat)."""
        col = self.col0 + px / PANEL_PX * self.win_w
        row = self.row0 + py / PANEL_PX * self.win_h
        x, y = self.transform * (col, row)
        return self.from_tile.transform(x, y) if self.from_tile else (x, y)

    def px_tile_xy(self, x: float, y: float) -> tuple[float, float]:
        col, row = ~self.transform * (x, y)
        return ((col - self.col0) / self.win_w * PANEL_PX, (row - self.row0) / self.win_h * PANEL_PX)


def _rings(geom: dict):
    if geom["type"] == "Polygon":
        yield geom["coordinates"][0]
    elif geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            yield poly[0]


def _visible(pts) -> bool:
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return max(xs) > 0 and min(xs) < PANEL_PX and max(ys) > 0 and min(ys) < PANEL_PX


def draw_lonlat_polygon(draw, view: TileView, geom: dict, color, width=3, label=None):
    for ring in _rings(geom):
        pts = [view.px(lon, lat) for lon, lat in ring]
        if not _visible(pts):
            continue
        draw.line(pts + [pts[0]], fill=color, width=width, joint="curve")
        if label:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            _tag(draw, (min(xs), min(ys) - 20), label, color)


def draw_native_polygon(draw, view: TileView, poly, color, width=2, label=None):
    """poly: shapely polygon already in the tile's own CRS (raw model output)."""
    pts = [view.px_tile_xy(x, y) for x, y in poly.exterior.coords]
    if not _visible(pts):
        return
    draw.line(pts, fill=color, width=width, joint="curve")
    if label:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        _tag(draw, (min(xs), min(ys) - 20), label, color)


def _tag(draw, xy, text, color):
    f = _font(15)
    x, y = xy
    x = max(4, min(x, PANEL_PX - 150))
    y = max(4, y)
    w = draw.textlength(text, font=f)
    draw.rectangle([x - 2, y - 1, x + w + 3, y + 17], fill=(0, 0, 0))
    draw.text((x, y), text, font=f, fill=color)


def draw_point(draw, view: TileView, lon: float, lat: float):
    x, y = view.px(lon, lat)
    for r, col, wd in ((11, (0, 0, 0), 5), (11, COLORS["point"], 2)):
        draw.ellipse([x - r, y - r, x + r, y + r], outline=col, width=wd)
    draw.line([x - 16, y, x - 5, y], fill=COLORS["point"], width=2)
    draw.line([x + 5, y, x + 16, y], fill=COLORS["point"], width=2)
    draw.line([x, y - 16, x, y - 5], fill=COLORS["point"], width=2)
    draw.line([x, y + 5, x, y + 16], fill=COLORS["point"], width=2)


def draw_marker(draw, view: TileView, lon: float, lat: float, label: str, color=(255, 255, 255)):
    """Ring + label, for analyst-annotated locations (not model output)."""
    x, y = view.px(lon, lat)
    draw.ellipse([x - 13, y - 13, x + 13, y + 13], outline=(0, 0, 0), width=6)
    draw.ellipse([x - 13, y - 13, x + 13, y + 13], outline=color, width=3)
    _tag(draw, (x + 16, y - 9), label, color)


def draw_scale_bar(draw, view: TileView):
    for bar_m in (100, 50, 25):
        if bar_m / view.m_per_px < PANEL_PX * 0.4:
            break
    length = bar_m / view.m_per_px
    x0, y0 = 16, PANEL_PX - 22
    draw.rectangle([x0 - 8, y0 - 24, x0 + length + 12, y0 + 12], fill=(0, 0, 0))
    draw.line([x0, y0, x0 + length, y0], fill=(255, 255, 255), width=4)
    draw.line([x0, y0 - 6, x0, y0 + 6], fill=(255, 255, 255), width=3)
    draw.line([x0 + length, y0 - 6, x0 + length, y0 + 6], fill=(255, 255, 255), width=3)
    draw.text((x0, y0 - 22), f"{bar_m} m", font=_font(14), fill=(255, 255, 255))


def side_by_side(clean: Image.Image, overlay: Image.Image) -> Image.Image:
    out = Image.new("RGB", (clean.width * 2 + 12, clean.height), (255, 255, 255))
    out.paste(clean, (0, 0))
    out.paste(overlay, (clean.width + 12, 0))
    return out


def render(tile_path: str, center_lonlat, half_m: float, draw_fn, two_panel=True) -> Image.Image:
    """draw_fn(draw, view) paints the overlays. Returns clean|overlay or overlay only."""
    view = TileView(tile_path, center_lonlat, half_m)
    clean = view.image()
    overlay = clean.copy()
    d = ImageDraw.Draw(overlay)
    draw_fn(d, view)
    draw_scale_bar(d, view)
    return side_by_side(clean, overlay) if two_panel else overlay
