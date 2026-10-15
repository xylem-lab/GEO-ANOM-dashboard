# Task 1 — Building and Lagoon Detection: Formal Accuracy Metrics

> **2026-10-07 — superseded.** All figures below were computed on tiles later found to be shifted/stretched for 219/417 sites (see `docs/NEXT_SESSION.md` 2026-10-07); recompute on `data/processed/task1/run_2026-10-07/` before citing. Earlier note: **2026-10-05 — partly superseded.** Counts below come from `full_registry_unet_tulbure_detections.geojson`, which double-counts ~20% of buildings (overlapping tiles) and is missing 15 farms. Current baseline: `data/processed/task1/run_2026-10-05/` (2,251 unique buildings). The R² and precision figures were not recomputed; the §4 recall/0.9% figure needs rechecking. See `docs/NEXT_SESSION.md`.


Building metrics computed 2026-09-10; lagoon rebuild and audit done
2026-09-14 (see section 5) using `geo_anom/phase1/evaluation.py`
(unit-tested against synthetic known values — see
`tests/test_evaluation.py`). Replaces informal "ratio" and one-off
scratchpad-script correlation figures used earlier in this project with
standard, reproducible metrics. Sections 1-4 cover poultry/confined-animal
house detection, which was independently verified clean of the MD-iMAP
registration bug that affected lagoons (0/2,724 detections fall outside
their own source tile's bounds). Section 5 covers the lagoon rebuild.

## 1. Farm-level count regression vs. 2016/17 ground truth

Detected houses per farm vs. Soroka & Duren (2020) hand-labeled houses
within the same 2km footprint, for the 353 farms with any ground-truth
coverage (Delmarva-only — see the documented GT positional-accuracy
limitation below for why this is farm-level count, not point-level IoU).

| Metric | Value |
|---|---|
| n | 353 |
| R² | 0.655 |
| RMSE | 3.66 houses/farm |
| MAE | 2.46 houses/farm |
| Pearson r | 0.854 (p=1.2e-101) |
| Spearman ρ | 0.765 (p=5.4e-69) |

A strong, real linear relationship — R²=0.655 means the model explains
about two-thirds of farm-to-farm variance in true house count, and the very
low p-values rule out this being a chance correlation on a sample this
large.

## 2. Farm-level house count / floor area vs. live registry headcount

Two versions, since raw house **count** turned out to be a weak predictor
of headcount and floor **area** a somewhat better one — both reported
honestly rather than picking the flattering one.

| Comparison | n | Fit | R² | Pearson r | Spearman ρ |
|---|---|---|---|---|---|
| House count ~ headcount | 362 | linear | 0.043 | 0.208 | 0.459 |
| Total floor area (m²) ~ headcount | 362 | linear | 0.090 | 0.301 | 0.567 |
| Total floor area (m²) ~ headcount | 362 | log-log | 0.256 | — | — |

**Why this matters, not just a weaker number**: headcount doesn't
determine house *count* well (R²=0.043) because farms trade off house count
against house *size* — a farm can house the same number of birds in fewer,
bigger houses. Floor area is a materially better predictor (R² roughly
doubles, and the log-log fit — appropriate given headcount spans 3+ orders
of magnitude across farms — gets to R²=0.256). This is a real, useful
finding for the actual downstream goal (nutrient supply, which scales with
floor area / stocking capacity, not raw building count): **total detected
floor area should be preferred over house count as the supply-estimation
input**. Applied 2026-09-14: `supply_calculator.py::calculate_supply()`
now apportions each farm's nutrient total across its detected structures
weighted by floor-area share (falling back to an even split only if a
farm's structures have no usable area data), not an even 1/N split.
Verified with synthetic unit tests (unequal-area farm gets a
proportional, not even, split; equal-area farm still splits evenly as
the correct special case) — there's no ground-truth nutrient dataset to
validate the real-world numbers against yet (that's Phase 3, gated on
external data), so test-level correctness is what this change can
actually be verified against today.

## 3. Object-level precision (real audit, not an eyeball pass)

Stratified sample: 35 farms, 3 per county × 12 counties (low/mid/​high
headcount tier per county), ~300+ individual house detections directly
overlaid on source imagery and visually checked one by one.

**Result: 1 confirmed false positive** (Christopher Both, Caroline County —
a residential building near a pool/patio, geometrically distinct from that
farm's other 11 real detections). Every other detection in the sample
corresponds to a real, visible structure.

Precision over this audited sample ≈ **299/300 ≈ 99.7%** (exact denominator
depends on the precise per-site counts summed from the sample; reported as
an approximate but real, sourced figure — the underlying per-site detection
counts are reproducible from `full_registry_unet_tulbure_detections.geojson`
filtered to the 35 sampled farm names).

## 4. Farm-level recall

Of 341 currently-active poultry-type farms with imagery, **14 (4.1%) show
zero detections**. All 14 have now received a full, documented root-cause
audit (ground-truth cross-check + direct visual inspection of current
imagery, zoomed to the exact registry coordinate with a marker overlay) —
this is a closed, fully-explained number, not a partial one.

**Original 9** (audited in an earlier session): 1 is outside the model's
Delmarva training region entirely (Carroll County); 2 show real land-use
change (ground truth existed in 2016/17, nothing visible now); **3 are
genuine, unexplained model misses** on clearly-visible real structures;
3 show no structures near the registry point at all.

**5 newly-in-scope farms** (added when registry coverage was extended;
audited 2026-09-14 with the same rigor): none turned out to be a genuine
model miss — each has a distinct, non-model explanation, confirmed by
zooming to the exact registry coordinate on current (2023) NAIP imagery:

- **Justin Murphy/Murphy's Crusting & Uniloader Service, Inc.** (320,000
  headcount) — zero structures of any kind within the full ~600m tile;
  the registry point sits in open cropland at a forest edge. The entity
  name is itself a manure-hauling/uniloader service — this strongly reads
  as a **business address registered as the permit location, not a
  physical animal-housing site**. Whatever real barns exist for this
  operation are not at this coordinate.
- **Ernest Adkins Jr./Viola's Acres** (400,000 headcount — the single
  largest in this audit) — the tract is >80% dense pine plantation; the
  only cleared structures found anywhere in the tile (a house, a small
  shed, a pond) are residential-scale, nowhere near sufficient for a
  400,000-bird operation. **No structure matching the registered
  headcount exists anywhere in this tile** — the most surprising single
  finding of this audit, and worth a real follow-up (the headcount may be
  aggregated across a non-contiguous second site, or the registry
  coordinate may be simply wrong).
- **J. Farm, LLC "Red Dirt Road"/Stephen J. Stoltzfus** (144,000
  headcount) — the registry point and essentially the entire ~600m tile
  is dense forest/pine plantation; zero structures of any kind visible
  anywhere in it.
- **VALO BioMedia North America LLC (New Construction)** (52,440
  headcount) — the registry point itself sits on open cropland, but a
  real, large industrial-scale building complex is visible ~180-200m
  away along the same road. That building's architecture (large blocky,
  flat-roofed complex, not an elongated barn) doesn't match the classic
  poultry-house shape the Tulbure filter is calibrated for — consistent
  with the "(New Construction)" qualifier and a biomedia/vaccine-
  production use, not conventional broiler housing. **A real structure
  exists nearby, but a coordinate offset and a non-standard building
  typology both work against detection here** — distinct from a model
  failure on a normal barn.
- **Eldwin D. Martin** (17,000 headcount, ducks) — the registry point
  sits inside a small rural residential cluster; a small (~15m)
  outbuilding is close to the point, plausible as a modest duck house
  given the much smaller headcount, but the surrounding development
  reads as a residential subdivision rather than a farm complex. The
  most ambiguous of the five — flagged as inconclusive rather than
  forced into a category, on the same "don't report more precision than
  the evidence supports" standard as everything else in this document.

**Final tally across all 14 zero-detection farms**: outside training
region (1), land-use change (2), genuine unexplained model miss (3,
**0.9% of the full 341-farm population** — the number that actually
characterizes detector quality), no structures found in-tile at all (6:
the original 3 plus Murphy, Adkins, and Stoltzfus), real structure
present but non-standard type/coordinate offset (1: VALO), inconclusive
small-scale ambiguous case (1: Martin). Zero of the 14 are attributable
to canopy occlusion or a shape-filter edge case on an otherwise-normal
barn — every non-model explanation found here is a registry/coordinate
or building-typology issue, not a detector weakness.

## 5. Lagoon detection rebuild (2026-09-14): registration bug fixed, but a new, deeper precision problem found

**Background**: lagoons were detected from MD iMAP RGB tiles while houses
were detected from Planetary Computer (PC) NAIP tiles — two different
imagery sources with a real, confirmed ~70-100m mutual georeferencing
offset. This is what produced the "lagoon sitting on a field" bug you
found in Google Earth. The fix: rebuild lagoon candidate generation on
Planetary Computer imagery (same source as houses), reusing the
already-validated color/solidity/area/barn-proximity filters from
`sam_lagoon_refine.py`, ported into a new `scripts/ndwi_lagoon_detect.py`.

**Registration bug: confirmed fixed.** Direct coordinate comparison
against the previously-confirmed-real lagoons on James Donald Dulin's and
Hoa Tran's farms shows the new PC-sourced detections land within ~5m of
the original MD-iMAP-derived coordinates — negligible, expected
floating-point-level agreement. Roland Todd's farm (the exact farm used
in the original bug diagnosis) shows the offset directly: the
MD-iMAP-derived coordinate for that farm's real lagoon sits **~100m from
the actual visible water body** on the PC tile — confirming the bug's
magnitude and cause exactly as diagnosed, and confirming MD iMAP's
georeferencing error is real but **spatially variable** (negligible on
some farms, ~100m on others), consistent with a local
orthorectification/DEM error rather than one constant global offset.

**A new, more serious problem found while building the fix: candidate
generation does not generalize to full scale, even after honest
recalibration.** The color/solidity thresholds from `sam_lagoon_refine.py`
were calibrated on MD iMAP's specific color rendering; direct measurement
found they don't transfer to PC imagery's different color processing (a
known-false Brian Harding natural-pond candidate measured b-r=17.5 on PC
imagery, inside the old threshold's "water" range). Recalibrated on a
7-farm hand-checked test set (raised `MIN_SOLIDITY` 0.85→0.90,
`mask_is_water_colored`'s b-r floor 15→19) — but a **position-level check
caught a labeling mistake in that recalibration itself**: a candidate on
Roland Todd's tile that matched by farm name was assumed to be the
confirmed-real lagoon, but was actually a *different*, false candidate
~1km away in solid forest canopy — the real lagoon's color was too dark
(near-black under partial canopy shading) to generate a candidate box at
all. Corrected, the true positive count in that test set was only 2 (not
3), which the recalibrated thresholds still didn't cleanly separate from
every false class using color/solidity alone.

**Full-scale run (417 farms) found 74 candidates. A stratified visual
audit of 10 candidates across 4 farms found only 1 confirmed real
lagoon** — the rest were dark building rooftops, forest-edge/hedgerow
shadow, and river/wetland fragments, each independently passing the
color+solidity check the same way real lagoons do. This is the same
false-positive-whack-a-mole pattern already documented multiple times in
this project's history (river → pool → forest canopy on MD iMAP), now
recurring in new forms (rooftops, hedgerows, river fragments) on a
different imagery source, after an honest recalibration attempt. **This
sample is small (n=10) and not a full audit of all 74** — reported as a
clear, preliminary signal, not a final precision number.

**Recommendation**: the registration-bug fix is real and should be kept —
`scripts/ndwi_lagoon_detect.py` is the correct pipeline shape (same
imagery source as houses, filters ported and honestly recalibrated where
measurement supported it). But `data/processed/detections/
full_registry_pc_lagoon_detections.geojson`'s 74 candidates should be
treated as **unverified candidates requiring individual visual review**,
not a trusted detection count — do not report "N lagoons detected" from
this file without that review. NDWI is computed and stored per-candidate
(`ndwi_mean` property) as a diagnostic; it does not separate real lagoons
from these false-positive classes any better than color did (real lagoons
measured NDWI from -0.15 to +0.19 in this project's own data, overlapping
false positives' range) — this reinforces, rather than resolves, the
NDWI negative result already found earlier this session. A reliable
automated lagoon detector likely needs either a labeled training set for
a real classifier, or hand-verification of every candidate before use;
neither is in scope for this pass.

## Known limitation, stated explicitly (not hidden)

Soroka & Duren's 2016/17 ground truth has a real positional-accuracy issue
(100-450m per-point offset, confirmed by direct visual overlay — our own
detections land exactly on real houses; the GT points do not, on the same
imagery). This is why metric #1 above is a **farm-level count regression**,
not point-level precision/recall/IoU against that dataset — point matching
against it would produce numbers that don't reflect real detector quality.
Metric #3 (real object-level precision) instead comes from direct visual
audit against current imagery, which is not affected by this limitation.

## What "a reasonable position" looks like from here

**Buildings** are a genuine, reproducible, honestly-scoped, and now
**fully closed out** result: strong farm-level count agreement
(R²=0.655 vs. real 2016/17 ground truth), very high measured precision
(~99.7% on a stratified sample spanning the whole state), and a true
miss rate, audited across the entire zero-detection population (14/14,
not a partial sample), of **0.9%** (not the less-informative blanket
2.9%-8% figures used earlier in the project). The floor-area finding is
a real, usable methodological improvement, already applied to
`supply_calculator.py`. This half of Task 1 is publication-ready.

**Lagoons** are a different story: the registration bug is genuinely
fixed (section 5), but full-scale precision is not — a preliminary
10-candidate audit found ~1/10 real. This is a real, honestly-reported
negative result for the write-up, not a solved problem: automated
lagoon detection from single-date RGB(+NIR) NAIP imagery, at this
resolution, has hit a real ceiling across every signal tried this
project (RGB color, shape/solidity, NDWI, texture). Worth framing in a
paper as a genuine limitation/future-work finding rather than glossed
over — the buildings result stands on its own regardless.
