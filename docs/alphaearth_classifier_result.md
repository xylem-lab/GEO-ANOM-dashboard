# AlphaEarth logistic-regression classifier for lagoon presence (2026-09-16)

A real supervised classifier (logistic regression on 64-dim AlphaEarth
embeddings), trained on CAFOSat's national presence-labeled patches, going
one step further than the naive 6-point mean-similarity check from earlier
today (`docs/dynamicworld_alphaearth_lagoon_check_result.md`).

## Training setup

- **Positive class**: CAFOSat rows with `manure_pond > 0`, non-augmented,
  with a real `CAFO_UNIQUE_ID` (867 unique farms nationally).
- **Negative class**: CAFOSat rows with `manure_pond == 0` at a real farm
  (not generic non-farm land) — the harder, more relevant negative, since
  the actual application is "does this farm have a pond," not "is this a
  farm at all."
- **Split**: grouped by `CAFO_UNIQUE_ID` (not row) so no farm's patches
  appear in both train and test — avoids leakage from multiple crops/patches
  of the same site.
- 700 positive + 700 negative points for training, 150+150 held out from
  CAFOSat's own distribution for a first sanity check.
- Embeddings fetched via `Image.sampleRegions()` in batches (not one EE call
  per point) — ~1,700 points in a handful of round trips, laptop-feasible.
- Script: `scripts/train_alphaearth_lagoon_classifier.py`. Fetched
  embeddings are cached to `data/processed/alphaearth_cafosat_embeddings_cache.npz`
  (gitignored — regenerate by deleting the cache, don't commit it).

## Result 1: works well on CAFOSat's own distribution

| Metric | Value |
|---|---|
| Precision | 0.791 |
| Recall | 0.833 |
| F1 | 0.812 |
| ROC-AUC | 0.837 |

A real, usable classifier for "does this CAFOSat-style patch contain a
manure pond" — a meaningfully better result than the naive mean-similarity
check, and evidence AlphaEarth embeddings do carry real signal for this
question in general.

## Result 2: does NOT transfer to this project's own false positives

Evaluated the same classifier against this project's known real lagoons
(11: 7 visually-confirmed + 4 CAFOSat-supported) and known false positives
(19 CAFOSat-contradicted, from the classical-CV+SAM candidate pipeline):

- Real lagoons: mean p(pond) = 0.715 (range 0.386-0.968)
- False positives: mean p(pond) = 0.724 (range 0.287-0.964)

**Essentially no separation** — the false-positive mean is actually
slightly *higher* than the real-lagoon mean. Best threshold (0.3) gets
100% recall but only 38% precision, barely above the test set's 37% base
rate of real examples (11/30) — close to no better than guessing.

## Why the gap between Result 1 and Result 2 — a real, explainable finding

CAFOSat's negative class ("farm with no pond") is an easy negative: it's
just answering "is there a pond visible on this farm, yes or no," which the
embedding clearly encodes well (hence the strong CAFOSat-internal score).

This project's false positives are a much harder, adversarial-like
category: they are candidates that **already survived classical-CV
color/solidity + SAM refinement** specifically *because* they look
pond-like (dark water-colored shapes with plausible solidity) — canopy
shadow, dark rooftops, wetland fragments. A classifier trained to
distinguish "pond vs. clearly-not-a-pond" doesn't necessarily learn to
distinguish "real pond vs. things a first-stage detector already mistook
for a pond." That's a materially different, harder discrimination task,
and this result suggests AlphaEarth's general-purpose embedding doesn't
resolve it out of the box.

## Bottom line

Three attempts at a false-positive filter for the existing lagoon
candidates (NDWI/GLCM, Dynamic World, AlphaEarth) have now failed on this
project's actual false-positive population, even though the third one
(AlphaEarth) demonstrably works on an easier, non-adversarial version of
the same question. This is a meaningful, specific finding: **the problem
isn't "can a model tell water from non-water" — it's "can a model tell a
real pond from the specific false-positive shapes that already fooled a
prior detection stage."** Any future attempt should train specifically
against this project's own false-positive population (or a similarly
adversarial one), not a generic pond/no-pond dataset like CAFOSat, before
expecting it to help this exact stage of the pipeline.
