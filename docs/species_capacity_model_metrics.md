# Poultry Capacity Model — Honest Metrics (2026-09-30)

Fit and cross-validated by `scripts/train_capacity_model.py`. This is the
first model in the pipeline that estimates headcount from detected building
geometry alone, with no registry lookup at prediction time.

## What was fit

- **Training set**: 357 poultry-type farms (chickens_not_laying_hens,
  laying_hens_dry_manure, turkeys, ducks_liquid_manure) that have at least one
  U-Net building detection and a recorded registry headcount. The registry
  headcount is used here only as the training label, the same way any
  labeled dataset uses ground truth to fit a model — not as a runtime lookup.
- **Features tried**: log(total detected floor area) alone, and
  log(total floor area) + log(building count) together, compared by 5-fold
  cross-validated R^2 on held-out farms (not training-set R^2, which is what
  an earlier informal study reported and is optimistic).
- **Result**: log(area) alone: R^2 = 0.231 (+/- 0.105);
  log(area) + log(building count): R^2 = 0.232 (+/- 0.112).
  Model actually saved: log(area) alone
  (the other one wasn't enough of an improvement to justify the extra feature).
- **Residual spread**: 0.54 in log-space, meaning individual farm
  predictions should be read as "within roughly a factor of 1.7x",
  not as precise headcounts. This is a real, moderate, usable signal for a
  farm-level estimate — not a substitute for an actual count.

## Why this is poultry-only, and what would actually fix the rest

Of 417 active registry farms, only 372 have any U-Net building detection at
all. Within those, the per-species counts are:

- chickens_not_laying_hens: 352
- unknown: 9
- cattle_includes_heifers: 3
- laying_hens_dry_manure: 3
- swine_55_lbs: 1
- dairy_cattle: 1
- ducks_liquid_manure: 1
- turkeys: 1
- horses: 1

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
