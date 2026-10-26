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
