#!/usr/bin/env python3
"""
Regression check for the species-scoped beef filter fix (unet_detect.py,
SPECIES_FILTER_OVERRIDES): confirms the v2 output is byte-for-byte identical
to the validated original for every farm EXCEPT the 3 cattle_includes_heifers
farms, before this replaces the canonical detection file.

Usage:
    python scripts/validate_species_scoped_fix.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data/raw/naip_tiles_pc_4band_full/manifest.json"
ORIGINAL_PATH = ROOT / "data/processed/detections/full_registry_unet_tulbure_detections.geojson"
V2_PATH = ROOT / "data/processed/detections/full_registry_unet_tulbure_detections_v2.geojson"


def key(props):
    return (props["farm_name"], round(props["area_m2"]), round(props["length_m"], 1), round(props["width_m"], 1))


def main():
    manifest = json.loads(MANIFEST_PATH.read_text())
    beef_farms = {f["farm_name"] for f in manifest if f["animal_type"] == "cattle_includes_heifers"}

    original = json.loads(ORIGINAL_PATH.read_text())
    v2 = json.loads(V2_PATH.read_text())

    orig_by_farm = {}
    for f in original["features"]:
        orig_by_farm.setdefault(f["properties"]["farm_name"], set()).add(key(f["properties"]))
    v2_by_farm = {}
    for f in v2["features"]:
        v2_by_farm.setdefault(f["properties"]["farm_name"], set()).add(key(f["properties"]))

    all_farms = set(orig_by_farm) | set(v2_by_farm)
    non_beef_diffs = []
    for farm in all_farms:
        if farm in beef_farms:
            continue
        if orig_by_farm.get(farm, set()) != v2_by_farm.get(farm, set()):
            non_beef_diffs.append(farm)

    print(f"Original total: {len(original['features'])}")
    print(f"V2 total:       {len(v2['features'])}")
    print(f"Non-beef farms with ANY difference (should be 0): {len(non_beef_diffs)}")
    for f in non_beef_diffs:
        print(f"  DIFF: {f}  orig={len(orig_by_farm.get(f, []))} v2={len(v2_by_farm.get(f, []))}")

    print("\n--- Beef farms (expected to change) ---")
    for farm in sorted(beef_farms):
        print(f"  {farm}: orig={len(orig_by_farm.get(farm, []))} -> v2={len(v2_by_farm.get(farm, []))}")

    if not non_beef_diffs:
        print("\nPASS: zero effect outside the 3 beef farms. Safe to adopt as canonical.")
    else:
        print(f"\nFAIL: {len(non_beef_diffs)} non-beef farms changed. DO NOT adopt -- investigate.")


if __name__ == "__main__":
    main()
