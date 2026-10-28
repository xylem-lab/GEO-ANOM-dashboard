"""Post-processing of detected houses: cleaner outlines and recovered houses.

Two measured problems with the U-Net output (docs/NEXT_SESSION.md, 2026-10-28):
- outlines are blobs that miss the ends and darker parts of the roof
  (median 78% of the hand-traced roof covered on the Eastern Shore);
- real houses whose mask broke into short pieces, or merged with a
  neighbour, are thrown out by the size filter (278 + 65 traced houses).

`rectangle()` replaces an outline with its minimum rotated rectangle (no
imagery needed). `SamRefiner` uses Meta's Segment Anything (vit_b) on the
same 1 m NAIP image the detector saw: a point inside a rejected piece is
grown to the whole roof, and the result is kept only if it passes the
same house filter as every other detection and is roughly rectangular.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from shapely.geometry import Point
from shapely.geometry import shape as shapely_shape

from geo_anom.task1 import detect
from geo_anom.task1.tiles import ROOT

SAM_CHECKPOINT = ROOT / "data/models/sam_vit_b_01ec64.pth"
MIN_FILL = 0.75        # outline area / its rotated rectangle; poultry houses are rectangles


def rectangle(poly):
    """Minimum rotated rectangle of an outline (the house's footprint as a rectangle)."""
    return poly.minimum_rotated_rectangle


def fill_ratio(poly) -> float:
    rect = poly.minimum_rotated_rectangle
    return poly.area / rect.area if rect.area > 0 else 0.0


def is_house_shape(poly, animal_type: str | None = None) -> tuple[bool, list[str]]:
    """Same size filter as detection, plus 'roughly a rectangle'."""
    reasons = detect.filter_reasons(detect.polygon_stats(poly), animal_type)
    f = fill_ratio(poly)
    if f < MIN_FILL:
        reasons.append(f"fill {f:.2f} < {MIN_FILL}")
    return not reasons, reasons


def long_axis(poly):
    """(centre xy, unit vector along the long side, length, width) of a polygon's rectangle."""
    rect = poly.minimum_rotated_rectangle
    c = np.array(rect.exterior.coords)[:4]
    e1, e2 = c[1] - c[0], c[2] - c[1]
    u, L, W = (e1, np.linalg.norm(e1), np.linalg.norm(e2)) if np.linalg.norm(e1) >= np.linalg.norm(e2) \
        else (e2, np.linalg.norm(e2), np.linalg.norm(e1))
    return np.array(rect.centroid.coords[0]), u / max(L, 1e-9), L, W


class SamRefiner:
    """Segment Anything on an RGB image in a metre-based CRS (pixel <-> map via `transform`)."""

    def __init__(self, checkpoint: Path = SAM_CHECKPOINT, device: str | None = None):
        import torch
        from segment_anything import SamPredictor, sam_model_registry

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.predictor = SamPredictor(sam_model_registry["vit_b"](checkpoint=str(checkpoint)).to(device))
        self._key = None

    def set_image(self, rgb: np.ndarray, transform, key=None):
        if key is None or key != self._key:
            self.predictor.set_image(np.ascontiguousarray(rgb[..., :3]))
            self._key = key
        self.transform = transform
        self.shape = rgb.shape[:2]

    def _to_px(self, xy):
        return np.array([~self.transform * tuple(p) for p in np.atleast_2d(xy)])

    def _polygons(self, mask, seed_px):
        """The connected piece of `mask` under the seed pixel, as a map polygon."""
        import cv2
        from rasterio.features import shapes

        n, lab = cv2.connectedComponents(mask.astype(np.uint8))
        x, y = int(round(seed_px[0])), int(round(seed_px[1]))
        if n <= 1 or not (0 <= y < lab.shape[0] and 0 <= x < lab.shape[1]) or lab[y, x] == 0:
            return None
        part = lab == lab[y, x]
        polys = [shapely_shape(g) for g, v in shapes(part.astype(np.uint8), mask=part, transform=self.transform) if v == 1]
        return max(polys, key=lambda p: p.area).buffer(0) if polys else None

    def grow(self, seed_xy, box=None, extra_points=None):
        """Masks SAM proposes for the object under `seed_xy` (map coords), best score first.
        Returns a list of (polygon, score)."""
        pts = self._to_px([seed_xy] + list(extra_points or []))
        kw = dict(point_coords=pts, point_labels=np.ones(len(pts)), multimask_output=True)
        if box is not None:
            b = self._to_px([(box[0], box[3]), (box[2], box[1])])
            kw["box"] = np.array([b[:, 0].min(), b[:, 1].min(), b[:, 0].max(), b[:, 1].max()])
        masks, scores, _ = self.predictor.predict(**kw)
        out = []
        for m, s in sorted(zip(masks, scores), key=lambda t: -t[1]):
            p = self._polygons(m, pts[0])
            if p is not None and not p.is_empty:
                out.append((p, float(s)))
        return out

    def best_house(self, seed_xy, animal_type=None, **kw):
        """Highest-scoring SAM mask under the seed that passes the house filter, or None."""
        for p, s in self.grow(seed_xy, **kw):
            ok, _ = is_house_shape(p, animal_type)
            if ok:
                return p, s
        return None

    def recover_fragment(self, frag_poly, animal_type=None):
        """A short rejected piece -> the whole roof it belongs to (or None)."""
        c, u, L, W = long_axis(frag_poly)
        return self.best_house(tuple(c), animal_type)

    def split_merged(self, blob_poly, animal_type=None, step_m: float = 12.0):
        """A blob covering several side-by-side houses -> the individual houses."""
        c, u, L, W = long_axis(blob_poly)
        v = np.array([-u[1], u[0]])
        found = []
        for off in np.arange(-W / 2 + step_m / 2, W / 2, step_m):
            seed = c + v * off
            if not blob_poly.contains(Point(seed)):
                continue
            got = self.best_house(tuple(seed), animal_type,
                                  extra_points=[tuple(seed + u * L * 0.25), tuple(seed - u * L * 0.25)])
            if got and all(got[0].intersection(f[0]).area < 0.3 * got[0].area for f in found):
                found.append(got)
        return found
