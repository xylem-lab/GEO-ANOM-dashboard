#!/usr/bin/env python3
"""
Train a real classifier (logistic regression, not a mean-similarity baseline)
on AlphaEarth embeddings of CAFOSat's manure-pond presence labels, and
evaluate it both on CAFOSat's own held-out split and on this project's known
real/false-positive lagoon set.

Why this and not the naive mean-embedding cosine check from 2026-09-16
(see docs/dynamicworld_alphaearth_lagoon_check_result.md): that check used
only 6 reference points and a single mean vector. This trains on ~1400
non-augmented, group-split (by CAFO_UNIQUE_ID, to avoid same-farm leakage
between train/test) CAFOSat points nationally -- a real, if still modest,
supervised classifier.

Negative class definition: farms that DON'T have a manure pond (CAFOSat rows
with manure_pond==0 and a real CAFO_UNIQUE_ID), not generic non-farm land --
this matches the actual application (distinguishing candidate detections at
farms that do vs. don't have a real lagoon), which is a harder and more
relevant negative than "farm vs. empty field."

Usage:
    python scripts/train_alphaearth_lagoon_classifier.py
"""
import sys
from pathlib import Path

import ee
import numpy as np
import pandas as pd
from pyproj import Transformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ID = "prime-keel-328306"
HFCSV = str(
    Path.home()
    / ".cache/huggingface/hub/datasets--oishee3003--CAFOSat/snapshots/"
    "152f4c5885c16dd63eddf295a461890d3c761343/CAFOSat.csv"
)
RNG = np.random.RandomState(42)
N_TRAIN_PER_CLASS = 700
N_TEST_PER_CLASS = 150
BATCH_SIZE = 500  # points per sampleRegions() call
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "alphaearth_cafosat_embeddings_cache.npz"


def to_lonlat(row):
    """Reproject a CAFOSat row's (refined_x, refined_y) from its own
    patch_crs (varies by state -- multiple UTM zones) to WGS84 lon/lat."""
    transformer = Transformer.from_crs(row["patch_crs"], "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(row["refined_x"], row["refined_y"])
    return lon, lat


def build_point_sets():
    df = pd.read_csv(HFCSV)
    non_aug = df[df["image_type"] != "augmented"].copy()

    positives = non_aug[(non_aug["manure_pond"] > 0) & non_aug["CAFO_UNIQUE_ID"].notna()]
    hard_negatives = non_aug[(non_aug["manure_pond"] == 0) & non_aug["CAFO_UNIQUE_ID"].notna()]

    pos_groups = positives["CAFO_UNIQUE_ID"].unique()
    neg_groups = hard_negatives["CAFO_UNIQUE_ID"].unique()
    RNG.shuffle(pos_groups)
    RNG.shuffle(neg_groups)

    n_pos_test_groups = max(1, int(0.2 * len(pos_groups)))
    n_neg_test_groups = max(1, int(0.2 * len(neg_groups)))
    pos_test_groups = set(pos_groups[:n_pos_test_groups])
    pos_train_groups = set(pos_groups[n_pos_test_groups:])
    neg_test_groups = set(neg_groups[:n_neg_test_groups])
    neg_train_groups = set(neg_groups[n_neg_test_groups:])

    def sample_from_groups(df_subset, groups, n):
        sub = df_subset[df_subset["CAFO_UNIQUE_ID"].isin(groups)]
        # one row per group first (avoid over-representing multi-patch farms),
        # then top up randomly if we still need more
        one_per_group = sub.groupby("CAFO_UNIQUE_ID").sample(n=1, random_state=42)
        if len(one_per_group) >= n:
            return one_per_group.sample(n=n, random_state=42)
        extra_needed = n - len(one_per_group)
        remaining = sub.drop(one_per_group.index)
        extra = remaining.sample(n=min(extra_needed, len(remaining)), random_state=42) if len(remaining) else remaining
        return pd.concat([one_per_group, extra])

    pos_train = sample_from_groups(positives, pos_train_groups, N_TRAIN_PER_CLASS)
    pos_test = sample_from_groups(positives, pos_test_groups, N_TEST_PER_CLASS)
    neg_train = sample_from_groups(hard_negatives, neg_train_groups, N_TRAIN_PER_CLASS)
    neg_test = sample_from_groups(hard_negatives, neg_test_groups, N_TEST_PER_CLASS)

    print(f"train: {len(pos_train)} positive, {len(neg_train)} negative")
    print(f"test:  {len(pos_test)} positive, {len(neg_test)} negative")

    return pos_train, pos_test, neg_train, neg_test


def fetch_embeddings(df_points, ae_image):
    """Batch-fetch AlphaEarth embeddings for a set of CAFOSat rows via
    Image.sampleRegions() -- one/few EE round trips instead of one per point."""
    lonlats = [to_lonlat(row) for _, row in df_points.iterrows()]
    ids = list(range(len(lonlats)))

    all_embeddings = {}
    for start in range(0, len(lonlats), BATCH_SIZE):
        batch = lonlats[start:start + BATCH_SIZE]
        batch_ids = ids[start:start + BATCH_SIZE]
        feats = [
            ee.Feature(ee.Geometry.Point([lon, lat]), {"pid": pid})
            for (lon, lat), pid in zip(batch, batch_ids)
        ]
        fc = ee.FeatureCollection(feats)
        sampled = ae_image.sampleRegions(collection=fc, scale=10, geometries=False)
        info = sampled.getInfo()
        for feat in info["features"]:
            props = feat["properties"]
            pid = props["pid"]
            emb = np.array([props.get(f"A{i:02d}", np.nan) for i in range(64)], dtype=np.float32)
            all_embeddings[pid] = emb
        print(f"  fetched batch {start}-{start+len(batch)} ({len(info['features'])} returned)")

    ordered = [all_embeddings.get(i) for i in ids]
    return ordered


def main():
    ee.Initialize(project=PROJECT_ID)
    ae_image = (
        ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
        .filterDate("2024-01-01", "2025-01-01")
        .mosaic()
    )

    pos_train, pos_test, neg_train, neg_test = build_point_sets()

    if CACHE_PATH.exists():
        print(f"\nLoading cached embeddings from {CACHE_PATH}")
        cache = np.load(CACHE_PATH, allow_pickle=True)
        pos_train_emb, neg_train_emb = list(cache["pos_train"]), list(cache["neg_train"])
        pos_test_emb, neg_test_emb = list(cache["pos_test"]), list(cache["neg_test"])
    else:
        print("\nFetching training embeddings...")
        pos_train_emb = fetch_embeddings(pos_train, ae_image)
        neg_train_emb = fetch_embeddings(neg_train, ae_image)
        print("Fetching CAFOSat test embeddings...")
        pos_test_emb = fetch_embeddings(pos_test, ae_image)
        neg_test_emb = fetch_embeddings(neg_test, ae_image)
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            CACHE_PATH,
            pos_train=np.array(pos_train_emb, dtype=object),
            neg_train=np.array(neg_train_emb, dtype=object),
            pos_test=np.array(pos_test_emb, dtype=object),
            neg_test=np.array(neg_test_emb, dtype=object),
        )
        print(f"Cached embeddings to {CACHE_PATH}")

    def drop_none(embs, label):
        out = [(e, label) for e in embs if e is not None and not np.isnan(e).any()]
        return out

    train_pairs = drop_none(pos_train_emb, 1) + drop_none(neg_train_emb, 0)
    test_pairs = drop_none(pos_test_emb, 1) + drop_none(neg_test_emb, 0)

    X_train = np.array([p[0] for p in train_pairs])
    y_train = np.array([p[1] for p in train_pairs])
    X_test = np.array([p[0] for p in test_pairs])
    y_test = np.array([p[1] for p in test_pairs])

    print(f"\nTrain set: {len(X_train)} points ({y_train.sum()} positive)")
    print(f"CAFOSat test set: {len(X_test)} points ({y_test.sum()} positive)")

    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)

    clf = LogisticRegression(max_iter=2000, class_weight="balanced")
    clf.fit(X_train_s, y_train)

    y_pred = clf.predict(X_test_s)
    y_proba = clf.predict_proba(X_test_s)[:, 1]

    print("\n=== CAFOSat held-out test set (same distribution as training) ===")
    print(f"Precision: {precision_score(y_test, y_pred):.3f}")
    print(f"Recall:    {recall_score(y_test, y_pred):.3f}")
    print(f"F1:        {f1_score(y_test, y_pred):.3f}")
    print(f"ROC-AUC:   {roc_auc_score(y_test, y_proba):.3f}")

    # --- Now the real target: this project's own known real/FP lagoon set ---
    print("\n=== This project's own known lagoons (the actual target task) ===")
    from shapely.geometry import Point
    from geo_anom.phase2.alphaearth_filter import AlphaEarthFilter

    REAL_LAGOONS = [
        ("James Donald Dulin", -75.79036, 38.78674),
        ("Roland Todd/Roland's Roaster's", -75.84334, 38.68623),
        ("Jabar Rahim", -75.98935, 38.49513),
        ("Paul Aaron Hutchison Sr./Home Farm (1)", -76.01636, 38.80501),
        ("Paul Aaron Hutchison Sr./Home Farm (2)", -76.01759, 38.80470),
        ("Paul Aaron Hutchison Sr./Home Farm (3)", -76.01863, 38.80919),
        ("Hoa Tran/Morning Sun LLC", -75.53077, 38.29693),
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

    f = AlphaEarthFilter()
    real_scores, fp_scores = [], []
    for name, lon, lat in REAL_LAGOONS:
        emb = f.get_embedding(Point(lon, lat))
        if emb is None:
            print(f"  WARNING: no embedding for {name}")
            continue
        proba = clf.predict_proba(scaler.transform(emb.reshape(1, -1)))[0, 1]
        real_scores.append(proba)
        print(f"    REAL  {name:50s} p(pond)={proba:.3f}")

    for name, lon, lat in FALSE_POSITIVES:
        emb = f.get_embedding(Point(lon, lat))
        if emb is None:
            print(f"  WARNING: no embedding for {name}")
            continue
        proba = clf.predict_proba(scaler.transform(emb.reshape(1, -1)))[0, 1]
        fp_scores.append(proba)
        print(f"    FP    {name:50s} p(pond)={proba:.3f}")

    real_scores = np.array(real_scores)
    fp_scores = np.array(fp_scores)
    print(f"\nReal lagoons (n={len(real_scores)}):      mean p(pond)={real_scores.mean():.3f}  "
          f"median={np.median(real_scores):.3f}  min={real_scores.min():.3f}  max={real_scores.max():.3f}")
    print(f"False positives (n={len(fp_scores)}): mean p(pond)={fp_scores.mean():.3f}  "
          f"median={np.median(fp_scores):.3f}  min={fp_scores.min():.3f}  max={fp_scores.max():.3f}")

    print("\n=== Threshold sweep on our own known lagoons ===")
    for thresh in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        tp = (real_scores >= thresh).sum()
        fn = (real_scores < thresh).sum()
        fp = (fp_scores >= thresh).sum()
        tn = (fp_scores < thresh).sum()
        prec = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
        rec = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
        print(f"  threshold={thresh:.1f}  TP={tp} FN={fn} FP={fp} TN={tn}  precision={prec:.2f}  recall={rec:.2f}")


if __name__ == "__main__":
    main()
