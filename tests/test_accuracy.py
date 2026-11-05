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
    assert e["houses on neither source"] == pytest.approx(10)
    assert e["recall (ES)"] == pytest.approx(60 / 94)
    assert e["roof km2 (ES)"] == pytest.approx((60 + 24 + 10) * 2500 / 1e6)
    assert (est["high"] - est["low"]).abs().max() < 1e-9


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
    a.add("k3", "unsure", "main"); b.add("k3", "house", "main")
    a.add("k4", "house", "main"); b.add("k4", "not a house", "main")
    L = A.load_labels(tmp_path)
    q = A.adjudication_queue(L, ["UA", "JH"])
    assert set(q.key) == {"k2", "k3", "k4"}
    adj = tmp_path / "adjudicated.csv"
    A.adjudicate(adj, "k2", "gone", "roof missing on 2023 photo", "UA+JH")
    with pytest.raises(ValueError):
        A.adjudicate(adj, "k3", "house", "", "UA")
    fin = A.final_labels(L, ["UA", "JH"], pd.read_csv(adj))
    assert fin.to_dict() == {"k1": "house", "k2": "gone", "k3": "unsure", "k4": "unsure"}


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
