#!/usr/bin/env python3
"""
Zero-shot(ish) check: does AlphaEarth's 64-dim satellite embedding separate
this project's known-real lagoons from known-false-positive candidates via
simple cosine similarity to a small reference set -- no model training,
just the pretrained embedding plus a handful of reference points?

Reference/test split (to avoid testing on the same points used to build the
reference, unlike a naive "does it match itself" check):
- Reference ("afo") embedding = mean of 6 of the 7 visually-confirmed real
  lagoons.
- Test set = the 1 held-out real lagoon + the 4 CAFOSat-supported candidates
  + all 19 CAFOSat-contradicted (false-positive) candidates.

This exercises geo_anom/phase2/alphaearth_filter.py, which had two real bugs
fixed 2026-09-16 (see git log): the "year" property filter matched zero
images, and the band-name guess didn't match the real "A00".."A63" bands --
before today this module had never successfully extracted a real embedding.

Usage:
    python scripts/check_lagoons_alphaearth.py
"""
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo_anom.phase2.alphaearth_filter import AlphaEarthFilter

REAL_LAGOONS = [
    ("James Donald Dulin", -75.79036, 38.78674),
    ("Roland Todd/Roland's Roaster's", -75.84334, 38.68623),
    ("Jabar Rahim", -75.98935, 38.49513),
    ("Paul Aaron Hutchison Sr./Home Farm (1)", -76.01636, 38.80501),
    ("Paul Aaron Hutchison Sr./Home Farm (2)", -76.01759, 38.80470),
    ("Paul Aaron Hutchison Sr./Home Farm (3)", -76.01863, 38.80919),
    ("Hoa Tran/Morning Sun LLC", -75.53077, 38.29693),  # held out for test
]

CAFOSAT_SUPPORTED = [
    ("Todd Hite/Hite Farms, LLC (1)", -75.50605, 38.04383),
    ("Todd Hite/Hite Farms, LLC (2)", -75.50489, 38.05149),
    ("Tue D. Nguyen (1)", -75.50705, 38.04383),
    ("Tue D. Nguyen (2)", -75.50607, 38.05148),
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


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def main():
    f = AlphaEarthFilter()

    ref_points = REAL_LAGOONS[:6]
    held_out_real = REAL_LAGOONS[6:]

    print("Building reference embedding from 6 confirmed-real lagoons...")
    ref_embeddings = []
    for name, lon, lat in ref_points:
        emb = f.get_embedding(Point(lon, lat))
        if emb is not None:
            ref_embeddings.append(emb)
        else:
            print(f"  WARNING: no embedding for {name}")
    ref = np.mean(ref_embeddings, axis=0)
    print(f"  reference built from {len(ref_embeddings)}/{len(ref_points)} points\n")

    test_real = held_out_real + CAFOSAT_SUPPORTED
    test_fp = FALSE_POSITIVES

    def score_group(points):
        scores = []
        for name, lon, lat in points:
            emb = f.get_embedding(Point(lon, lat))
            if emb is None:
                print(f"  WARNING: no embedding for {name}")
                continue
            s = cosine(emb, ref)
            scores.append(s)
            print(f"    {name:55s} cosine_sim={s:.4f}")
        return scores

    print("=== Held-out real lagoons + CAFOSat-supported (should score HIGH) ===")
    real_scores = score_group(test_real)

    print("\n=== CAFOSat-contradicted false positives (should score LOW) ===")
    fp_scores = score_group(test_fp)

    print("\n=== Summary ===")
    print(f"Real/supported (n={len(real_scores)}): mean={np.mean(real_scores):.4f} "
          f"median={np.median(real_scores):.4f} min={np.min(real_scores):.4f} max={np.max(real_scores):.4f}")
    print(f"False positives (n={len(fp_scores)}): mean={np.mean(fp_scores):.4f} "
          f"median={np.median(fp_scores):.4f} min={np.min(fp_scores):.4f} max={np.max(fp_scores):.4f}")

    print("\n=== Threshold sweep ===")
    for thresh in [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]:
        tp = sum(1 for s in real_scores if s >= thresh)
        fn = sum(1 for s in real_scores if s < thresh)
        fp = sum(1 for s in fp_scores if s >= thresh)
        tn = sum(1 for s in fp_scores if s < thresh)
        prec = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
        recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
        print(f"  threshold={thresh:.2f}  TP={tp} FN={fn} FP={fp} TN={tn}  precision={prec:.2f}  recall={recall:.2f}")


if __name__ == "__main__":
    main()
