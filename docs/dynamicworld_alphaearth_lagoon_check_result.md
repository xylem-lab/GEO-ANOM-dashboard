# Dynamic World + AlphaEarth zero-shot lagoon checks (2026-09-16)

Two pretrained-model checks against the known real/false-positive lagoon set
(7 visually-confirmed real, 4 CAFOSat-supported, 19 CAFOSat-contradicted, from
the 2026-09-15 CAFOSat validation run). Both required setting up Earth Engine
access for this project for the first time (registered Cloud project
`prime-keel-328306`, see `.env`, gitignored, not committed).

## Dynamic World (Google, 10m Sentinel-2, "water" probability band)

**Result: not usable.** Real lagoons scored water_prob 0.029-0.458 (median
0.042); false positives scored 0.027-0.091 (median 0.036) — almost complete
overlap. Best threshold (0.1-0.2) gets 100% precision but only 18% recall.
**Cause, as suspected before running this**: 10m Sentinel-2 pixels are too
coarse for farm-scale lagoons (tens of meters across) — a lagoon rarely fills
a whole pixel, so its water signal gets diluted with surrounding land cover.
Script: `scripts/check_lagoons_dynamicworld.py`.

## AlphaEarth Satellite Embedding (Google, 10m, 64-dim learned embedding)

**Two real, previously-undiscovered bugs fixed first** in
`geo_anom/phase2/alphaearth_filter.py` (committed here in March 2026, never
tested, no test file existed, not referenced by any current pipeline
script):
1. `.filter(ee.Filter.eq("year", self.year))` matched **zero images, always**
   — this collection's images have no `year` property (verified directly:
   properties are `system:time_start/time_end`, `UTM_ZONE`, `MODEL_VERSION`,
   `DATASET_VERSION`). Fixed to `.filterDate(...)`.
2. Band names were guessed as `embedding_i`/`bi`; the real bands are
   `A00`-`A63` (verified directly against the live collection). Every
   embedding extraction before this fix silently returned all-zero vectors
   via the `.get(key, 0.0)` fallback — this module has never successfully
   extracted a real embedding since it was written.

Also fixed: `get_embedding()` called `.first()` on the whole global,
per-UTM-zone-tiled collection with no spatial filter, so it usually grabbed
a tile that didn't even cover the query point. Now filters by location
first (`filterBounds(point).mosaic()`).

**With real embeddings finally extracted, the result is still negative**:
built a reference embedding from 6 of the 7 confirmed-real lagoons, tested
cosine similarity against the 7th (held out) plus the 4 CAFOSat-supported
candidates (should score high) and the 19 CAFOSat-contradicted candidates
(should score low).

- Real/supported (n=5): mean cosine similarity 0.722, range 0.691-0.766
- False positives (n=19): mean cosine similarity 0.699, range 0.547-0.827

**No threshold separates the groups** — the false-positive group's maximum
(0.827) exceeds the real group's maximum (0.766). Best available operating
point (threshold 0.6) gets 100% recall but only 24% precision, barely above
the test set's 21% base rate of real examples — i.e., close to no better
than guessing.

**Honest caveat, not a final verdict on AlphaEarth**: this was a fast,
minimal baseline (mean-of-6-references cosine similarity), not a properly
trained classifier. AlphaEarth embeddings are used successfully elsewhere
for land-cover discrimination tasks; a real logistic regression or small
classifier trained on more reference points (using CAFOSat's larger MD/DE
sample, or the full national manure-pond-positive set as the "afo" class and
CAFOSat's non-pond patches as explicit negatives, which
`AlphaEarthFilter.build_reference_db()` already supports) might extract more
signal than a 6-point mean can. That's a real next step if this direction is
worth pursuing further — this result rules out the free/instant version, not
the whole approach.

## Bottom line

Neither of today's two zero-training checks produced a usable lagoon
detector. Combined with the earlier NDWI/GLCM-texture negative result and
the CAFOSat-audited ~10% precision of the existing classical-CV pipeline,
this project has now tried and ruled out: color/solidity thresholds, spectral
water indices (NDWI), texture (GLCM), a coarse pretrained land-cover
classifier (Dynamic World), and a naive pretrained-embedding similarity
check (AlphaEarth). The remaining paths are the ones already scoped:
(2) a classifier trained on CAFOSat's real presence-labeled patches, or a
more serious AlphaEarth classifier trained the same way; (3) a Maryland
labeling campaign; (4) full detector training (PRISM-CAFO-style), which
needs both (3) and a Python 3.10 GPU environment.
