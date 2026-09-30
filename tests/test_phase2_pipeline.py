"""Tests for Phase 2 pipeline components."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from geo_anom.core.config import load_config, NutrientCoefficient
from geo_anom.core.geo_utils import BBox, meters_sq_to_acres, polygon_area_m2
from geo_anom.phase2.species_capacity import predict_poultry_headcount
from geo_anom.phase2.yolo_detector import Detection
from geo_anom.phase2.supply_calculator import SupplyCalculator


class TestDetection:
    """Test the Detection dataclass."""

    def test_center_px(self):
        det = Detection(
            bbox_px=(100, 200, 300, 400),
            bbox_geo=(-76.1, 38.5, -76.0, 38.6),
            confidence=0.95,
            class_id=0,
            class_name="poultry_house",
            tile_path="test.tif",
        )
        assert det.center_px == (200, 300)


class TestSupplyCalculation:
    """Test nutrient supply math with known inputs."""

    def test_broiler_nitrogen_calculation(self):
        """
        150,000 broilers × 0.91 lb N/head/yr × 6.5 flocks/yr = 887,250 lb N/yr
        """
        coeff = NutrientCoefficient(
            N_lbs_per_head_per_year=0.91,
            P2O5_lbs_per_head_per_year=0.63,
            flocks_per_year=6.5,
        )
        headcount = 150_000
        annual_n = headcount * coeff.N_lbs_per_head_per_year * coeff.flocks_per_year
        assert abs(annual_n - 887_250.0) < 1.0

    def test_broiler_phosphorus_calculation(self):
        """
        150,000 broilers × 0.63 lb P₂O₅/head/yr × 6.5 flocks/yr = 614,250 lb P₂O₅/yr
        """
        coeff = NutrientCoefficient(
            N_lbs_per_head_per_year=0.91,
            P2O5_lbs_per_head_per_year=0.63,
            flocks_per_year=6.5,
        )
        headcount = 150_000
        annual_p = headcount * coeff.P2O5_lbs_per_head_per_year * coeff.flocks_per_year
        assert abs(annual_p - 614_250.0) < 1.0

    def test_dairy_cattle_nitrogen(self):
        """500 dairy cattle × 168 lb N/head/yr × 1 cycle = 84,000 lb N/yr"""
        coeff = NutrientCoefficient(
            N_lbs_per_head_per_year=168.0,
            P2O5_lbs_per_head_per_year=96.0,
            flocks_per_year=1.0,
        )
        headcount = 500
        annual_n = headcount * coeff.N_lbs_per_head_per_year * coeff.flocks_per_year
        assert annual_n == 84_000.0

    def test_normalize_animal_type(self):
        """Test that animal type normalization works."""
        calc = SupplyCalculator()
        assert calc._normalize_animal_type("Broiler Chicken") == "broiler_chicken"
        assert calc._normalize_animal_type("  TURKEY  ") == "turkey"
        assert calc._normalize_animal_type("dairy") == "dairy_cattle"
        assert calc._normalize_animal_type("hog") == "swine"
        assert calc._normalize_animal_type("") == "unknown"

    def test_normalize_raw_socrata_animal_types(self):
        """The exact-match table never matches the live registry's actual
        raw column-name values -- these are the real strings, not made up
        for the test. Covers the exact bug found 2026-09: broilers (the
        dominant type) silently mapped to nothing."""
        calc = SupplyCalculator()
        assert calc._normalize_animal_type("chickens_not_laying_hens") == "broiler_chicken"
        assert calc._normalize_animal_type("swine_55_lbs") == "swine"
        assert calc._normalize_animal_type("cattle_includes_heifers") == "beef_cattle"
        assert calc._normalize_animal_type("chickens_laying_hens") == "layer_chicken"
        # a real, currently-uncoefficiented type -- must NOT collide with a
        # keyword (e.g. must not match "hen") and must surface as itself,
        # not silently become "unknown", so it's visible in the
        # no-nutrient-coefficient warning instead of being hidden.
        assert calc._normalize_animal_type("ducks_liquid_manure") == "ducks_liquid_manure"


class TestSupplyApportionment:
    """calculate_supply() end-to-end: a farm/cluster's total nutrient
    number must be divided across all its detected structures, not
    assigned in full to each one -- the bug found 2026-09 that would have
    overcounted statewide totals by a factor of N on any farm with more
    than one detected structure (routine at real scale: 5-20 barns/farm).
    The split itself is weighted by each structure's share of the group's
    total detected floor area, not an even 1/N split -- see
    docs/task1_metrics.md section 2 for why an even split is a poor
    assumption (headcount-vs-house-count R^2=0.043 vs. headcount-vs-area
    R^2=0.256 log-log: farms trade off house count against house size).

    As of 2026-09-30, headcount for poultry-shaped detections comes from
    `species_capacity.predict_poultry_headcount()` (floor area only, no
    registry lookup at prediction time) rather than the matched permit's
    headcount -- see docs/task1_completion_criteria.md for why a
    registry-dependent number defeated the point of using remote sensing
    at all. These tests compute their expected values through that same
    model rather than hardcoding a registry headcount, since that registry
    number is no longer what the pipeline actually uses."""

    def test_apportions_proportionally_to_floor_area(self):
        """Two structures at one farm with a 3:1 area ratio must receive
        nutrient shares in that same 3:1 ratio, not an even 1:1 split."""
        permits = gpd.GeoDataFrame(
            {"animal_type": ["chickens_not_laying_hens"], "headcount": [100_000]},
            geometry=[Point(-75.80, 38.60)],
            crs="EPSG:4326",
        )
        polygons = gpd.GeoDataFrame(
            {
                "class_name": ["poultry_house"] * 2,
                "area_m2": [3000.0, 1000.0],  # 3:1 ratio
                "confidence": [0.9, 0.9],
            },
            geometry=[Point(-75.8001, 38.6001), Point(-75.8002, 38.6002)],
            crs="EPSG:4326",
        )

        result = SupplyCalculator().calculate_supply(polygons, permits)

        assert len(result) == 2
        assert (result["capacity_source"] == "vision_poultry_model").all()
        big, small = result.sort_values("area_m2", ascending=False)["annual_N_lbs"]
        assert big == pytest.approx(3 * small, rel=1e-3)

        config = load_config()
        coeff = config.nutrient_coefficients["broiler_chicken"]
        predicted_headcount, _ = predict_poultry_headcount(4000.0, 2)
        farm_total_n = predicted_headcount * coeff.N_lbs_per_head_per_year * coeff.flocks_per_year
        assert result["annual_N_lbs"].sum() == pytest.approx(farm_total_n, rel=1e-3)
        # The registry's headcount is still carried for comparison, but is
        # not what the N/P numbers above were computed from.
        assert (result["registry_headcount"] == 100_000).all()

    def test_falls_back_to_even_split_when_area_data_missing(self):
        """If a farm's structures have no usable area data (area sums to
        zero), apportion evenly rather than dividing by zero."""
        permits = gpd.GeoDataFrame(
            {"animal_type": ["chickens_not_laying_hens"], "headcount": [100_000]},
            geometry=[Point(-75.80, 38.60)],
            crs="EPSG:4326",
        )
        polygons = gpd.GeoDataFrame(
            {
                "class_name": ["poultry_house"] * 2,
                "area_m2": [0.0, 0.0],
                "confidence": [0.9, 0.9],
            },
            geometry=[Point(-75.8001, 38.6001), Point(-75.8002, 38.6002)],
            crs="EPSG:4326",
        )

        result = SupplyCalculator().calculate_supply(polygons, permits)

        assert result["annual_N_lbs"].iloc[0] == pytest.approx(result["annual_N_lbs"].iloc[1])

    def test_equal_area_structures_still_split_evenly(self):
        """Area-weighting should reduce to an even split as the special
        case where every structure at a farm has the same area."""
        permits = gpd.GeoDataFrame(
            {
                "animal_type": ["chickens_not_laying_hens"],
                "headcount": [100_000],
            },
            geometry=[Point(-75.80, 38.60)],
            crs="EPSG:4326",
        )
        # Three structures at the same farm, close enough to all join to
        # the one permit above (well within the default 2km).
        polygons = gpd.GeoDataFrame(
            {
                "class_name": ["poultry_house"] * 3,
                "area_m2": [1000.0, 1000.0, 1000.0],
                "confidence": [0.9, 0.9, 0.9],
            },
            geometry=[
                Point(-75.8001, 38.6001),
                Point(-75.8002, 38.6002),
                Point(-75.8003, 38.6003),
            ],
            crs="EPSG:4326",
        )

        result = SupplyCalculator().calculate_supply(polygons, permits)

        assert len(result) == 3
        assert (result["n_structures_at_farm"] == 3).all()

        config = load_config()
        coeff = config.nutrient_coefficients["broiler_chicken"]
        predicted_headcount, _ = predict_poultry_headcount(3000.0, 3)
        farm_total_n = predicted_headcount * coeff.N_lbs_per_head_per_year * coeff.flocks_per_year
        expected_per_structure = round(farm_total_n / 3, 1)

        assert (result["annual_N_lbs"] == expected_per_structure).all()
        # Summing back across the farm reconstructs the real farm total,
        # not 3x an overcount.
        assert result["annual_N_lbs"].sum() == pytest.approx(farm_total_n, rel=1e-3)

    def test_matched_poultry_subtype_used_for_coefficient_not_headcount(self):
        """A matched permit's specific poultry subtype (turkey, here) still
        picks which nutrient coefficient applies -- that's using available
        information, not depending on it -- but the headcount itself comes
        from the vision model, not the registry's 10,000."""
        permits = gpd.GeoDataFrame(
            {"animal_type": ["turkeys"], "headcount": [10_000]},
            geometry=[Point(-75.80, 38.60)],
            crs="EPSG:4326",
        )
        polygons = gpd.GeoDataFrame(
            {"class_name": ["poultry_house"], "area_m2": [800.0], "confidence": [0.9]},
            geometry=[Point(-75.8001, 38.6001)],
            crs="EPSG:4326",
        )

        result = SupplyCalculator().calculate_supply(polygons, permits)

        assert len(result) == 1
        assert result.iloc[0]["n_structures_at_farm"] == 1
        assert result.iloc[0]["capacity_source"] == "vision_poultry_model"
        assert result.iloc[0]["animal_type"] == "turkey"
        assert result.iloc[0]["registry_headcount"] == 10_000
        assert result.iloc[0]["headcount"] != 10_000  # not the registry number

        config = load_config()
        coeff = config.nutrient_coefficients["turkey"]
        predicted_headcount, _ = predict_poultry_headcount(800.0, 1)
        expected_n = round(predicted_headcount * coeff.N_lbs_per_head_per_year * coeff.flocks_per_year, 1)
        assert result.iloc[0]["annual_N_lbs"] == pytest.approx(expected_n, rel=1e-3)

    def test_unregistered_poultry_shaped_cluster_still_gets_a_number(self):
        """The actual point of this change: a detected building cluster
        with NO permit anywhere nearby must still produce a nonzero N/P
        estimate, not a silent zero -- that's the difference between a
        pipeline that only works on farms already in the registry and one
        that doesn't need the registry at all."""
        permits = gpd.GeoDataFrame(
            {"animal_type": [], "headcount": []},
            geometry=[],
            crs="EPSG:4326",
        )
        polygons = gpd.GeoDataFrame(
            {"class_name": ["poultry_house"] * 2, "area_m2": [1200.0, 1500.0], "confidence": [0.9, 0.9]},
            geometry=[Point(-76.10, 39.00), Point(-76.1005, 39.0005)],
            crs="EPSG:4326",
        )

        result = SupplyCalculator().calculate_supply(polygons, permits)

        assert len(result) == 2
        assert (result["capacity_source"] == "vision_poultry_model").all()
        assert (result["registry_headcount"].isna()).all()
        assert (result["annual_N_lbs"] > 0).all()
        assert (result["headcount"] > 0).all()

    def test_matched_non_poultry_species_falls_back_to_registry(self):
        """A matched permit with a known non-poultry species (dairy here)
        should NOT run the poultry capacity model -- it wasn't fit on that
        shape -- and should fall back to the registry's own headcount,
        explicitly flagged as a fallback rather than vision-derived."""
        permits = gpd.GeoDataFrame(
            {"animal_type": ["dairy_cattle"], "headcount": [500]},
            geometry=[Point(-75.80, 38.60)],
            crs="EPSG:4326",
        )
        polygons = gpd.GeoDataFrame(
            {"class_name": ["poultry_house"], "area_m2": [1200.0], "confidence": [0.9]},
            geometry=[Point(-75.8001, 38.6001)],
            crs="EPSG:4326",
        )

        result = SupplyCalculator().calculate_supply(polygons, permits)

        assert result.iloc[0]["capacity_source"] == "registry_fallback"
        assert result.iloc[0]["headcount"] == 500

        config = load_config()
        coeff = config.nutrient_coefficients["dairy_cattle"]
        expected_n = round(500 * coeff.N_lbs_per_head_per_year * coeff.flocks_per_year, 1)
        assert result.iloc[0]["annual_N_lbs"] == expected_n


class TestGeoUtils:
    """Test geospatial utilities."""

    def test_meters_sq_to_acres(self):
        # 1 acre = 4046.86 m²
        assert abs(meters_sq_to_acres(4046.86) - 1.0) < 0.001

    def test_bbox_from_point(self):
        bb = BBox.from_point(lon=-76.0, lat=38.5, buffer_km=1.0)
        assert bb.west < -76.0 < bb.east
        assert bb.south < 38.5 < bb.north

    def test_bbox_buffer(self):
        bb = BBox(west=-76.1, south=38.5, east=-76.0, north=38.6)
        buffered = bb.buffer(km=1.0)
        assert buffered.west < bb.west
        assert buffered.east > bb.east

    def test_bbox_to_esri_string(self):
        bb = BBox(west=-76.1, south=38.5, east=-76.0, north=38.6)
        assert bb.to_esri_string() == "-76.1,38.5,-76.0,38.6"

    def test_config_loads_nutrient_coefficients(self):
        config = load_config()
        assert "broiler_chicken" in config.nutrient_coefficients
        bc = config.nutrient_coefficients["broiler_chicken"]
        assert bc.N_lbs_per_head_per_year == 0.91
        assert bc.flocks_per_year == 6.5
