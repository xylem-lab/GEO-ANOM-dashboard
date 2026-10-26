"""Tests for geo_anom.task2 (the poultry -> corn loop), without network access."""

from __future__ import annotations

import copy

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import box

from geo_anom.task2 import balance as B
from geo_anom.task2 import cdl

CELL = 5000.0
X0, Y0 = 440_000, 4_250_000      # UTM 18N, Eastern Shore


def houses(*cells_and_sizes):
    """One 120 x 15 m house per entry, placed inside the given cell."""
    geoms = []
    for (ix, iy) in cells_and_sizes:
        x, y = ix * CELL + 100, iy * CELL + 100
        geoms.append(box(x, y, x + 120, y + 15))
    return gpd.GeoDataFrame(geometry=geoms, crs=B.UTM)


def test_houses_binned_by_absolute_cell():
    i, j = int(X0 // CELL), int(Y0 // CELL)
    h = B.houses_on_grid(houses((i, j), (i, j), (i + 1, j)), CELL)
    assert h.loc[(i, j), "houses"] == 2 and h.loc[(i + 1, j), "houses"] == 1
    assert h.loc[(i, j), "roof_m2"] == pytest.approx(2 * 120 * 15)


def test_grid_keeps_cells_with_either_houses_or_crop():
    i, j = int(X0 // CELL), int(Y0 // CELL)
    h = B.houses_on_grid(houses((i, j)), CELL)
    g = B.build_grid(h, {"corn": {(i, j): 100.0, (i + 3, j): 400.0}}, CELL)
    assert len(g) == 2
    row = g.set_index("cell_id").loc[f"{i + 3}_{j}"]
    assert row.houses == 0 and row.corn_acres == 400.0
    assert g.geometry.iloc[0].area == pytest.approx(CELL ** 2)


def test_within_radius_sums_neighbours_only():
    i, j = 0, 0
    h = B.houses_on_grid(houses((i, j)), CELL)
    crops = {"corn": {(i + 1, j): 10.0, (i + 2, j): 20.0, (i + 6, j): 1000.0}}
    g = B.add_within(B.build_grid(h, crops, CELL), ["corn_acres"], 12_000, CELL).set_index("cell_id")
    assert g.loc["0_0", "corn_acres_12km"] == pytest.approx(30.0)     # 5 and 10 km away, not 30 km
    assert g.loc["6_0", "corn_acres_12km"] == pytest.approx(1000.0)


def test_roof_per_acre_edges():
    r = B.roof_per_acre([100, 50, 0], [10, 0, 0])
    assert r[0] == 10 and np.isinf(r[1]) and np.isnan(r[2])


def test_nutrient_balance_refuses_until_coefficients_set():
    g = B.build_grid(B.houses_on_grid(houses((0, 0)), CELL), {"corn": {(0, 0): 100.0}}, CELL)
    with pytest.raises(ValueError, match="birds_per_m2"):
        B.nutrient_balance(g, B.COEFFICIENTS)
    c = copy.deepcopy(B.COEFFICIENTS)
    for k, v in {"detection_recall": 0.5, "birds_per_m2": 10, "flocks_per_year": 5, "litter_N_lb_per_bird_flock": 0.1,
                 "litter_N_available": 0.5, "litter_P2O5_lb_per_bird_flock": 0.1, "corn_N_lb_per_acre": 150,
                 "corn_P2O5_lb_per_acre": 60}.items():
        c[k]["value"] = v
    out = B.nutrient_balance(g, c).iloc[0]
    birds = 1800 / 0.5 * 10
    assert out.N_supply_lb == pytest.approx(birds * 5 * 0.1 * 0.5)
    assert out.N_balance_lb == pytest.approx(birds * 5 * 0.1 * 0.5 - 100 * 150)
    assert B.COEFFICIENTS["birds_per_m2"]["value"] is None          # the template itself is untouched


def test_crop_acres_on_grid_from_a_small_raster(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    a = np.zeros((10, 10), dtype=np.uint8)
    a[:5, :] = 1          # 50 corn pixels
    a[5:, :2] = 5         # 20 soybean pixels
    p = tmp_path / "cdl.tif"
    with rasterio.open(p, "w", driver="GTiff", width=10, height=10, count=1, dtype="uint8",
                       crs=B.UTM, transform=from_origin(X0 + 1000, Y0 + 1000, 30, 30)) as dst:
        dst.write(a, 1)
    d = cdl.crop_acres_on_grid(p, cdl.CROP_GROUPS["corn"], CELL)
    assert list(d) == [(int(X0 // CELL), int(Y0 // CELL))]
    assert sum(d.values()) == pytest.approx(50 * cdl.PIXEL_ACRES)


def test_implied_stocking():
    assert B.implied_birds_per_m2(1000, 50, 0.5) == pytest.approx(10)
