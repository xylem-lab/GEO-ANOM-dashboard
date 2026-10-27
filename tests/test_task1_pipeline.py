"""Tests for geo_anom.task1 -- the parts checkable without imagery or weights."""

from __future__ import annotations

import pytest
from pyproj import Transformer
from shapely.geometry import box, mapping
import numpy as np
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


class TestGrid:
    def test_tiles_cover_area_with_overlap(self):
        from geo_anom.task1 import region
        import geopandas as gpd
        # 10 km x 6 km rectangle of "land"
        area = gpd.GeoDataFrame(geometry=[box(X0, Y0, X0 + 10_000, Y0 + 6_000)], crs="EPSG:32618")
        sites = region.grid_sites(area, "Test County", tile_dir=None)
        assert len(sites) == len({s["grid_id"] for s in sites})          # unique ids
        xs = sorted({round(TO_UTM(s["lon"], s["lat"])[0]) for s in sites})
        steps = np.diff(xs)
        assert np.allclose(steps, region.STRIDE_M, atol=2)               # 1,750 m apart -> 250 m overlap
        assert all(s["tile_path"].startswith("data/raw/naip_grid/test_county/") for s in sites)

    def test_mostly_water_tiles_skipped(self):
        from geo_anom.task1 import region
        import geopandas as gpd
        # a thin 50 m strip of land: tiles over it have < 5% land
        area = gpd.GeoDataFrame(geometry=[box(X0, Y0, X0 + 6_000, Y0 + 50)], crs="EPSG:32618")
        assert region.grid_sites(area, "Strip") == []


def test_grid_dedupe_keeps_largest_outline():
    whole, cut = house(length=150), house(length=110)     # same barn, cut by a tile edge
    sites = [site("A", 60, 0)]
    out = deduplicate([feature(whole, "t1", "A", prob=0.80), feature(cut, "t2", "A", prob=0.95)], sites, prefer="area")
    assert len(out) == 1 and out.iloc[0]["area_m2"] == pytest.approx(150 * 15)
    out = deduplicate([feature(whole, "t1", "A", prob=0.80), feature(cut, "t2", "A", prob=0.95)], sites)
    assert out.iloc[0]["area_m2"] == pytest.approx(110 * 15)            # default: most confident


def test_results_root_override_and_local_fallback(tmp_path, monkeypatch):
    from geo_anom.task1 import env
    monkeypatch.setenv("GEO_ANOM_RESULTS", str(tmp_path))
    assert env.results_root() == tmp_path
    monkeypatch.delenv("GEO_ANOM_RESULTS")
    monkeypatch.setattr(env, "_drive_candidates", lambda: [])
    assert env.results_root() == env.ROOT / "data/processed/task1"
    monkeypatch.setattr(env, "_drive_candidates", lambda: [str(tmp_path / "Task1_results" / env.RESULTS_MARKER)])
    assert env.results_root() == tmp_path / "Task1_results"


def test_checkpoint_on_disk_matches_published_hash():
    from geo_anom.task1 import env
    if env.CHECKPOINT["path"].exists():
        assert env.sha256(env.CHECKPOINT["path"]) == env.CHECKPOINT["sha256"]


def test_ground_truth_taken_from_shared_drive_copy(tmp_path, monkeypatch):
    from geo_anom.task1 import env
    real = env.ROOT / "data/raw/external/soroka_duren/Delmarva_PL_House_Final.zip"
    if not real.exists():
        pytest.skip("USGS zip not on this machine")
    drive = tmp_path / "Task1_results"; drive.mkdir()
    (drive / real.name).write_bytes(real.read_bytes())          # what the user uploads
    monkeypatch.setenv("GEO_ANOM_RESULTS", str(drive))
    monkeypatch.setitem(env.GROUND_TRUTH, "zip", tmp_path / "gt" / real.name)
    monkeypatch.setitem(env.GROUND_TRUTH, "dir", tmp_path / "gt" / "unzipped")
    monkeypatch.setattr(env, "_fetch", lambda *a, **k: pytest.fail("should not download"))
    shp = env.ensure_ground_truth()
    assert shp.suffix == ".shp" and shp.exists()


def test_wrong_ground_truth_file_rejected(tmp_path, monkeypatch):
    from geo_anom.task1 import env
    drive = tmp_path / "Task1_results"; drive.mkdir()
    (drive / "Delmarva_PL_House_Final.zip").write_bytes(b"not the USGS file")
    monkeypatch.setenv("GEO_ANOM_RESULTS", str(drive))
    monkeypatch.setitem(env.GROUND_TRUTH, "zip", tmp_path / "gt" / "Delmarva_PL_House_Final.zip")
    monkeypatch.setitem(env.GROUND_TRUTH, "dir", tmp_path / "gt" / "unzipped")
    with pytest.raises(RuntimeError, match="SHA-256"):
        env.ensure_ground_truth()


def test_streaming_keeps_only_a_few_tiles_in_memory():
    """Downloads faster than detection: tiles must not pile up (Colab RAM crash, 2026-10-26)."""
    import gc
    import threading
    import time
    import weakref

    from geo_anom.task1.pipeline import stream_tiles

    class Tile:                      # stands in for a tile array; weakly referenceable
        def __init__(self):
            self.data = bytearray(1000)

    alive, lock, peak, handled = weakref.WeakSet(), threading.Lock(), [0], []

    def fetch(site):
        t = Tile()
        with lock:
            alive.add(t)
        return t, {}, site

    def handle(site, got):
        time.sleep(0.002)           # the slow "detector"
        gc.collect()
        with lock:
            peak[0] = max(peak[0], len(alive))
        handled.append(site["farm_name"])

    todo = [{"farm_name": f"t{i}"} for i in range(200)]
    stream_tiles(todo, fetch, handle, max_workers=4, max_in_flight=8, log=lambda m: None)
    assert sorted(handled) == sorted(s["farm_name"] for s in todo)        # every tile handled once
    assert peak[0] <= 8 + 1, f"{peak[0]} tiles held at once"


def test_streaming_survives_a_failed_download():
    from geo_anom.task1.pipeline import stream_tiles

    def fetch(site):
        if site["farm_name"] == "bad":
            raise IOError("read failed")
        return None if site["farm_name"] == "water" else ("img", {}, site)

    seen, logs = [], []
    stream_tiles([{"farm_name": n} for n in ["a", "bad", "water", "b"]], fetch,
                 lambda s, got: seen.append((s["farm_name"], got is None)), max_workers=2, log=logs.append)
    assert sorted(seen) == [("a", False), ("b", False), ("water", True)]
    assert any("FAILED bad" in m for m in logs)


def test_county_with_no_houses():
    """Calvert (2026-10-27): 239 tiles, 0 houses -> empty buildings.geojson without columns."""
    import geopandas as gpd
    from geo_anom.task1 import county as C
    empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    area = gpd.GeoDataFrame(geometry=[box(X0, Y0, X0 + 5000, Y0 + 5000)], crs="EPSG:32618")
    b = C.county_buildings(empty, area)
    assert len(b) == 0 and "near_permit" in b and int(b.near_permit.sum()) == 0


def test_stac_session_retries_gateway_timeouts():
    """Planetary Computer's search answered 504 for some St. Mary's tiles (2026-10-27)."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from geo_anom.task1.tiles import make_session

    calls = []

    class Flaky(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(1)
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            code = 504 if len(calls) <= 2 else 200
            body = b'{"features": []}' if code == 200 else b"gateway timeout"
            self.send_response(code); self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Flaky)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = make_session(retries=3, backoff=0.01).post(f"http://127.0.0.1:{srv.server_port}/search", json={}, timeout=5)
        assert r.status_code == 200 and len(calls) == 3       # two 504s, then success
    finally:
        srv.shutdown()


def test_county_complete_only_when_every_tile_is_accounted_for(tmp_path, monkeypatch):
    """A failed tile (e.g. a 504) must be retried even after the county was summarised."""
    import json as _json
    from geo_anom.task1 import county as C, region
    from geo_anom.task1.pipeline import NO_IMAGERY_DIR, shard_name

    grid = [{"grid_id": f"r000_c00{i}", "farm_name": f"T grid r000_c00{i}", "lat": 38, "lon": -76,
             "tile_path": f"data/raw/naip_grid/t/r000_c00{i}.tif"} for i in range(3)]
    monkeypatch.setattr(region, "county_boundary", lambda name: None)
    monkeypatch.setattr(region, "grid_sites", lambda area, name: grid)
    out = C.county_out("T", tmp_path)
    (out / "tiles_done").mkdir(parents=True)
    for f in ("run_meta.json", "county_summary.json"):
        (out / f).write_text("{}")
    (out / "tiles_done" / shard_name(grid[0])).write_text("{}")
    assert C.tile_status("T", tmp_path)["missing"] == ["r000_c001", "r000_c002"]
    assert not C.is_complete("T", tmp_path)                      # summarised, but 2 tiles missing
    (out / NO_IMAGERY_DIR).mkdir()
    (out / NO_IMAGERY_DIR / shard_name(grid[1])).write_text(_json.dumps({"site": grid[1]}))
    (out / "tiles_done" / shard_name(grid[2])).write_text("{}")
    assert C.is_complete("T", tmp_path)                          # 2 done + 1 known to have no photo
