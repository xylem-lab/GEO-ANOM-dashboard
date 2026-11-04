"""Tests for geo_anom.task2.nutrients (no data files beyond the default sheet)."""

import numpy as np
import pandas as pd
import pytest

from geo_anom.task2 import nutrients as NU


@pytest.fixture
def sheet():
    return NU.load_coefficients()


def test_sheet_loads_and_is_ordered(sheet):
    assert set(NU.REQUIRED) <= set(sheet.index)
    assert (sheet.low <= sheet.mid).all() and (sheet.mid <= sheet.high).all()


def test_bad_sheet_refused(tmp_path, sheet):
    s = sheet.reset_index(); s.loc[0, "low"] = s.loc[0, "high"] + 1
    s.to_csv(tmp_path / "c.csv", index=False)
    with pytest.raises(ValueError):
        NU.load_coefficients(tmp_path / "c.csv")


def test_litter_chain_by_hand(sheet):
    v = NU.values(sheet)
    s = NU.litter(1000.0, v)                                  # one 1,000 m2 house
    birds = 1000 * NU.FT2_PER_M2 * 0.93 * 1.10 * 5.5 * 0.93
    assert s["birds_year"] == pytest.approx(birds)
    assert s["tons"] == pytest.approx(birds * 2.65 / 2000)
    assert s["P2O5_lb"] == pytest.approx(s["tons"] * 20.2 * NU.P_TO_P2O5)


def test_soybeans_need_no_N(sheet):
    d = NU.crop_need({"soybeans": 100.0}, NU.values(sheet))
    assert d["N_need_lb"] == 0 and d["P2O5_need_lb"] == pytest.approx(4000)


def test_no_cropland_means_all_surplus(sheet):
    b = NU.balance([5000.0], {"corn": [0.0]}, NU.values(sheet))
    assert b["capacity_tons"][0] == 0 and b["surplus_tons"][0] == pytest.approx(b["tons"][0])


def test_high_P_share_follows_dllc_fit(sheet):
    v = NU.values(sheet)
    assert NU.high_P_share(10.0, 1.0, v) == pytest.approx((1.632 * 10 + 10.294) / 100)
    assert NU.high_P_share(1e6, 1.0, v) == pytest.approx(0.95)


def test_monte_carlo_shapes_and_mid_inside(sheet):
    roof = np.array([20000.0, 0.0]); acres = {"corn": np.array([500.0, 5000.0])}
    mc = NU.monte_carlo(roof, acres, sheet, n=500)
    assert mc["surplus_tons"].shape == (500, 2)
    s = NU.summarize_draws(mc["surplus_tons"], ["a", "b"])
    assert s.loc["a", "p5"] <= s.loc["a", "p50"] <= s.loc["a", "p95"]
    assert s.loc["b", "p_surplus"] == 0                        # no houses -> never surplus


def test_tornado_lists_varying_coefficients(sheet):
    t = NU.tornado(np.array([20000.0]), {"corn": np.array([500.0])}, sheet)
    assert "litter_lb_per_bird" in set(t.coefficient) and (t.swing.diff().dropna() <= 1e-9).all()


def test_within_matches_add_within():
    import geopandas as gpd
    from geo_anom.task2 import balance as B
    g = pd.DataFrame({"ix": [0, 1, 2, 5], "iy": [0, 0, 0, 5], "v": [1.0, 2.0, 3.0, 4.0]})
    g = gpd.GeoDataFrame(g, geometry=gpd.points_from_xy(g.ix, g.iy))
    ref = B.add_within(g, ["v"], 1000, 1000)["v_1km"].values
    got = NU.within(g.v.values[None], g.ix, g.iy, 1000, 1000)[0]
    assert np.allclose(got, ref)


def test_hay_scenario_adds_need(sheet):
    v = NU.values(sheet)
    a = NU.crop_need({"corn": 100.0}, v)["N_need_lb"]
    b = NU.crop_need({"corn": 100.0, "hay": 50.0}, v)["N_need_lb"]
    assert b - a == pytest.approx(50 * 80)
