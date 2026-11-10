"""Tests for geo_anom.task1.accuracy (synthetic frames; no imagery, no drive)."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from geo_anom.task1 import accuracy as A

UTM = A.UTM
X0, Y0 = 400_000.0, 4_200_000.0          # a spot in UTM 18N


def house(x, y, length=150, width=15):
    return box(X0 + x, Y0 + y, X0 + x + length, Y0 + y + width)


def world():
    """Two 'counties' 5 km x 5 km side by side; houses in the first; one west outline elsewhere."""
    b = {"Somerset": box(X0, Y0, X0 + 5000, Y0 + 5000), "Wicomico": box(X0 + 5000, Y0, X0 + 10000, Y0 + 5000)}
    traced = gpd.GeoDataFrame(geometry=[house(1000, 1000), house(1000, 1100), house(1000, 1200),   # 3 found
                                        house(3000, 3000),                                       # missed
                                        house(6000, 1000), house(6000, 1100)], crs=UTM)           # Wicomico
    rel = gpd.GeoDataFrame({"house_id": ["h1", "h2", "h3", "h4", "h5", "h6", "w1"],
                            "county": ["Somerset"] * 4 + ["Wicomico", "Wicomico", "Frederick"]},
                           geometry=[house(1000, 1000), house(1000, 1100), house(1000, 1200),
                                     house(1500, 1500),                       # inside extent, not traced -> S2
                                     house(6000, 1000), house(6000, 1100),
                                     house(-50000, 0)], crs=UTM)               # west -> S3
    return rel, traced, b


def test_frames_strata_and_k():
    rel, traced, b = world()
    obj, cells, k = A.frames(rel, traced, counties=list(b), boundaries=b)
    s = obj.set_index("key")["stratum"].to_dict()
    assert s["map:h1"] == s["map:h5"] == "S1"
    assert s["map:h4"] == "S2"
    assert s["map:w1"] == "S3"
    assert s["usgs:3"] == "S4" and (obj.stratum == "S4").sum() == 1
    assert k["Somerset"] == pytest.approx(1.0)
    assert len(cells) == 50 and cells.key.is_unique
    # cell holding the houses at (1000..1150, 1000..1215) -> A; its neighbours -> B; far corner -> C
    st = cells.set_index("key")["stratum"]
    kx, ky = int((X0 + 1000) // 1000), int((Y0 + 1000) // 1000)
    assert st[f"cell:{kx}_{ky}"] == "S6A"
    assert st[f"cell:{kx + 1}_{ky + 1}"] in ("S6A", "S6B")
    assert st[f"cell:{int(X0 // 1000) + 9}_{int(Y0 // 1000) + 4}"] == "S6C"


def test_allocate():
    c = pd.Series({"a": 1000, "b": 300, "c": 3, "d": 60})
    a = A.allocate(c, 100)
    assert a.sum() == 100 and a["c"] == 3 and a["d"] >= 5
    assert (A.allocate(c, None) == c).all()
    assert (A.allocate(pd.Series({"a": 4}), 10) == 4).all()


def fake_frame(n1=400, n2=200, n4=300, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for h, n in (("S1", n1), ("S2", n2), ("S3", 20), ("S4", n4)):
        for i in range(n):
            rows.append({"key": f"{h}:{i}", "stratum": h, "county": ["Somerset", "Wicomico"][i % 2],
                         "area_m2": 2500.0, "geometry": house(i * 200 % 4000, i * 30 % 4000)})
    obj = gpd.GeoDataFrame(rows, crs=UTM)
    cells = gpd.GeoDataFrame([{"key": f"cell:{i}", "stratum": ["S6A", "S6B", "S6C"][i % 3],
                               "county": "Somerset", "area_m2": 1e6, "geometry": box(0, 0, 1, 1)}
                              for i in range(600)], crs=UTM)
    return obj, cells


def test_draw_roles_and_determinism():
    obj, cells = fake_frame()
    f = A.draw(obj, cells, seed=7)
    g = A.draw(obj, cells, seed=7)
    assert (f.role == g.role).all() and (f.pilot == g.pilot).all()
    n = f[f.role == "sample"].groupby("stratum").size()
    assert n["S1"] == 100 and n["S2"] == 150 and n["S3"] == 20 and n["S4"] == 150
    assert n["S6A"] == 150 and n["S6B"] == 150 and n["S6C"] == 100
    cal = f[f.role == "calibration"]
    assert len(cal) == 30 and set(cal.stratum) == {"S1", "S2", "S4"}
    assert f[f.pilot].role.eq("sample").all()
    assert f[f.pilot].groupby("stratum").size().to_dict() == {"S1": 25, "S2": 25, "S4": 25}
    # within each stratum x county the ranks are a permutation, the sample is the first ranks
    for (h, c), q in f[f.kind == "object"].groupby(["stratum", "county"]):
        assert sorted(q["rank"]) == list(range(len(q)))
        s = q[q.role == "sample"]["rank"]
        assert sorted(s) == list(range(len(s)))


def test_replace_pilot_keeps_allocation():
    obj, cells = fake_frame()
    f = A.draw(obj, cells, seed=1)
    g = A.replace_pilot(f)
    assert (g.role == "discarded pilot").sum() == 75
    assert g.pilot.sum() == 75
    before = f[f.role == "sample"].groupby(["stratum", "county"]).size()
    after = g[g.role == "sample"].groupby(["stratum", "county"]).size()
    assert before.equals(after)
    assert not set(g[g.pilot].key) & set(f[f.pilot].key)


def test_queue_order_differs_by_reviewer():
    obj, cells = fake_frame()
    f = A.draw(obj, cells, seed=1)
    a, b = A.queue(f, "UA", "main"), A.queue(f, "JH", "main")
    assert set(a.key) == set(b.key) and list(a.key) != list(b.key)
    assert not set(a.key) & set(A.queue(f, "UA", "pilot").key)
    assert len(A.queue(f, "UA", "cells")) == 400


def test_estimate_census_is_exact():
    """Everything labelled (census) -> estimate = truth and the bootstrap has no spread."""
    obj, cells = fake_frame(n1=40, n2=20, n4=30)
    sizes = {h: None for h in A.SIZES}
    f = A.draw(obj, cells, sizes=sizes, seed=3, pilot={}, calibration={})
    vals = {}
    for k_, h in zip(f.key, f.stratum):
        i = int(k_.split(":")[1])
        if h == "S1":
            vals[k_] = "house"
        elif h == "S2":
            vals[k_] = "house" if i < 15 else "not a house"       # 15 / 20
        elif h == "S3":
            vals[k_] = "house" if i < 5 else "not a house"        # 5 / 20 (all in ES counties here)
        elif h == "S4":
            vals[k_] = "house" if i < 24 else "gone"              # 24 / 30
        else:
            vals[k_] = "1" if (h == "S6A" and i < 30) else "0"    # 10 cells of S6A with one house each
    est = A.estimate(f, pd.Series(vals), k={"Somerset": 1.0, "Wicomico": 1.0}, B=50)
    e = est["estimate"]
    assert e["correct map houses (ES)"] == pytest.approx(40 + 15 + 5)
    assert e["precision (Eastern Shore)"] == pytest.approx(60 / 80)
    assert e["missed traced houses standing"] == pytest.approx(24)
    assert e["houses on a list (ES)"] == pytest.approx(84)              # v1.2: cells are residual, not listed
    assert e["residual: cell expansion (ES)"] == pytest.approx(10)
    assert e["recall (ES)"] == pytest.approx(60 / 84)
    assert e["roof km2 (ES)"] == pytest.approx((60 + 24) * 2500 / 1e6)
    assert (est["high"] - est["low"]).abs().max() < 1e-9
    assert (est["widened by"] == "").all()                              # census strata are never widened


def test_estimate_weights_by_county():
    """Unequal sampling rates across counties are weighted back by N/n."""
    rows = [{"key": f"S1:{i}", "stratum": "S1", "county": "Somerset" if i < 100 else "Wicomico",
             "area_m2": 1.0, "geometry": box(0, 0, 1, 1)} for i in range(200)]
    obj = gpd.GeoDataFrame(rows, crs=UTM)
    f = obj.assign(kind="object", role="reserve", pilot=False, rank=0)
    f.loc[list(range(0, 10)) + list(range(100, 150)), "role"] = "sample"     # 10 of 100 vs 50 of 100
    lab = pd.Series({k: ("house" if k.startswith("S1:") and int(k[3:]) < 100 else "not a house") for k in f.key})
    est = A.estimate(f, lab, k={}, B=20)
    assert est.loc["precision (Eastern Shore)", "estimate"] == pytest.approx(0.5)


def test_final_labels_and_adjudication(tmp_path):
    a, b = A.Store(tmp_path, "UA"), A.Store(tmp_path, "JH")
    a.add("k1", "house", "main"); b.add("k1", "house", "main")
    a.add("k2", "house", "main"); b.add("k2", "gone", "main")
    a.add("k3", A.CANT_TELL, "main"); b.add("k3", "house", "main")
    a.add("k5", "house", "main", check_later=True); b.add("k5", "house", "main")
    a.add("k4", "house", "main"); b.add("k4", "not a house", "main")
    L = A.load_labels(tmp_path)
    q = A.adjudication_queue(L, ["UA", "JH"])
    assert set(q.key) == {"k2", "k3", "k4", "k5"}           # k5: agreed but flagged check later
    assert bool(q.set_index("key").loc["k5", "check later"])
    adj = tmp_path / "adjudicated.csv"
    A.adjudicate(adj, "k2", "gone", "roof missing on 2023 photo", "UA+JH")
    with pytest.raises(ValueError):
        A.adjudicate(adj, "k3", "house", "", "UA")
    A.adjudicate(adj, "kept1", "house", "round-1 pilot item kept in the sample", "UA+JH")
    fin = A.final_labels(L, ["UA", "JH"], pd.read_csv(adj))
    assert fin.to_dict() == {"k1": "house", "k2": "gone", "k3": A.CANT_TELL, "k4": A.CANT_TELL, "k5": "house",
                             "kept1": "house"}


def test_store_latest_wins_and_rejects_unknown(tmp_path):
    s = A.Store(tmp_path, "UA")
    s.add("k", "gone", "pilot"); s.add("k", "house", "pilot")
    assert s.latest().set_index("key").value["k"] == "house"
    with pytest.raises(ValueError):
        s.add("k", "maybe", "pilot")
    with pytest.raises(ValueError):
        A.Store(tmp_path, " ")


def test_kappa_and_agreement():
    assert A.cohen_kappa("aabb", "aabb") == pytest.approx(1)
    assert A.cohen_kappa("aabb", "abab") == pytest.approx(0)
    L = pd.DataFrame({"key": ["x", "y", "x", "y"], "reviewer": ["a", "a", "b", "b"],
                      "value": ["house", "gone", "house", "gone"], "phase": "main", "note": ""})
    fr = pd.DataFrame({"key": ["x", "y"], "stratum": ["S2", "S4"]})
    t = A.agreement(L, fr, ["a", "b"], B=20).set_index("items")
    assert t.loc["all objects", "kappa (house / not)"] == pytest.approx(1)


def test_render_object_without_network():
    from rasterio.transform import from_origin
    img = (np.random.default_rng(0).random((500, 500, 3)) * 255).astype(np.uint8)
    png = A.render_object((img, from_origin(X0, Y0, 1, 1), "EPSG:32618", "2023-06-02"))
    assert png[:4] == b"\x89PNG"
    assert A.render_object(None)[:4] == b"\x89PNG"


def test_final_labels_cells_take_larger_count(tmp_path):
    a, b = A.Store(tmp_path, "UA"), A.Store(tmp_path, "JH")
    a.add("cell:1_1", "0", "cells"); b.add("cell:1_1", "2", "cells")
    a.add("cell:1_2", "1", "cells"); b.add("cell:1_2", "1", "cells")
    fin = A.final_labels(A.load_labels(tmp_path), ["UA", "JH"])
    assert fin.to_dict() == {"cell:1_1": "2", "cell:1_2": "1"}


# ── v1.2 ─────────────────────────────────────────────────────────────────────

def test_frames_west():
    rel, _, _ = world()
    bw = {"Frederick": box(X0 - 60000, Y0 - 5000, X0 - 50000, Y0 + 5000)}
    det = gpd.GeoDataFrame({"candidate_id": ["f/1", "f/2"], "county": "Frederick"},
                           geometry=[house(-50000, 0), house(-58000, 3000)], crs=UTM)   # f/1 = on release w1
    permits = gpd.GeoDataFrame({"county": ["Frederick"], "animal_type": ["turkeys"]},
                               geometry=gpd.points_from_xy([X0 - 55500], [Y0 - 4500]), crs=UTM)
    s7, cells, far = A.frames_west(rel, det, permits, boundaries=bw)
    assert list(s7.key) == ["w05:f/2"] and s7.area_m2.iloc[0] == pytest.approx(150 * 15)
    st = cells.stratum.value_counts()
    assert st["S8"] >= 4 and st["S6WA"] >= 1 and st["S6WB"] >= 1
    assert st.sum() + far == 100
    assert not set(cells.stratum) - {"S8", "S6WA", "S6WB"}


def test_shape_filter():
    g = gpd.GeoDataFrame(geometry=[house(0, 0, 150, 15), house(0, 100, 50, 10), house(0, 200, 80, 40)], crs=UTM)
    f = A.shape_filter(g)
    assert len(f) == 1 and f.length_m.iloc[0] == pytest.approx(150)


def test_frames_footprints_and_kf():
    rel, traced, b = world()
    fp = gpd.GeoDataFrame({"fid": [0, 1, 2], "density": [5, 5, 5]}, geometry=[
        house(1000, 1000, 150, 16),              # on h1 (release and traced): not a candidate, used for k_f
        house(4000, 4000, 160, 15),              # new long building in Somerset: S5ES
        house(8000, 4000, 160, 15)], crs=UTM)    # Wicomico (also Eastern Shore)
    s5, k_f = A.frames_footprints(fp, rel, traced, gpd.GeoDataFrame(geometry=[], crs=UTM), boundaries=b)
    assert sorted(s5.key) == ["msfp:1", "msfp:2"] and set(s5.stratum) == {"S5ES"}
    assert k_f == pytest.approx((150 * 15) / (150 * 16))


def test_draw_addendum_refuses_labelled_and_has_no_pilot():
    s7 = gpd.GeoDataFrame({"key": [f"w05:{i}" for i in range(30)], "stratum": "S7", "county": "Frederick",
                           "area_m2": 1.0}, geometry=[box(0, 0, 1, 1)] * 30, crs=UTM)
    cells = gpd.GeoDataFrame({"key": [f"cell:{i}" for i in range(300)], "stratum": ["S8"] * 20 + ["S6WA"] * 180 + ["S6WB"] * 100,
                              "county": "Frederick", "area_m2": 1e6}, geometry=[box(0, 0, 1, 1)] * 300, crs=UTM)
    f = A.draw_addendum(s7, cells)
    n = f[f.role == "sample"].groupby("stratum").size().to_dict()
    assert n == {"S7": 30, "S8": 20, "S6WA": 40, "S6WB": 60}
    assert not f.pilot.any() and not (f.role == "calibration").any()
    with pytest.raises(RuntimeError):
        A.draw_addendum(s7, cells, labelled_keys={"w05:3"})
    q = A.queue(f, "UA", "addendum objects")
    assert len(q) == 30 and len(A.queue(f, "UA", "addendum cells")) == 120
    assert len(A.queue(f, "UA", "main")) == 0


def _sampled_frame(n_s1=100, N_s1=2450):
    rows = [{"key": f"S1:{i}", "stratum": "S1", "county": "Somerset", "area_m2": 2500.0, "kind": "object",
             "role": "sample" if i < n_s1 else "reserve", "pilot": False, "rank": i} for i in range(N_s1)]
    rows += [{"key": f"S6A:{i}", "stratum": "S6A", "county": "Somerset", "area_m2": 1e6, "kind": "cell",
              "role": "sample" if i < 150 else "not drawn", "pilot": False, "rank": i} for i in range(1000)]
    return pd.DataFrame(rows)


def test_constant_strata_get_exact_bounds():
    """All 100 sampled S1 outlines correct: the bootstrap alone has zero width; the exact one-sided
    bound (0.05^(1/100) = 0.9705) must set the lower end. Zero-hit cells: upper end of the residual."""
    f = _sampled_frame()
    lab = pd.Series({k: ("house" if k.startswith("S1") else "0") for k in f.key[f.role == "sample"]})
    est = A.estimate(f, lab, k={}, B=50)
    p = est.loc["precision (Eastern Shore)"]
    assert p.estimate == pytest.approx(1.0)
    assert p.low == pytest.approx(0.05 ** (1 / 100), abs=1e-9) and "S1" in p["widened by"]
    r = est.loc["residual: cell expansion (ES)"]
    assert r.estimate == 0 and r.high == pytest.approx(1000 * (1 - 0.05 ** (1 / 150)) * 3.0)
    t = A.residual_table(f, lab, est)
    assert t.loc["zero-hit bound S6A", "high"] == pytest.approx(1000 * (1 - 0.05 ** (1 / 150)) * 3.0)


def test_other_form_counts(tmp_path):
    a, b = A.Store(tmp_path, "UA"), A.Store(tmp_path, "Monica")
    a.add("k1", "not a house", "main", note="poultry, other form; wide layer house"); b.add("k1", "not a house", "main")
    a.add("k2", "not a house", "main"); b.add("k2", "not a house", "main")
    L = A.load_labels(tmp_path)
    fin = A.final_labels(L, ["UA", "Monica"])
    fr = pd.DataFrame({"key": ["k1", "k2"], "stratum": ["S7", "S7"]})
    assert A.other_form_counts(L, fin, fr).to_dict() == {"S7": 1}


def test_allocate_many_counties_small_n():
    """S6W-A in the real frame: 14 counties, n 40 -> the minimum drops to 2, nothing negative, sums to n."""
    c = pd.Series({"Allegany": 1, "Anne Arundel": 25, "Baltimore County": 38, "Baltimore city": 15, "Carroll": 8,
                   "Charles": 16, "Frederick": 56, "Garrett": 4, "Harford": 5, "Howard": 5, "Montgomery": 26,
                   "Prince George's": 25, "St. Mary's": 1, "Washington": 10})
    a = A.allocate(c, 40)
    assert a.sum() == 40 and (a >= 1).all() and (a <= c).all()
    assert (a[c >= 2] >= 2).all()


def test_west_footprints_split_by_density():
    bw = {"Frederick": box(X0 - 60000, Y0 - 5000, X0 - 50000, Y0 + 5000)}
    rel = gpd.GeoDataFrame({"house_id": [], "county": []}, geometry=[], crs=UTM)
    fp = gpd.GeoDataFrame({"fid": [0, 1], "density": [12, 450]},
                          geometry=[house(-58000, 0), house(-55000, 2000)], crs=UTM)
    s5, _ = A.frames_footprints(fp, rel, gpd.GeoDataFrame(geometry=[], crs=UTM),
                                gpd.GeoDataFrame(geometry=[], crs=UTM), boundaries=bw)
    assert s5.set_index("key").stratum.to_dict() == {"msfp:0": "S5WR", "msfp:1": "S5WD"}


def test_footprint_density_counts_same_cell():
    allg = gpd.GeoSeries([house(10, 10), house(300, 300), house(1500, 10)], crs=UTM)
    d = A.footprint_density(allg, gpd.GeoSeries([house(500, 500)], crs=UTM))
    assert list(d) == [2]


def test_developed_footprints_are_an_assumption_not_widened():
    rows = [{"key": f"msfp:{i}", "stratum": "S5WD", "county": "Montgomery", "area_m2": 1000.0, "kind": "object",
             "role": "sample" if i < 30 else "reserve", "pilot": False, "rank": i} for i in range(7000)]
    rows += [{"key": f"map:{i}", "stratum": "S1", "county": "Somerset", "area_m2": 2500.0, "kind": "object",
              "role": "sample", "pilot": False, "rank": i} for i in range(50)]
    f = pd.DataFrame(rows)
    lab = pd.Series({k: ("house" if k.startswith("map:") else "not a house") for k in f.key[f.role == "sample"]})
    est = A.estimate(f, lab, k={}, B=20)
    assert est.loc["houses on a list (Maryland)", "high"] == pytest.approx(50)        # not widened by S5WD
    assert est.loc["assumption check: S5WD exact 95% upper bound (houses)", "high"] == \
        pytest.approx(7000 * (1 - 0.05 ** (1 / 30)))


# ── amendment A1 (D1): published-model outlines ───────────────────────────────

def test_frames_es_step0_and_links():
    rel, _, _ = world()
    step0 = gpd.GeoDataFrame({"candidate_id": ["a", "b", "c", "d"], "county": "Somerset"}, geometry=[
        house(1000, 1000, 70, 15), house(1080, 1000, 70, 15),     # two pieces of h1 -> both link to h1
        house(1000, 1100),                                         # = h2
        house(2500, 2500)], crs=UTM)                               # on nothing -> S9
    s9 = A.frames_es_step0(rel, step0)
    assert list(s9.key) == ["e05:d"]
    links = A.step0_links(rel, step0)
    assert links.to_dict() == {"map:h1": 2, "map:h2": 1}


def test_published_model_precision_census():
    """Census of everything: the published model's precision = correct published outlines / all of them;
    its recall = map houses it also has / houses on a list."""
    rows = [{"key": f"map:{i}", "stratum": "S1", "county": "Somerset", "area_m2": 1.0, "n_pub": [2, 1, 0, 1][i % 4]}
            for i in range(40)]
    rows += [{"key": f"e05:{i}", "stratum": "S9", "county": "Somerset", "area_m2": 1.0, "n_pub": 1} for i in range(10)]
    f = pd.DataFrame(rows).assign(kind="object", role="sample", pilot=False, rank=0)
    lab = pd.Series({k: ("house" if k.startswith("map:") else ("house" if k in ("e05:0", "e05:1") else "not a house"))
                     for k in f.key})
    n_pub = int(f[f.stratum == "S1"].n_pub.sum()) + 10                 # 40 + 10 = 50 published outlines
    est = A.estimate(f, lab, k={}, B=20, published_es=n_pub)
    e = est["estimate"]
    assert e["precision (published model, ES)"] == pytest.approx((40 + 2) / 50)
    assert e["recall (published model, ES)"] == pytest.approx(30 / 40)   # 10 map houses have no published outline
    assert e["recall gain, map v1 - published (ES)"] == pytest.approx(1 - 30 / 40)
    assert (est["high"] - est["low"]).abs().max() < 1e-9


def test_draw_amendment_a1():
    s9 = gpd.GeoDataFrame({"key": [f"e05:{i}" for i in range(30)], "stratum": "S9", "county": "Cecil",
                           "area_m2": 1.0}, geometry=[box(0, 0, 1, 1)] * 30, crs=UTM)
    f = A.draw_amendment_a1(s9)
    assert (f.role == "sample").sum() == 30 and not f.pilot.any()
    assert len(A.queue(f, "UA", "addendum objects")) == 30
    with pytest.raises(RuntimeError):
        A.draw_amendment_a1(s9, labelled_keys={"e05:4"})


def test_cell_agreement_covers_addendum_cells_and_empty(tmp_path):
    a, b = A.Store(tmp_path, "UA"), A.Store(tmp_path, "Monica")
    a.add("cell:1_1", "0", "cells"); b.add("cell:1_1", "0", "cells")
    a.add("cell:9_9", "2", "addendum cells"); b.add("cell:9_9", "1", "addendum cells")
    r = A.cell_agreement(A.load_labels(tmp_path), ["UA", "Monica"])
    assert r["cells"] == 2 and r["same count"] == pytest.approx(0.5)
    a.add("map:1", "house", "main")
    assert A.cell_agreement(A.load_labels(tmp_path).query("key == 'map:1'"), ["UA", "Monica"]) == {}


def test_assumption_rows_then_constant_stratum():
    """S5WD (assumption rows) sorts before S6A; the zero-hit S6A bound must still widen the residual."""
    rows = [{"key": f"msfp:{i}", "stratum": "S5WD", "county": "Montgomery", "area_m2": 1000.0, "kind": "object",
             "role": "sample" if i < 30 else "reserve", "pilot": False, "rank": i} for i in range(500)]
    rows += [{"key": f"cell:{i}", "stratum": "S6A", "county": "Somerset", "area_m2": 1e6, "kind": "cell",
              "role": "sample" if i < 50 else "not drawn", "pilot": False, "rank": i} for i in range(400)]
    rows += [{"key": f"map:{i}", "stratum": "S1", "county": "Somerset", "area_m2": 2500.0, "kind": "object",
              "role": "sample", "pilot": False, "rank": i} for i in range(20)]
    f = pd.DataFrame(rows)
    lab = pd.Series({k: ("house" if k.startswith("map:") else "0" if k.startswith("cell:") else "not a house")
                     for k in f.key[f.role == "sample"]})
    est = A.estimate(f, lab, k={}, B=20)
    r = est.loc["residual: cell expansion (ES)"]
    assert r.high == pytest.approx(400 * (1 - 0.05 ** (1 / 50)) * 3.0) and r["widened by"] == "S6A"


def test_start_round2_replaces_and_keeps_where_no_reserve():
    obj, cells = fake_frame()
    f = A.draw(obj, cells, seed=3)
    # one tiny fully sampled county in S2 whose only item is a pilot item
    i = f.index[(f.stratum == "S2") & f.pilot][0]
    f.loc[i, "county"] = "Tiny"
    used = set(f.key[f.pilot & (f.role == "sample")]) | set(f.key[f.role == "calibration"])
    g = A.start_round2(f, used)
    assert g.at[i, "round2"] == A.KEPT and g.at[i, "role"] == "sample" and not g.at[i, "pilot"]
    assert (g.role == "discarded pilot").sum() == 74
    assert (g.role == "used calibration").sum() == 30 and (g.role == "calibration").sum() == 30
    new = set(g.key[(g.role == "calibration") | (g.pilot & (g.role == "sample"))])
    assert not new & used
    assert (g.role == "sample").sum() == (f.role == "sample").sum()
    for ph in ("calibration", "pilot", "main"):
        assert not set(A.queue(g, "UA", ph).key) & used          # KEPT is in no queue
    with pytest.raises(RuntimeError):
        A.start_round2(f, used | new)


def test_gate_flag_and_pace(tmp_path):
    a, b = A.Store(tmp_path, "UA"), A.Store(tmp_path, "M")
    keys = [f"k{i}" for i in range(20)]
    for i, k in enumerate(keys):
        a.add(k, "house" if i < 10 else "not a house", "pilot", check_later=(i == 0), note="why" if i == 0 else "")
        b.add(k, "house" if i < 10 else "not a house", "pilot")
    fr = pd.DataFrame({"key": keys, "stratum": "S1"})
    L = A.load_labels(tmp_path)
    g = A.gate(L, fr, ["UA", "M"], keys)
    assert g["verdict"] == "PASS" and g["kappa"] == pytest.approx(1)
    assert A.gate(L, fr, ["UA", "M"], keys + ["missing"])["verdict"] == "not complete"
    b.add("k11", A.CANT_TELL, "pilot"); b.add("k12", A.CANT_TELL, "pilot"); b.add("k13", A.CANT_TELL, "pilot")
    g2 = A.gate(A.load_labels(tmp_path), fr, ["UA", "M"], keys)
    assert g2["verdict"].startswith("STOP")                    # 3 of 40 labels = 7.5% > 5%
    fl = A.agreement_by_flag(L, ["UA", "M"]).set_index("photos")
    assert fl.loc["flagged", "n"] == 1 and fl.loc["not flagged", "n"] == 19
    p = A.pace(A.load_raw(tmp_path)).set_index("interpreter")
    assert p.loc["UA", "notes"] == 1 and p.loc["UA", "check later"] == 1 and p.loc["M", "labels"] == 23


def test_house_vs_cant_tell_is_a_disagreement():
    L = pd.DataFrame({"key": ["x", "y", "z", "x", "y", "z"], "reviewer": list("aaabbb"),
                      "value": ["house", "not a house", "house", A.CANT_TELL, "not a house", "house"],
                      "phase": "pilot", "note": ""})
    fr = pd.DataFrame({"key": ["x", "y", "z"], "stratum": "S4"})
    t = A.agreement(L, fr, ["a", "b"], B=20).set_index("items")
    assert t.loc["all objects", "kappa (house / not)"] < 1


def test_render_closeup_without_network():
    from rasterio.transform import from_origin
    img = (np.random.default_rng(0).random((300, 300, 3)) * 255).astype(np.uint8)
    png = A.render_closeup((img, from_origin(X0, Y0, 1, 1), "EPSG:32618", "2023-06-02"), caption="E01: house")
    assert png[:4] == b"\x89PNG"
