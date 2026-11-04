"""Tests for geo_anom.task1.refine (shape logic only; SAM itself is not run here)."""

from shapely import affinity
from shapely.geometry import Polygon, box

from geo_anom.task1 import refine


def test_rectangle_of_ragged_outline_is_its_bounding_rectangle():
    blob = Polygon([(0, 0), (120, 2), (125, 10), (118, 16), (2, 15), (-3, 8)])
    r = refine.rectangle(blob)
    assert r.area >= blob.area
    assert len(r.exterior.coords) == 5


def test_house_shape_accepts_a_poultry_house_and_rejects_a_blob():
    house = affinity.rotate(box(0, 0, 150, 15), 33, origin="centroid")
    ok, reasons = refine.is_house_shape(house)
    assert ok, reasons
    # an L-shaped warehouse corner: right size, but fills little of its rectangle
    ell = box(0, 0, 150, 15).union(box(0, 0, 15, 120))
    ok, reasons = refine.is_house_shape(ell)
    assert not ok and any("fill" in r for r in reasons)


def test_long_axis():
    c, u, L, W = refine.long_axis(affinity.rotate(box(0, 0, 100, 10), 90, origin="centroid"))
    assert abs(L - 100) < 1e-6 and abs(W - 10) < 1e-6
    assert abs(abs(u[1]) - 1) < 1e-6


def test_match_bands_moves_dark_image_to_reference_and_keeps_nodata():
    import numpy as np
    from geo_anom.task1.tiles import match_bands

    rng = np.random.default_rng(0)
    dark = rng.integers(20, 120, size=(60, 60, 4)).astype(np.uint8)
    dark[:5] = 0                                   # no-data strip stays no-data
    ref = rng.integers(60, 200, size=(80, 80, 4)).astype(np.uint8)
    out = match_bands(dark, ref)
    assert (out[:5] == 0).all()
    assert abs(out[5:].mean() - ref.mean()) < 3
    # order is preserved: brighter in, brighter out
    a, b = dark[10, 10, 0], dark[20, 20, 0]
    if a < b:
        assert out[10, 10, 0] <= out[20, 20, 0]
