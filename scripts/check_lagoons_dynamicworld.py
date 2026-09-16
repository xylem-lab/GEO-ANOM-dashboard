#!/usr/bin/env python3
"""
Zero-shot check: does Google Dynamic World's pretrained "water" probability
band separate this project's known-real lagoons from known-false-positive
lagoon candidates, with no training of our own?

Test set (built from prior audits, not this script):
- 7 farms with a visually-confirmed real lagoon (full_registry_sam_lagoon_detections.geojson)
- 4 candidates (2 farms) CAFOSat-supported (independently confirmed real, 2026-09-15 run)
- 31 candidates CAFOSat-contradicted (independently confirmed false positive)

Dynamic World is 10m resolution (Sentinel-2) vs. NAIP's 0.6-1m -- the point of
this check is to find out whether that's too coarse to be useful here, not to
assume either way.

Usage:
    python scripts/check_lagoons_dynamicworld.py
"""
import ee
import numpy as np

PROJECT_ID = "prime-keel-328306"

REAL_LAGOONS = [
    ("James Donald Dulin", -75.79036, 38.78674),
    ("Roland Todd/Roland's Roaster's", -75.84334, 38.68623),
    ("Jabar Rahim", -75.98935, 38.49513),
    ("Paul Aaron Hutchison Sr./Home Farm (1)", -76.01636, 38.80501),
    ("Paul Aaron Hutchison Sr./Home Farm (2)", -76.01759, 38.80470),
    ("Paul Aaron Hutchison Sr./Home Farm (3)", -76.01863, 38.80919),
    ("Hoa Tran/Morning Sun LLC", -75.53077, 38.29693),
    ("Todd Hite/Hite Farms, LLC (1) [CAFOSat-supported]", -75.50605, 38.04383),
    ("Todd Hite/Hite Farms, LLC (2) [CAFOSat-supported]", -75.50489, 38.05149),
    ("Tue D. Nguyen (1) [CAFOSat-supported]", -75.50705, 38.04383),
    ("Tue D. Nguyen (2) [CAFOSat-supported]", -75.50607, 38.05148),
]

FALSE_POSITIVES = [
    ("Dan Heller/Stillwater Ventures, LLC", -75.95702, 39.09879),
    ("Nathan Wolf/Wolf Farm (1)", -75.77026, 38.61228),
    ("Nathan Wolf/Wolf Farm (2)", -75.76953, 38.61269),
    ("Nathan Wolf/Wolf Farm (3)", -75.77017, 38.61288),
    ("Yang Hyuk Lim/Holly Way Farm", -75.85328, 38.91994),
    ("S.H.L. Anderson Inc.", -75.80630, 38.19611),
    ("David Tribbett, Jr./River Road Farm", -75.86316, 38.95197),
    ("Mohammad Arshad (1)", -75.38618, 38.45759),
    ("Mohammad Arshad (2)", -75.39604, 38.45983),
    ("Van Bawi Thawng/Mt. Moriah Farm (1)", -75.52653, 38.01830),
    ("Van Bawi Thawng/Mt. Moriah Farm (2)", -75.52683, 38.01836),
    ("Sunny Apartments, LLC (Mohammed Ahmad)", -75.78624, 38.56800),
    ("Randy Collins/Home Farm", -75.80228, 38.67647),
    ("William Moore, III (1)", -75.86488, 38.94726),
    ("William Moore, III (2)", -75.86440, 38.94729),
    ("Deerspring Dairy Farm, LLC", -77.51369, 39.41037),
    ("Phat H. Nguyen", -75.52683, 38.01836),
    ("Keith/Aydelotte/Silver Bullet Farm, LLC (1)", -75.51108, 38.03601),
    ("Keith/Aydelotte/Silver Bullet Farm, LLC (2)", -75.50139, 38.04239),
]


def water_prob(dw_composite, lon, lat):
    pt = ee.Geometry.Point([lon, lat])
    try:
        val = dw_composite.sample(region=pt, scale=10, numPixels=1).first().get("water").getInfo()
        return val
    except Exception as e:
        return None


def main():
    ee.Initialize(project=PROJECT_ID)

    # Median composite of the most recent 12 months of Dynamic World over
    # the Delmarva bounding box, band "water" = per-pixel water probability.
    delmarva = ee.Geometry.BBox(-77.7, 37.9, -75.0, 39.8)
    dw = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterBounds(delmarva)
        .filterDate("2024-01-01", "2025-01-01")
        .select("water")
        .median()
    )

    print(f"{'label':60s} {'lon':>10s} {'lat':>9s} {'water_prob':>10s}")
    print("-" * 92)

    real_scores, fp_scores = [], []
    for name, lon, lat in REAL_LAGOONS:
        p = water_prob(dw, lon, lat)
        real_scores.append(p)
        print(f"{name:60s} {lon:10.5f} {lat:9.5f} {str(p):>10s}")

    print()
    for name, lon, lat in FALSE_POSITIVES:
        p = water_prob(dw, lon, lat)
        fp_scores.append(p)
        print(f"{name:60s} {lon:10.5f} {lat:9.5f} {str(p):>10s}")

    real_valid = [s for s in real_scores if s is not None]
    fp_valid = [s for s in fp_scores if s is not None]

    print("\n=== Summary ===")
    print(f"Real lagoons:      n={len(real_valid)}  mean water_prob={np.mean(real_valid):.3f}  "
          f"median={np.median(real_valid):.3f}  min={np.min(real_valid):.3f}  max={np.max(real_valid):.3f}")
    print(f"False positives:   n={len(fp_valid)}  mean water_prob={np.mean(fp_valid):.3f}  "
          f"median={np.median(fp_valid):.3f}  min={np.min(fp_valid):.3f}  max={np.max(fp_valid):.3f}")

    # Simple threshold sweep to see if ANY threshold separates the two groups
    print("\n=== Threshold sweep (does any cut separate real from false-positive?) ===")
    for thresh in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        tp = sum(1 for s in real_valid if s >= thresh)
        fn = sum(1 for s in real_valid if s < thresh)
        fp = sum(1 for s in fp_valid if s >= thresh)
        tn = sum(1 for s in fp_valid if s < thresh)
        prec = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
        recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
        print(f"  threshold={thresh:.1f}  TP={tp} FN={fn} FP={fp} TN={tn}  precision={prec:.2f}  recall={recall:.2f}")


if __name__ == "__main__":
    main()
