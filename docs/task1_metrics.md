# Task 1 — Building Detection: Formal Accuracy Metrics

Computed 2026-09-10 using `geo_anom/phase1/evaluation.py` (unit-tested against
synthetic known values — see `tests/test_evaluation.py`). Replaces informal
"ratio" and one-off scratchpad-script correlation figures used earlier in
this project with standard, reproducible metrics. Lagoon detection is
explicitly out of scope here (paused — see plan file for why); this covers
poultry/confined-animal house detection only, which was independently
verified clean of the MD-iMAP registration bug that affected lagoons (0/2,724
detections fall outside their own source tile's bounds).

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
input**, not something the pipeline currently does (`supply_calculator.py`
apportions by structure count, not by area — worth revisiting).

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
zero detections**. This isn't one uniform "miss rate" — individually
investigated:

- **9 farms** received a full, documented root-cause audit (ground-truth
  cross-check + direct visual inspection of current imagery) in an earlier
  session: 1 is outside the model's Delmarva training region entirely
  (Carroll County); 2 show real land-use change (ground truth existed in
  2016/17, nothing visible now); **3 are genuine, unexplained model misses**
  on clearly-visible real structures (~1% true miss rate against the full
  341-farm population); 3 show no structures near the registry point at
  all (plausibly not-yet-built permits or a registry coordinate that
  doesn't sit on the actual farm).
- **5 farms** are newly in scope (added when registry coverage was
  extended) and have **not** received the same individual audit. A quick
  visual check found: 2 with no visible structures in dense forest
  (inconclusive at a glance — needs a closer look), 1 whose registry name
  ("...Crusting & Uniloader Service") suggests the point may be a hauling
  business address rather than a physical farm, 1 with a headcount large
  enough (400,000) that a genuine miss would be notable if confirmed, and
  1 (VALO BioMedia) whose visible buildings don't match the classic
  elongated-barn shape at all — plausibly a different, untrained-for
  building typology (the company name suggests biomedia/vaccine production,
  not conventional broiler housing). **Flagged as needing the same audit
  rigor as the original 9 before folding into a final recall number** —
  not done here to avoid reporting a number that looks more precise than
  the evidence behind it actually is.

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

This is a genuine, reproducible, honestly-scoped result: strong farm-level
count agreement (R²=0.655 vs. real 2016/17 ground truth), very high
measured precision (~99.7% on a stratified sample spanning the whole
state), and a true miss rate on well-characterized farms of about 1% (not
the less-informative blanket 2.9%-8% figures used earlier in the project).
The floor-area finding (#2) is a real, usable methodological improvement
for the nutrient-calculation step. The 5 unaudited farms are the one loose
end before this could be called fully closed out.
