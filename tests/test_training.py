"""Tests for geo_anom.task1.training (labels, masks, augmentation; no downloads)."""

import geopandas as gpd
import numpy as np
from affine import Affine
from shapely.geometry import box

from geo_anom.task1 import training as T

UTM = T.UTM


def _gdf(geoms):
    return gpd.GeoDataFrame(geometry=geoms, crs=UTM)


def test_label_rules_by_year():
    assert T.value_for("traced", "2017") == T.POSITIVE
    assert T.value_for("traced", "2023") == T.POSITIVE
    assert T.value_for("new_confirmed", "2023") == T.POSITIVE
    assert T.value_for("new_confirmed", "2017") == T.IGNORE
    assert T.value_for("new_unchecked", "2023") == T.IGNORE
    assert T.value_for("rejected", "2021") == T.NEGATIVE


def test_label_layer_sorts_our_houses():
    traced = _gdf([box(0, 0, 150, 15)])
    ours = _gdf([box(2, 1, 148, 14),            # same house as traced -> dropped (traced wins)
                 box(0, 100, 150, 115),         # new, unchecked
                 box(0, 200, 150, 215)])        # new, confirmed in 07
    confirmed = _gdf([box(1, 201, 149, 214)])
    rejected = _gdf([box(0, 400, 80, 440)])
    lab = T.label_layer(traced, ours, confirmed, rejected)
    assert sorted(lab.source) == ["new_confirmed", "new_unchecked", "rejected", "traced"]


def test_mask_values_ring_and_nodata():
    t = Affine(1, 0, 0, 0, -1, 100)                 # 100 x 100 px, 1 m, top-left at (0, 100)
    lab = gpd.GeoDataFrame({"source": ["traced", "new_unchecked"]},
                           geometry=[box(10, 40, 70, 60), box(10, 5, 70, 15)], crs=UTM)
    nod = np.zeros((100, 100), bool); nod[:, 95:] = True
    m = T.rasterize_mask(lab, "2023", t, (100, 100), UTM, border_m=2, nodata=nod)
    assert m[50, 40] == T.POSITIVE                   # inside the traced house (y=50 -> row 50)
    assert m[40, 40] == T.IGNORE                     # on its edge (y=60 -> row 40)
    assert m[90, 40] == T.IGNORE                     # the unchecked detection (y=10 -> row 90)
    assert m[25, 40] == T.NEGATIVE                   # open ground
    assert (m[:, 95:] == T.IGNORE).all()             # no-data


def test_split_is_by_county():
    assert T.split_of("Wicomico") == "test"
    assert T.split_of("Dorchester") == "val"
    assert T.split_of("Somerset") == "train"


def test_augment_shapes_and_keeps_nodata_and_labels():
    rng = np.random.default_rng(0)
    img = rng.integers(1, 255, size=(512, 512, 4)).astype(np.uint8)
    img[:, :100] = 0
    mask = np.zeros((512, 512), np.uint8); mask[200:260, 100:400] = 1; mask[:, :100] = T.IGNORE
    for _ in range(20):
        a, m = T.augment(img, mask, rng)
        assert a.shape == (256, 256, 4) and m.shape == (256, 256)
        assert set(np.unique(m)) <= {0, 1, T.IGNORE}
        nod = ~a.any(axis=2)
        assert (m[nod] == T.IGNORE).all()            # no-data stays no-data and ignored


def test_house_windows_hold_every_house_whole():
    from shapely import affinity
    houses = [affinity.rotate(box(0, i * 25, 150, i * 25 + 15), 30, origin=(0, 0)) for i in range(6)]
    g = _gdf(houses + [box(5000, 0, 5160, 15)])      # one farm of 6 houses + a far-away house
    cs = T.house_windows(g)
    wins = [box(x - 256, y - 256, x + 256, y + 256) for x, y in cs]
    assert len(cs) == 2
    assert all(any(w.contains(h) for w in wins) for h in g.geometry)


def test_focused_crop_contains_a_house():
    rng = np.random.default_rng(3)
    img = np.full((512, 512, 4), 100, np.uint8)
    mask = np.zeros((512, 512), np.uint8); mask[480:500, 20:200] = 1
    hits = sum((T.augment(img, mask, rng, focus=1.0, scale=(1, 1))[1] == 1).any() for _ in range(30))
    assert hits == 30


def test_extra_windows_only_for_houses_outside_the_plan(monkeypatch):
    import pandas as pd
    traced = _gdf([box(0, 0, 150, 15)])
    plan = gpd.GeoDataFrame({"window_id": ["2023_e75_n7"], "cell": ["e75_n7"], "year": ["2023"]},
                            geometry=[box(75 - 256, 7 - 256, 75 + 256, 7 + 256)], crs=UTM)
    conf = _gdf([box(0, 40, 150, 55), box(3000, 0, 3150, 15)])     # one inside the window, one far away
    lab = T.label_layer(traced, None, conf, None)
    md = gpd.GeoDataFrame({"NAME": ["Somerset"], "NAMELSAD": ["Somerset County"]},
                          geometry=[box(-10000, -10000, 10000, 10000)], crs=UTM)
    monkeypatch.setattr(T.region, "md_counties", lambda: md)
    ex = T.extra_windows(plan, lab, years=["2023"])
    assert len(ex) == 1 and ex.kind.iloc[0] == "positive" and ex.split.iloc[0] == "train"
    assert ex.geometry.iloc[0].contains(conf.geometry.iloc[1])
