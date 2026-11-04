"""Tests for geo_anom.task1.final (no imagery, no downloads)."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from geo_anom.task1 import final as FN

UTM = FN.UTM


def g(*geoms):
    return gpd.GeoDataFrame(geometry=list(geoms), crs=UTM)


def test_add_new_keeps_only_new_houses():
    base = g(box(0, 0, 150, 15)).assign(source="detector")
    new = g(box(5, 1, 145, 14),        # same house -> dropped
            box(0, 40, 150, 55),       # new house -> kept
            box(10, 42, 140, 54))      # same as the one just added -> dropped
    out = FN.add_new(base, new, "SAM repair")
    assert list(out.source) == ["detector", "SAM repair"]


def test_add_new_small_overlap_is_a_different_house():
    base = g(box(0, 0, 150, 15))
    out = FN.add_new(base, g(box(0, 12, 150, 27)), "x")          # 3 m of 15 m overlap = 20% < 30%
    assert len(out) == 2


def test_rect_fills_the_roof():
    from shapely.geometry import Polygon
    jagged = Polygon([(0, 0), (150, 0), (150, 15), (100, 15), (100, 8), (50, 8), (50, 15), (0, 15)])
    assert FN.rect(g(jagged)).geometry.iloc[0].area == pytest.approx(150 * 15)


def test_score_found_precision_and_cover():
    traced = g(box(0, 0, 150, 15), box(0, 100, 150, 115))
    layer = g(box(0, 0, 120, 15),                 # covers 80% of the first traced house
              box(0, 300, 150, 315),              # confirmed by eye
              box(0, 600, 150, 615))              # neither
    s = FN.score(layer, traced, box(-1000, -1000, 1000, 1000), confirmed=g(box(1, 301, 149, 314)))
    assert (s["found"], s["on_traced"], s["confirmed"], s["detections"]) == (1, 1, 1, 3)
    assert s["cover"] == pytest.approx(0.8)


def test_capacity_range_is_ordered():
    c = FN.capacity([10_000.0])
    assert c["low"][0] < c["mid"][0] < c["high"][0]
    assert c["mid"][0] == pytest.approx(10_000 * FN.FT2_PER_M2 * 0.93 * 1.10)


def test_validation_table_totals():
    final = gpd.GeoDataFrame({"county": ["A", "A", "B"]}, geometry=[box(0, 0, 150, 15), box(0, 50, 150, 65), box(0, 0, 100, 15)], crs=UTM)
    awtf = pd.DataFrame({"ag_census_2017_birds": [50_000, 20_000], "mde_cafo_2017_birds": [60_000, np.nan]}, index=["A", "B"])
    V = FN.validation_table(final, awtf, pd.Series({"A": 40_000}))
    assert V.loc["Total", "houses"] == 3
    assert V.loc["A", "on_hand_mid"] == pytest.approx(V.loc["A", "capacity_mid"] * 0.80)
    assert np.isnan(V.loc["B", "mde_permitted"])


def test_miss_correction_adds_standing_share_of_missed_footprint(monkeypatch):
    cu = box(0, 0, 10_000, 10_000)
    monkeypatch.setattr(FN.region, "county_boundary", lambda n: g(cu))
    traced = g(box(0, 0, 100, 20), box(0, 100, 100, 120),        # found, 2,000 m2 each
               box(0, 200, 50, 220))                              # missed, 1,000 m2
    mapped = g(box(0, 0, 100, 20), box(0, 100, 100, 120))
    T = FN.miss_correction(mapped, traced, counties=["X"], standing=(3, 4), unconfirmed=0.0)
    r = T.loc["X"]
    assert (r.found, r.missed) == (2, 1)
    assert r.k == pytest.approx(1.0)
    assert r.roof_m2_mid == pytest.approx(4000 + 1000 * 0.75)
    assert r.houses_mid == pytest.approx(2.75)
    assert r.roof_m2_low < r.roof_m2_mid < r.roof_m2_high
    assert T.loc["Eastern Shore", "missed"] == 1
