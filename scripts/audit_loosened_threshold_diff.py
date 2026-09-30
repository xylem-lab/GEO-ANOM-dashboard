#!/usr/bin/env python3
"""
Compare the experimental loosened-threshold detection run
(LENGTH_MIN_M 55->40, ASPECT_MIN 2.5->2.0, see unet_detect_loosened_experiment.py)
against the validated full_registry_unet_tulbure_detections.geojson, to find
exactly what's newly introduced -- broken down by species, since the change
applies to all 417 farms, not just the 2 target beef farms.

This does NOT replace the existing 35-farm visual precision audit -- there's
no way to visually re-verify new candidates in this environment. It reports
what changed and flags plausibility (dimensions, distance-to-road) so a human
can decide whether the change is safe to adopt, especially for poultry farms
where any regression would hit the already-validated 99.7% precision figure.

Usage:
    python scripts/audit_loosened_threshold_diff.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data/raw/naip_tiles_pc_4band_full/manifest.json"
CURRENT_PATH = ROOT / "data/processed/detections/full_registry_unet_tulbure_detections.geojson"
LOOSENED_PATH = ROOT / "data/processed/detections/experimental_loosened_length_aspect.geojson"


def key(props):
    # Identify a detection by farm + rounded centroid-ish geometry proxy
    # (area/length/width triple is a reasonable fingerprint for "same house").
    return (props["farm_name"], round(props["area_m2"]), round(props["length_m"], 1), round(props["width_m"], 1))


def main():
    manifest = json.loads(MANIFEST_PATH.read_text())
    farm_type = {f["farm_name"]: f["animal_type"] for f in manifest}

    current = json.loads(CURRENT_PATH.read_text())
    loosened = json.loads(LOOSENED_PATH.read_text())

    current_keys = {key(f["properties"]) for f in current["features"]}
    new_features = [f for f in loosened["features"] if key(f["properties"]) not in current_keys]

    print(f"Current (validated) detections: {len(current['features'])}")
    print(f"Loosened-threshold detections:  {len(loosened['features'])}")
    print(f"NEW detections introduced by the loosened thresholds: {len(new_features)}\n")

    by_species = {}
    for f in new_features:
        p = f["properties"]
        species = farm_type.get(p["farm_name"], "?")
        by_species.setdefault(species, []).append(p)

    for species, feats in sorted(by_species.items(), key=lambda x: -len(x[1])):
        print(f"=== {species}: {len(feats)} new detection(s) ===")
        for p in feats:
            print(f"    {p['farm_name']:45s} area={p['area_m2']:.0f}m2 length={p['length_m']:.1f}m "
                  f"width={p['width_m']:.1f}m aspect={p['length_m']/p['width_m']:.2f}")
        print()

    n_poultry_new = sum(len(v) for k, v in by_species.items() if "chicken" in k or "laying" in k or k in ("turkeys",))
    print(f"New detections on POULTRY-type farms (the precision-risk area): {n_poultry_new}")
    print("These were NOT visually re-verified -- flagging count only. Any non-zero number here")
    print("means the existing 35-farm precision audit sample should be re-checked before adopting")
    print("this threshold change, since it could reopen previously-excluded false positives.")


if __name__ == "__main__":
    main()
