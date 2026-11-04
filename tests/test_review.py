"""Tests for geo_anom.task1.review (labels and summaries; no imagery)."""

from __future__ import annotations

import pandas as pd
import pytest

from geo_anom.task1 import review as R


def row(key, county="Wicomico", group="es_unmatched"):
    return {"key": key, "county": county, "group": group}


def test_store_latest_label_wins(tmp_path):
    s = R.LabelStore(tmp_path / "labels_ua.csv", "ua")
    s.add(row("a"), "not poultry")
    s.add(row("b"), "poultry house")
    s.add(row("a"), "poultry house")            # "back" then relabel
    lab = s.latest().set_index("key")["label"]
    assert lab.to_dict() == {"a": "poultry house", "b": "poultry house"}
    assert s.done() == {"a", "b"}


def test_store_needs_reviewer_and_known_label(tmp_path):
    with pytest.raises(ValueError):
        R.LabelStore(tmp_path / "labels_x.csv", "  ")
    s = R.LabelStore(tmp_path / "labels_ua.csv", "ua")
    with pytest.raises(ValueError):
        s.add(row("a"), "maybe")


def test_confirmed_needs_every_reviewer(tmp_path):
    a = R.LabelStore(tmp_path / "labels_a.csv", "a")
    b = R.LabelStore(tmp_path / "labels_b.csv", "b")
    a.add(row("k1"), "poultry house"); b.add(row("k1"), "poultry house")
    a.add(row("k2"), "poultry house"); b.add(row("k2"), "not poultry")
    a.add(row("k3"), "poultry house")
    labels = R.load_labels(tmp_path)
    assert R.confirmed_keys(labels) == {"k1", "k3"}


def test_kappa():
    assert R.cohen_kappa(["y", "n", "y"], ["y", "n", "y"]) == pytest.approx(1.0)
    assert R.cohen_kappa(["y", "y", "n", "n"], ["y", "n", "y", "n"]) == pytest.approx(0.0)


def test_summary_precision_range_and_controls(tmp_path):
    q = pd.DataFrame([row("u1"), row("u2"), row("u3"), row("c1", group="control"),
                      row("w1", county="Charles", group="unverified")])
    s = R.LabelStore(tmp_path / "labels_a.csv", "a")
    s.add(q.iloc[0], "poultry house")
    s.add(q.iloc[1], "not poultry")
    s.add(q.iloc[3], "poultry house")
    s.add(q.iloc[4], "not poultry")
    summaries = {"Wicomico": {"accuracy": {"detections": 10, "tp": 7}}, "Charles": {"accuracy": None}}
    out = R.summarize(q, R.load_labels(tmp_path), summaries)
    p = out["precision"].loc["Wicomico"]
    assert p["precision low"] == pytest.approx(0.8)      # 7 traced + 1 confirmed
    assert p["precision high"] == pytest.approx(0.9)     # everything but the 1 rejected
    assert p["not yet checked"] == 1
    assert out["control"] == {"checked": 1, "called poultry house": 1, "agreement": 1.0}
    assert out["unverified"].loc["Charles", "not poultry"] == 1


def test_kind_store_takes_its_own_labels(tmp_path):
    import pytest
    from geo_anom.task1 import review as R
    st = R.LabelStore(tmp_path / "labels_kind_UA.csv", "UA", labels=R.KIND_LABELS)
    row = {"key": "frederick/r001_c002_000", "county": "Frederick", "group": "unverified"}
    st.add(row, "dairy")
    assert st.done() == {"frederick/r001_c002_000"}
    with pytest.raises(ValueError):
        st.add(row, "poultry house")


def test_poultry_labels_ignore_kind_files(tmp_path):
    from geo_anom.task1 import review as R
    row = {"key": "k1", "county": "Frederick", "group": "unverified"}
    R.LabelStore(tmp_path / "labels_UA.csv", "UA").add(row, "not poultry")
    R.LabelStore(tmp_path / "labels_kind_UA.csv", "UA", labels=R.KIND_LABELS).add(row, "dairy")
    assert R.load_labels(tmp_path).label.tolist() == ["not poultry"]


def test_check_queue_keeps_only_unchecked(tmp_path, monkeypatch):
    import json
    import geopandas as gpd
    from shapely.geometry import box
    utm = R.UTM
    out = tmp_path / "county_wicomico"; out.mkdir()
    b = gpd.GeoDataFrame({"candidate_id": ["wicomico/t0_000", "wicomico/t0_001", "wicomico/t0_002", "wicomico/t0_003"],
                          "tile_path": ["t0.tif"] * 4, "assigned_distance_m": [100.0] * 4},
                         geometry=[box(0, 0, 150, 15),        # on a traced house -> control
                                   box(0, 300, 150, 315),     # already in the final map -> left out
                                   box(0, 600, 150, 615),     # new, unchecked
                                   box(0, 900, 150, 915)],    # new, unchecked
                         crs=utm).to_crs(4326)
    b.to_file(out / "buildings.geojson", driver="GeoJSON")
    (out / "run_meta.json").write_text("{}")
    (out / "sites.json").write_text(json.dumps([{"tile_path": "t0.tif", "naip_item_ids": ["x"]}]))
    cty = gpd.GeoDataFrame(geometry=[box(-5000, -5000, 5000, 5000)], crs=utm)
    monkeypatch.setattr(R.region, "county_boundary", lambda n: cty)
    gt = gpd.GeoDataFrame(geometry=[box(1, 1, 149, 14)], crs=utm)
    known = gpd.GeoDataFrame(geometry=[box(2, 301, 148, 314)], crs=utm)
    q = R.build_check_queue(tmp_path, ["Wicomico"], known=known, gt=gt, key_prefix="ft:")
    assert sorted(q.key) == ["ft:wicomico/t0_000", "ft:wicomico/t0_002", "ft:wicomico/t0_003"]
    assert q.set_index("key").loc["ft:wicomico/t0_000", "group"] == "control"
    assert (q.naip_item_ids.map(list) == pd.Series([["x"]] * 3)).all()
    assert R.build_check_queue(tmp_path, ["Queen Anne's"], gt=gt).empty      # county not run yet


def test_check_queue_skips_detections_on_roads(tmp_path, monkeypatch):
    import json
    import geopandas as gpd
    from shapely.geometry import box
    from geo_anom.task1 import detect
    utm = R.UTM
    out = tmp_path / "county_wicomico"; out.mkdir()
    gpd.GeoDataFrame({"candidate_id": ["w/0", "w/1", "w/2"], "tile_path": ["t0.tif"] * 3, "assigned_distance_m": [1.0] * 3},
                     geometry=[box(0, 0, 150, 15), box(0, 600, 150, 615), box(0, 900, 150, 915)],
                     crs=utm).to_crs(4326).to_file(out / "buildings.geojson", driver="GeoJSON")
    (out / "run_meta.json").write_text("{}")
    (out / "sites.json").write_text(json.dumps([{"tile_path": "t0.tif"}]))
    monkeypatch.setattr(R.region, "county_boundary", lambda n: gpd.GeoDataFrame(geometry=[box(-5000, -5000, 5000, 5000)], crs=utm))
    # w/1 sits on a road (2 m); w/0 is a control near a road -- controls are never dropped
    monkeypatch.setattr(detect, "distance_to_roads", lambda b, cache: pd.Series([3.0, 2.0, 250.0], index=b.index))
    gt = gpd.GeoDataFrame(geometry=[box(1, 1, 149, 14)], crs=utm)
    q = R.build_check_queue(tmp_path, ["Wicomico"], gt=gt, road_cache=tmp_path / "osm")
    assert sorted(q.key) == ["w/0", "w/2"]
    assert q.attrs["on_road"] == {"Wicomico": 1}


def test_agreement_queue_mixes_new_houses_and_rechecks():
    import geopandas as gpd
    from shapely.geometry import box
    utm = R.UTM
    rel = gpd.GeoDataFrame({"house_id": [f"MD-{i:05d}" for i in range(6)], "county": "Wicomico",
                            "source": ["detector", "brightened photo", "brightened photo", "SAM repair", "SAM repair", "SAM repair"]},
                           geometry=[box(0, i * 50, 150, i * 50 + 15) for i in range(6)], crs=utm)
    q07 = gpd.GeoDataFrame({"key": ["a", "b", "c", "d"], "county": "Wicomico", "group": ["es_unmatched"] * 3 + ["control"]},
                           geometry=[box(1000, i * 50, 1150, i * 50 + 15) for i in range(4)], crs=utm)
    lab = pd.DataFrame({"key": ["a", "b", "c", "d"], "label": ["poultry house", "not poultry", "unsure", "poultry house"],
                        "reviewer": "UA", "labelled_at": "2026-11-01"})
    q = R.build_agreement_queue(rel, q07, lab, n_new=2, n_old=4)
    assert q.group.value_counts().to_dict() == {"brightened photo": 2, "SAM repair": 2, "07 recheck": 2}
    assert set(q[q.group == "07 recheck"].key) == {"a", "b"}          # unsure and controls left out
    assert q.key.str.startswith("release_v1:").sum() == 4


def test_wilson_interval():
    lo, hi = R.wilson(27, 30)
    assert 0.73 < lo < 0.75 and 0.96 < hi < 0.98
