"""Tests for geo_anom.task1 -- the parts checkable without imagery or weights."""

from __future__ import annotations

import pytest
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform

from geo_anom.task1.detect import filter_reasons, passes_tulbure_filter, polygon_stats
from geo_anom.task1.merge import deduplicate
from geo_anom.task1.species import species_group
from geo_anom.task1.supply import building_supply, farm_supply

TO_WGS84 = Transformer.from_crs("EPSG:32618", "EPSG:4326", always_xy=True).transform
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True).transform
X0, Y0 = 440_000, 4_250_000  # somewhere on the Eastern Shore, UTM 18N


def house(dx=0.0, dy=0.0, length=120.0, width=15.0):
    return box(X0 + dx, Y0 + dy, X0 + dx + length, Y0 + dy + width)


def feature(poly, tile, farm, prob=0.9, animal_type="chickens_not_laying_hens"):
    return {"type": "Feature", "geometry": mapping(transform(TO_WGS84, poly)), "properties": {
        "kept": True, "tile": tile, "tile_path": f"tiles/{tile}.tif", "farm_name": farm, "animal_type": animal_type,
        "area_m2": poly.area, "mean_prob": prob}}


def site(name, dx, dy, animal_type="chickens_not_laying_hens", headcount=100_000):
    lon, lat = TO_WGS84(X0 + dx, Y0 + dy)
    return {"farm_name": name, "lat": lat, "lon": lon, "animal_type": animal_type,
            "headcount": headcount, "county": "Somerset"}


class TestFilter:
    def test_typical_poultry_house_kept(self):
        s = polygon_stats(house())
        assert s["length_m"] == pytest.approx(120) and s["width_m"] == pytest.approx(15)
        assert filter_reasons(s) == []

    def test_reasons_name_every_failure(self):
        reasons = filter_reasons(polygon_stats(house(length=30, width=6)))
        assert any(r.startswith("area") for r in reasons)
        assert any(r.startswith("length") for r in reasons)
        assert any(r.startswith("width") for r in reasons)

    def test_beef_override_only_applies_to_beef(self):
        s = polygon_stats(house(length=50, width=22))  # 1100 m2, aspect 2.27
        assert filter_reasons(s, "chickens_not_laying_hens")
        assert filter_reasons(s, "cattle_includes_heifers") == []

    def test_old_stats_keys_still_accepted(self):
        assert passes_tulbure_filter({"area_m2": 1800, "long_side_m": 120, "short_side_m": 15}, None)


class TestDeduplicate:
    def test_same_barn_from_two_tiles_counted_once(self):
        a, b = house(), house(dx=1.5)  # ~99% overlap, detected from two tiles
        sites = [site("Farm A", 60, 0), site("Farm B", 900, 0)]
        out = deduplicate([feature(a, "t1", "Farm A", 0.8), feature(b, "t2", "Farm B", 0.95)], sites)
        assert len(out) == 1
        assert out.iloc[0]["n_detections"] == 2
        assert out.iloc[0]["mean_prob"] == pytest.approx(0.95)  # higher-confidence copy kept

    def test_neighbouring_barns_kept_separate(self):
        out = deduplicate([feature(house(), "t1", "A"), feature(house(dy=30), "t1", "A")], [site("A", 0, 0)])
        assert len(out) == 2

    def test_attributed_to_nearest_permit_not_tile(self):
        # Barn sits next to Farm B's permit but was found in Farm A's tile.
        sites = [site("Farm A", -800, 0), site("Farm B", 60, 0, animal_type="dairy_cattle")]
        out = deduplicate([feature(house(), "tA", "Farm A")], sites)
        row = out.iloc[0]
        assert row["assigned_farm"] == "Farm B"
        assert row["tile_farm_name"] == "Farm A"
        assert row["species_group"] == "dairy"
        assert row["assigned_distance_m"] < 100


class TestSupply:
    def test_farm_total_and_area_split(self):
        sites = [site("A", 0, 0, headcount=100_000), site("D", 5000, 0, "dairy_cattle", 500)]
        b = deduplicate([feature(house(), "t", "A"), feature(house(dy=40, length=60), "t", "A")], sites)
        farms = farm_supply(sites, b)
        a = farms.set_index("farm_name").loc["A"]
        assert a["annual_N_lbs"] == pytest.approx(100_000 * a["N_per_head_per_flock"] * a["flocks_per_year"])

        bs = building_supply(b, farms)
        assert bs["annual_N_lbs"].sum() == pytest.approx(a["annual_N_lbs"], rel=1e-4)
        big, small = sorted(bs["annual_N_lbs"], reverse=True)
        assert big / small == pytest.approx(2.0, rel=1e-3)  # 120 m vs 60 m house

    def test_undetected_farm_keeps_supply_at_registry_point(self):
        sites = [site("D", 0, 0, "dairy_cattle", 500)]
        b = deduplicate([feature(house(dx=20_000), "t", "X")], sites + [site("X", 20_000, 0)])
        d = farm_supply(sites, b).iloc[0]
        assert d["located_by"] == "registry_point_only" and d["annual_N_lbs"] > 0

    def test_species_without_coefficient_flagged(self):
        d = farm_supply([site("H", 0, 0, "horses", 40)], deduplicate([], [site("H", 0, 0)])).iloc[0]
        assert d["no_coefficient"] and d["annual_N_lbs"] == 0


def test_species_groups():
    assert species_group("chickens_not_laying_hens") == "broiler"
    assert species_group("dairy_cattle") == "dairy"
    assert species_group(None) == "unknown"
    assert species_group("something_new") == "unknown"


def test_farm_overview_pin_sits_on_barns_not_registry_point():
    from geo_anom.task1.merge import farm_overview
    # registry point 600 m west of the two barns it owns
    sites = [site("A", -600, 0)]
    b = deduplicate([feature(house(), "t", "A"), feature(house(dy=40), "t", "A")], sites)
    ov = farm_overview(b)
    assert len(ov) == 1 and ov.iloc[0]["buildings"] == 2
    pin = transform(TO_UTM, ov.geometry.iloc[0])
    assert abs(pin.x - (X0 + 60)) < 5 and abs(pin.y - (Y0 + 27.5)) < 5   # centre of the two houses
    assert 550 < ov.iloc[0]["registry_point_distance_m"] < 700
    assert ov.iloc[0]["maps_url"].startswith("https://www.google.com/maps/@")
