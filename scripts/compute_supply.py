#!/usr/bin/env python3
"""
N / P2O5 supply from a map_buildings.py run.

    python3 scripts/compute_supply.py data/processed/task1/run_2026-10-05

Writes into the same run directory:
    supply_by_farm.csv          one row per registry farm (incl. farms with
                                no detected building, flagged)
    supply_by_building.geojson  each farm's total split by floor-area share
    supply_by_species.csv       statewide totals per species group

See geo_anom/task1/supply.py for the formulas and their limits. Totals are
printed next to the AWTF 2023 report's statewide figure -- read that line
before using any number.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo_anom.task1 import tiles  # noqa: E402
from geo_anom.task1.supply import AWTF_BENCHMARKS, building_supply, farm_supply, species_totals  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path, help="Output directory of scripts/map_buildings.py")
    ap.add_argument("--sites", type=Path, default=None,
                    help="Registry sites to compute supply for (default: the run's sites.json)")
    args = ap.parse_args()

    manifest = tiles.load_manifest(args.sites or args.run_dir / "sites.json")
    buildings = gpd.read_file(args.run_dir / "buildings.geojson")
    if "assigned_farm" not in buildings:
        sys.exit("buildings.geojson has no assigned_farm -- rerun map_buildings.py without --no-dedupe")

    farms = farm_supply(manifest, buildings)
    farms.to_csv(args.run_dir / "supply_by_farm.csv", index=False)
    building_supply(buildings, farms).to_file(args.run_dir / "supply_by_building.geojson", driver="GeoJSON")
    totals = species_totals(farms)
    totals.to_csv(args.run_dir / "supply_by_species.csv")

    print(totals.to_string(float_format=lambda x: f"{x:,.0f}" if abs(x) >= 1 else f"{x:.3f}"))
    located = farms["located_by"].eq("detected_buildings")
    print(f"\nN located on detected buildings: {farms.loc[located, 'annual_N_lbs'].sum():,.0f} lbs/yr "
          f"({located.sum()}/{len(farms)} farms); at registry point only: "
          f"{farms.loc[~located, 'annual_N_lbs'].sum():,.0f} lbs/yr")
    if farms["no_coefficient"].any():
        print("No coefficient (zero supply): " +
              ", ".join(sorted(farms.loc[farms['no_coefficient'], 'animal_type'].astype(str).unique())))
    if "broiler" in totals.index and len(farms) >= 400:
        ours = totals.loc["broiler", "annual_N_lbs"]
        ref = AWTF_BENCHMARKS["broiler_N_lbs_2019"]
        print(f"\nCHECK broiler N: {ours:,.0f} lbs/yr here vs {ref:,.0f} in AWTF 2023 report (2019) "
              f"-> ratio {ours / ref:.1f}x")
    elif "broiler" in totals.index:
        print(f"\n(Partial run, {len(farms)} farms: no statewide comparison against AWTF.)")


if __name__ == "__main__":
    main()
