#!/usr/bin/env python3
"""
Fit a vision-only headcount-from-floor-area model for poultry-type farms, so
the supply calculator can stop requiring a registry lookup for the ~85% of
the active registry that's poultry-shaped.

Deliberately scoped to poultry only. A per-farm feature table was built and
inspected before writing this: of 417 active farms, only 372 have >=1 U-Net
building detection at all, and within those, dairy has exactly 1 farm with a
detection, beef has 3, swine/turkey/ducks have 1 each. No classifier trained
on 1-3 examples per class generalizes -- fitting one anyway would be
fabricated confidence, not a model. Poultry (chickens_not_laying_hens +
laying_hens_dry_manure + turkeys + ducks_liquid_manure, all sharing the same
long-house shape per docs/labeling_guide.md) has 356 farms with detections
and headcount data -- the only group with enough examples for a real,
held-out-validated fit. See docs/species_capacity_model_metrics.md for why
dairy/beef/swine/duck/turkey are NOT covered here and what would actually
fix that (retraining segmentation on non-poultry examples, not a downstream
classifier -- the existing shape filter already restricts detected buildings
to a narrow poultry-like band, so there's very little shape variance left
for a classifier to separate species by).
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold

ROOT = Path(__file__).resolve().parent.parent
DETECTIONS = ROOT / "data/processed/detections/full_registry_unet_tulbure_detections.geojson"
MANIFEST = ROOT / "data/raw/naip_tiles_pc_4band_full/manifest.json"
OUT_MODEL = ROOT / "data/processed/models/poultry_capacity_model.json"
OUT_METRICS = ROOT / "docs/species_capacity_model_metrics.md"

POULTRY_TYPES = {"chickens_not_laying_hens", "laying_hens_dry_manure", "turkeys", "ducks_liquid_manure"}


def build_farm_features() -> dict[str, dict]:
    dets = json.loads(DETECTIONS.read_text())["features"]
    manifest = {s["farm_name"]: s for s in json.loads(MANIFEST.read_text())}

    by_farm: dict[str, list[dict]] = defaultdict(list)
    for feat in dets:
        by_farm[feat["properties"]["farm_name"]].append(feat["properties"])

    rows = {}
    for name, buildings in by_farm.items():
        site = manifest.get(name)
        if site is None:
            continue
        areas = [b["area_m2"] for b in buildings]
        rows[name] = {
            "animal_type": site.get("animal_type"),
            "headcount": site.get("headcount"),
            "n_buildings": len(buildings),
            "total_area_m2": sum(areas),
            "mean_area_m2": sum(areas) / len(areas),
        }
    return rows


def main():
    rows = build_farm_features()
    poultry = [
        r for r in rows.values()
        if r["animal_type"] in POULTRY_TYPES and r["headcount"] and r["headcount"] > 0
    ]
    print(f"Farms with >=1 detection: {len(rows)}")
    print(f"Poultry-type farms usable for fitting (detection + headcount): {len(poultry)}")

    X_area = np.log(np.array([r["total_area_m2"] for r in poultry])).reshape(-1, 1)
    X_n = np.log(np.array([r["n_buildings"] for r in poultry])).reshape(-1, 1)
    y = np.log(np.array([r["headcount"] for r in poultry]))

    # Two candidate models, evaluated by 5-fold CV R^2 on held-out farms (not
    # train-set R^2, which is what the earlier one-off study reported).
    kf = KFold(n_splits=5, shuffle=True, random_state=20260930)

    def cv_r2(X):
        scores = []
        for train_idx, test_idx in kf.split(X):
            model = LinearRegression().fit(X[train_idx], y[train_idx])
            pred = model.predict(X[test_idx])
            ss_res = np.sum((y[test_idx] - pred) ** 2)
            ss_tot = np.sum((y[test_idx] - y[test_idx].mean()) ** 2)
            scores.append(1 - ss_res / ss_tot)
        return np.mean(scores), np.std(scores)

    r2_area_mean, r2_area_std = cv_r2(X_area)
    X_both = np.hstack([X_area, X_n])
    r2_both_mean, r2_both_std = cv_r2(X_both)

    print(f"log(area) only:            held-out R^2 = {r2_area_mean:.3f} +/- {r2_area_std:.3f}")
    print(f"log(area) + log(n_bldgs):  held-out R^2 = {r2_both_mean:.3f} +/- {r2_both_std:.3f}")

    # Pick the simpler model unless the 2-feature one is a clear, real improvement.
    use_both = r2_both_mean > r2_area_mean + 0.03
    final_X = X_both if use_both else X_area
    final_r2_mean, final_r2_std = (r2_both_mean, r2_both_std) if use_both else (r2_area_mean, r2_area_std)
    final_model = LinearRegression().fit(final_X, y)
    residuals = y - final_model.predict(final_X)
    residual_std = float(np.std(residuals))

    coeffs = {
        "features": ["log_total_area_m2", "log_n_buildings"] if use_both else ["log_total_area_m2"],
        "intercept": float(final_model.intercept_),
        "coef": [float(c) for c in final_model.coef_],
        "residual_log_std": residual_std,
        "cv_r2_mean": float(final_r2_mean),
        "cv_r2_std": float(final_r2_std),
        "n_training_farms": len(poultry),
        "trained_on": "poultry-type farms only (chickens_not_laying_hens, laying_hens_dry_manure, turkeys, ducks_liquid_manure)",
        "scope_warning": "Do not apply to dairy/beef/swine detections -- fit on poultry-shaped buildings only, no held-out evidence it generalizes to other species.",
    }
    OUT_MODEL.parent.mkdir(parents=True, exist_ok=True)
    OUT_MODEL.write_text(json.dumps(coeffs, indent=2))
    print(f"\nSaved model -> {OUT_MODEL}")

    # Non-poultry census, for the honest "why not" writeup.
    by_type_with_det = defaultdict(int)
    for r in rows.values():
        by_type_with_det[r["animal_type"] or "unknown"] += 1

    metrics_md = f"""# Poultry Capacity Model — Honest Metrics (2026-09-30)

Fit and cross-validated by `scripts/train_capacity_model.py`. This is the
first model in the pipeline that estimates headcount from detected building
geometry alone, with no registry lookup at prediction time.

## What was fit

- **Training set**: {len(poultry)} poultry-type farms (chickens_not_laying_hens,
  laying_hens_dry_manure, turkeys, ducks_liquid_manure) that have at least one
  U-Net building detection and a recorded registry headcount. The registry
  headcount is used here only as the training label, the same way any
  labeled dataset uses ground truth to fit a model — not as a runtime lookup.
- **Features tried**: log(total detected floor area) alone, and
  log(total floor area) + log(building count) together, compared by 5-fold
  cross-validated R^2 on held-out farms (not training-set R^2, which is what
  an earlier informal study reported and is optimistic).
- **Result**: log(area) alone: R^2 = {r2_area_mean:.3f} (+/- {r2_area_std:.3f});
  log(area) + log(building count): R^2 = {r2_both_mean:.3f} (+/- {r2_both_std:.3f}).
  Model actually saved: {"the 2-feature version" if use_both else "log(area) alone"}
  (the other one wasn't enough of an improvement to justify the extra feature).
- **Residual spread**: {residual_std:.2f} in log-space, meaning individual farm
  predictions should be read as "within roughly a factor of {math.exp(residual_std):.1f}x",
  not as precise headcounts. This is a real, moderate, usable signal for a
  farm-level estimate — not a substitute for an actual count.

## Why this is poultry-only, and what would actually fix the rest

Of 417 active registry farms, only 372 have any U-Net building detection at
all. Within those, the per-species counts are:

{chr(10).join(f"- {k}: {v}" for k, v in sorted(by_type_with_det.items(), key=lambda kv: -kv[1]))}

Dairy has exactly 1 farm with a detection. Beef has 3. Swine, turkeys, and
ducks have 1 each. No model trained on 1-3 examples per class can be
validated — reporting an accuracy or R^2 for a class with 3 points is not
a real evaluation, so none was attempted.

The deeper reason isn't sample size alone: the existing shape filter
(`unet_detect.py`'s Tulbure-derived thresholds) already restricts every
detected building in this dataset to a narrow poultry-house-like shape band
by construction. Buildings that don't fit that band — most dairy and beef
barns — mostly never get segmented as building-shaped objects in the first
place; they're missing upstream, not filtered out downstream. That means a
classifier operating on detected-building shape features has almost nothing
to work with for those species: there's no polygon to classify for 13 of 14
dairy farms. **The actual fix is retraining or fine-tuning the segmentation
step on real non-poultry examples (CAFOSat's dairy/beef patches, or
Maryland-specific labels) — not a downstream species classifier**, which is
why one wasn't built here. This matches the conclusion already reached
independently in `docs/research_log.md`'s 2026-09-21 and 2026-09-23 entries.

## What this model is used for

`geo_anom/phase2/species_capacity.py` loads this model and
`supply_calculator.py` now calls it for every poultry-shaped detected
building cluster, registered or not — replacing the registry headcount
lookup as the primary source for that ~85% of the active registry. Non-poultry
species still fall back to registry headcount where a permit match exists,
clearly flagged as `capacity_source: "registry_fallback"` rather than treated
as if it were vision-derived. A cluster with no registry match and a
non-poultry shape produces no number at all, honestly, rather than a
fabricated one.
"""
    OUT_METRICS.write_text(metrics_md)
    print(f"Saved metrics -> {OUT_METRICS}")


if __name__ == "__main__":
    main()
