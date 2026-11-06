# Verification protocol v1.1: accuracy assessment of map v1 (frozen 2026-11-06; amendment A1)

| Name | What it is |
|---|---|
| **Map v1** | `Task1_results/final/release_v1/` (2,833 houses, 6.98 km² roof; MANIFEST SHA-256 recorded). Frozen, never edited. |
| **Verification v1.1** | This protocol and its measurement of map v1 (notebook 14). |
| **Map v2** | An improved map, made only if this verification shows it is needed. Corrections found here go into v2, never into map v1. |

Status: **frozen 2026-11-06, before any label existed.** This document consolidates
the drafts written on 2026-11-05 and 2026-11-06 (Appendix A keeps each one's
SHA-256). Its own SHA-256 goes into `sample_meta.json`, `sample_meta_addendum.json`
and every result of notebook 14. Any later change gets a new version, a date, a
reason, and a note on whether it affects the sample. **Amendment A1** (end of
this document, 2026-11-06, before any label) adds the published model's
Eastern Shore outlines that are not on map v1 (stratum S9).

Notebook: `notebooks/14_accuracy_assessment.ipynb`. Code: `geo_anom/task1/accuracy.py`.
Samples and labels: shared drive `Task1_results/accuracy_v1/` (they name places;
never in git). Interpreter guide: `docs/TASK1_LABELLING_GUIDE.md`.

Replaces: the single-reviewer 97% precision, the informal 21/24 still-standing
check, and the corrected roof 7.79 km² built on it. Method follows the
good-practice pattern of Olofsson et al. 2014 (sampling design, response design,
analysis; *verify the citation before use*).

## 1. What we estimate

Reference: standing poultry houses in Maryland on the 2023 NAIP photo of each place.

| Parameter | Definition |
|---|---|
| Precision | Share of map v1 outlines on a standing poultry house (Maryland, and Eastern Shore) |
| Houses on a list, T̂_L | Standing houses on at least one list: map v1, the USGS 2016/17 tracing, the notebook-05 detector output west of the Bay, a cell around a western poultry permit, or the footprint candidates (S5) |
| Recall | Correct map houses ÷ T̂_L (Maryland); Eastern Shore version in §5 |
| Roof | Roof area of the houses in T̂_L, km² |
| Residual, R | Standing houses on no list: its own line (§6), never inside T̂_L's interval |

Each with a 95% CI. The Eastern Shore figures (9 counties) are reported on their
own as well. Reported next to the objective numbers against the tracing
(recall 80.5%, precision 88.2%), which stay as they are.

## 2. Response design (how an item is labelled)

**Unit.** One building at a point (centre of the outline, traced polygon,
detection or footprint). Interpreters see a crosshair at the point, never the
outline (its shape would give away where the item came from). Photo:
`accuracy.render_object`.

**Imagery.** NAIP **2023 only** (newest 2023 image covering the point; flight
date printed on the photo), 1 m, surroundings 500 m + close-up 160 m. Cells: the
same at 1.2 m (one of the image's own overview levels; a house is still ≥ 10
pixels wide). When unsure: Google Earth Pro imagery nearest to 2023, date noted.
Caveat to report: the primary imagery is map v1's own input, so dark 2023 flights
hurt both. Some notebook-05 tiles in Calvert, Anne Arundel, St. Mary's, Harford,
Allegany and Garrett mosaic 2017–2022 photos where 2023 did not cover the tile;
labels still use 2023 only.

**Standing poultry house (2023).** All of:
- long, narrow, single-storey building: roughly 12–20 m wide, 100–200 m long
  (40×400 to 66×650 ft), length ≥ 5× width;
- roof complete;
- poultry cues, at least one: tunnel fans or doors on an end, feed bins along a
  side, parallel siblings on the same farm, manure shed or composter nearby.

Idle or rusted houses **count** (idle can't be told from imagery; Extension: rust
is not a reliable sign). Turkey and layer houses count. Not a house: dairy
free-stall barns (wider, open sides, silos and lagoons nearby), hoop/greenhouses,
warehouses, sheds, roads, bare slabs.

**Labels** (one per item): `house`; `gone` (demolished, roofless, bare slab);
`under construction` (counts as not standing in 2023); `not a house`; `unsure`.
Plus a `low confidence` tick, a `poultry, other form` tick (with `not a house`,
for a poultry building outside the shape rule, e.g. a wide or multi-storey layer
house or a short duck house; counted in its own row, never in T̂_L) and an
optional note. One map outline counts as one house (2,450 outlines touch 2,446
traced houses, so merged and split outlines nearly cancel; stated as an
approximation). Analysis: `house` = yes, everything else = no; `unsure` and
`under construction` are also reported counted as yes (sensitivity rows).

**Cells.** A 1 km square (dashed, 100 m margin, faint 3×3 grid) with every known
building outlined in one neutral colour: map v1 outlines, traced polygons,
western notebook-05 detections and S5 footprint candidates. Question: *how many
standing poultry houses have their centre inside the square and none of these
outlines?* Answer 0–5 or 6+, with where in the note. Photo: `accuracy.render_cell`.

**Interpreters.** Umesh Adari (`UA`) and Monica (`Monica`), independent and
blind: each gets every sampled item in their own random order, strata mixed, no
county, source, score or earlier label shown, and no access to the other's labels
until both finish a phase. Known limit: UA labelled most of S2 and all of S7 in
notebook 07; Monica has not. Monica's agreement with the adjudicated label is
reported separately, per stratum (S2 and S7 in particular).

**Calibration.** 30 items that never enter the sample or reserve: the last 10 of
the random orders of S1, S2 and S4, spread over counties. Both label, compare,
discuss; if the wording proves unclear, a new protocol version comes before the
pilot.

**Pilot and gate.** A random 25 sampled items each of S1, S2 and S4 (75),
labelled before anything else. Cohen's kappa on house / not house:
κ ≥ 0.8 → continue (pilot labels kept); κ < 0.8 → revise §2 (new version),
set the pilot aside, replace it from the reserve (same stratum and county),
rerun. Never relabel the same items after seeing the disagreements.

**Adjudication.** Every disagreement (and every `unsure`) reviewed jointly with
the notes; decision and reason recorded. If still split, a third person
(Prof. Nakalembe or Extension) decides; if they can't, the item stays `unsure`.
A cell still split takes the larger count (conservative for recall). Kappa
(5 labels and binary, bootstrap 95% CI) is reported on the **pre-adjudication**
labels, per stratum and overall.

## 3. Sampling design

Frames come from map v1, the USGS tracing, the notebook-05 runs, the MDE registry
snapshot and the Microsoft footprints (SHA-256 of each recorded). Matching: an
outline is *on* a traced house if they intersect; a county's traced extent is the
hull of its traced houses + 500 m. Cells: a fixed 1 km grid (multiples of 1 km in
UTM 18N), cell assigned to the county holding its centre.

| Stratum | Frame | N | n |
|---|---|---|---|
| S1 | Map v1 outlines touching a traced house | 2,450 | 100 |
| S2 | Outlines in the traced extent, touching no traced house | 327 | 150 |
| S3 | Outlines outside the traced extent (30 Eastern Shore + 26 west) | 56 | all |
| S4 | Traced houses no outline touches | 594 | 150 |
| S5ES | Footprint candidates (§4), Eastern Shore | 1,501 | 150 |
| S5WR | Footprint candidates, west, rural (< 100 footprints in their 1 km cell) | 1,497 | 170 |
| S5WD | Footprint candidates, west, developed (≥ 100) | 7,357 | 30 |
| S7 | Western notebook-05 detections touching no map v1 outline | 367 | all |
| S8 | Western cells within 1 km of a western poultry permit (types `chickens_not_laying_hens`, `laying_hens_dry_manure`, `turkeys`, `ducks_liquid_manure`: 6 permits) | 49 | all |
| S6A / S6B / S6C | Eastern Shore cells containing a known house / within 1 km / farther | 1,137 / 2,748 / 5,476 | 150 / 150 / 100 |
| S6WA / S6WB | Western cells (not S8) containing a western detection or map outline / within 1 km | 235 / 1,068 | 40 / 60 |

Western cells farther than 1 km from every known building (15,902) are not
sampled: a feasible n gives a meaningless bound. Houses there count only through
S5 or the residual.

**Allocation.** Within each stratum, proportional by county (largest remainder)
with at least 5 per county, or all of a county's items if fewer. Where those
minimums alone exceed n (e.g. S6WA: 14 counties, n 40), the minimum is lowered one
step at a time until it fits; no county is trimmed below it.

**Draws.** Each stratum × county is a full random permutation: the first n are
the sample, the next the reserve (cells beyond n: not drawn), the last items of
S1, S2 and S4 the calibration set. Two draws, each once, before any label:
- *First sample* (S1–S4, S6), seed **20261105**, drawn 2026-11-05:
  `frame.geojson` + `sample_meta.json`.
- *Addendum* (S5ES, S5WR, S5WD, S7, S8, S6WA, S6WB), seed **20261106**, no pilot or
  calibration: `frame_addendum.geojson` + `sample_meta_addendum.json`.

Notebook 14 refuses to draw either again once its file exists, and refuses the
addendum if any of its keys already has a label. Phases, in order: calibration,
pilot, main (first-sample objects), addendum objects (S5, S7), cells (S6),
addendum cells (S8, S6W).

## 4. Footprint candidates (S5)

Source: Microsoft US Building Footprints v2, Maryland file (ODbL; attribution and
share-alike apply to any derived database we publish), from
`minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/Maryland.geojson.zip`
(the older `usbuildingdata` address refuses since 2026), checked against the
server's MD5; SHA-256 and the per-feature `capture_dates_range` (mostly empty)
recorded. Rule: minimum rotated rectangle ≥ 60 m long and length ≥ 4× width;
touching no map v1 outline, no traced polygon and (west) no notebook-05
detection. Density = number of footprints (all, before the rule) with their centre
in the same 1 km grid cell; it splits the western candidates into rural (S5WR) and
developed (S5WD) before the draw.

**Developed land (S5WD).** Stated assumption: developed land holds no poultry
houses (zoning; no poultry permits there). The 30-item spot check is reported as
"houses found in 30" with its exact bound on its own row (with 0 found, ~700
houses: not a useful bound). S5WD is not used to widen T̂_L's interval; the claim
about developed land rests on the assumption, and the paper says so.

## 5. Estimators

y = 1 if adjudicated `house`; cells give a count. N, n per stratum × county.

- Correct map houses: Ĉ_ES (S1, S2, S3 Eastern Shore), C_W (S3 west, census).
  **Precision** = (Ĉ_ES + C_W) / 2,833 and Ĉ_ES / 2,807.
- Missed traced houses standing M̂ (S4); western detections that are houses R̂_W
  (S7, census); footprint houses F̂_ES (S5ES), F̂_W (S5WR + S5WD); permit-cell
  houses P_W (S8, census). Each Σ N·p̂ over county sub-strata.
- **T̂_L = Ĉ_ES + C_W + M̂ + R̂_W + F̂_ES + F̂_W + P_W.**
- **Recall (Maryland)** = (Ĉ_ES + C_W) / T̂_L; **recall (Eastern Shore)** =
  Ĉ_ES / (Ĉ_ES + M̂ + F̂_ES).
- **Roof (Maryland)** = map outline area of correct houses (Σ N·mean(area·y), S1–S3)
  + S4 traced area × k (outline/traced area on S1 pairs, per county) + S7
  rectangle area + S5 footprint area × k_f (map outline area ÷ footprint area on
  outlines touching both a traced house and a footprint) + P_W × mean roof of
  standing western houses (S3 west + S7; if none, S4). Roof (Eastern Shore) =
  the Eastern Shore terms.
- **CIs:** rescaled stratified bootstrap, 2,000 resamples within each stratum ×
  county, each resampled mean's deviation scaled by √((1 − n/N)·n/(n − 1)) (a census
  has no sampling error); seed recorded. **Constant strata:** where every sampled
  y of a sampled (not census) stratum is equal, that stratum is moved to its exact
  one-sided 95% bound (Clopper-Pearson for objects; for zero-hit cells
  N·(1 − 0.05^(1/n)) positive cells × mean houses per positive cell), one stratum at
  a time with the others at their point estimates, and the wider interval is kept.
  S5WD is exempt (§4).
- Per stratum: share with Wilson and exact 95% intervals.
- Sensitivity rows: `unsure` = house; `under construction` = house; each
  interpreter alone vs adjudicated. T2/T3 (±5%, `docs/PAPER_STANDARD.md`) apply to
  T̂_L and roof (Maryland).

## 6. Residual: houses on no list

Reported on its own line, two ways, never added into T̂_L's interval:
1. **Cells.** Ŷ = Σ (N/n) Σ counts over S6A/B/C and S6WA/B, bootstrap CI, and for
   each zero-hit cell stratum its exact one-sided 95% bound, converted to houses
   with the mean count per positive cell over S6, S6W and S8 (3 if none, stated as
   an assumption). Far western cells: not covered; said so.
2. **Capture-rate model.** q_ES = share of the 3,040 traced houses touched by
   neither a (rule-passing) footprint nor a map v1 outline; q_W = touched by
   neither a footprint nor a notebook-05 (step-0) detection; geometry only,
   Clopper-Pearson 95%. R = L·q/(1 − q), L = list houses off the tracing (Eastern
   Shore: Ĉ in S2 + S3 + F̂_ES; west: all western list houses). Assumes traced
   houses represent houses off the tracing and, for the west, that Eastern Shore
   capture rates transfer. Both assumptions are stated with the number.

## 7. Recorded covariates (declared before labelling)

- Footprint density of the item's 1 km cell, for every sampled item.
- A Maryland land-use class (e.g. state parcel land-use code or the Chesapeake
  Bay Program land use/land cover), if added: the layer is named in an amendment
  **before adjudication**.

Covariates give error breakdowns (e.g. where false detections occur). They never
change an estimate. A breakdown used to design map v2 is reported as such.

## 8. Outputs

- Drive `Task1_results/accuracy_v1/`: both frames and metas (SHA-256), labels per
  interpreter, adjudication log, `strata.csv`, `estimates.csv`, `residual.csv`,
  `agreement.csv`, `run_meta.json` (protocol SHA-256, map v1 MANIFEST SHA-256,
  tracing, footprints and registry SHA-256, seeds, code commit).
- Git: this protocol, notebook 14 (outputs cleared), `accuracy.py` + tests, and an
  anonymous summary (strata sizes, kappa, estimates with CIs; no locations).

## 9. Decisions

1. Interpreters: UA and Monica.
2. S2: sample 150 (not a census).
3. Footprints: on (download approved by the user 2026-11-06); western split by
   density, not by a land-use layer.
4. Third-person adjudicator: Prof. Nakalembe or Extension. *Open.*
5. Under construction = not standing (sensitivity row shows the other way).

## 10. What this verification cannot support

An interval that includes houses on no list; houses in western cells farther than
1 km from any known building, other than through S5 or the model residual;
poultry houses on developed land beyond the stated assumption; per-county western
estimates; poultry buildings outside §2's shape; stocking (idle houses count).

Labelling time, rough, per interpreter: first-sample objects ~460 × 15 s ≈ 2 h;
addendum objects (367 + 350) × 15 s ≈ 3 h; cells (400 + 149) × 40 s ≈ 6 h;
calibration + pilot ≈ 1 h. About 12 h each.

## Appendix A. Drafting history

Each draft's SHA-256 is kept in `sample_meta.json` (`protocol_sha256`,
`protocol_amendments`); the documents are in git history. No label existed at any
of these steps.

| Draft (internal name) | Date | SHA-256 (first 12) | What it set |
|---|---|---|---|
| v0 (proposal) | 2026-11-05 | not frozen | Strata, two blind interpreters, kappa, estimators |
| "v1" | 2026-11-05 | 461665a6c9f6 | Frozen; the first sample (S1–S4, S6, seed 20261105) was drawn under it |
| "v1.1" | 2026-11-05 | 0505a1fc58c1 | Second interpreter: Monica |
| "v1.2" | 2026-11-06 | 7d589b117021 | Statewide scope: S5 (both regions), S7, S8, S6W; list-frame total + residual; exact bounds for constant strata (missing in the first code). Design record: `docs/TASK1_PROTOCOL_v1.2_PROPOSAL.md` (branch `research/protocol-v1.2-statewide`, commit fdadf34) |
| density split | 2026-11-06 | (this document) | S5W split into S5WR / S5WD by footprint density; developed land as a stated assumption; allocation minimum rule; covariate declaration |
| **Verification v1.1** | 2026-11-06 | e5a710851f8f | This consolidation; public naming: map v1 / verification v1.1 / map v2. Frozen; addendum drawn under it |
| Amendment A1 (D1) | 2026-11-06 | in `sample_meta_a1.json` | S9 published-model outlines on the Eastern Shore not on map v1 (census, seed 20261107); published model's precision and recall vs map v1. Briefly recorded as "left out" in PAPER_STANDARD (commit 8a770b9) and reversed by the user the same day, before any label |

Changes made while building the first draft, before the first sample: calibration
items from the tail of the random orders; pilot 25 each from S1, S2, S4 (S3 is a
census with no reserve); no "outline covers two houses" flag (can't be judged
blind); cells answered by count + note, centre-inside rule, 1.2 m; bootstrap
finite-population corrected; every photo NAIP 2023 only.

## Amendment A1 (2026-11-06, before any label): the published model on the Eastern Shore (D1)

Why: the paper's method comparison (published model → map v1) needs the
published model's **precision** on the 2023 sample, not only its recall
(PAPER_STANDARD T4a/T4c). The 2016/17-tracing figures are what this verification
replaces. Nothing else in this protocol changes; the first sample and the
addendum stay as drawn.

**Stratum S9.** Notebook-05 (step-0, published model) outlines in the 9 Eastern
Shore counties that touch no map v1 outline: 30 on 2026-11-06 (Cecil 13,
Worcester 6, Caroline 5, Wicomico 3, Somerset 1, Dorchester 1, Queen Anne's 1;
none touches a traced house). **Census** (n = N), seed **20261107** (sets the
order only), no pilot or calibration items, drawn once into
`frame_a1.geojson` + `sample_meta_a1.json`; refused if any S9 key has a label.
Labelled like every object (§2, blind, NAIP 2023), in the phase *addendum
objects*. Keys `e05:<candidate_id>`. Extra labelling ≈ 30 × 15 s ≈ 8 min per
interpreter.

**Linking.** Each of the other Eastern Shore published-model outlines (2,299)
is linked to the map v1 outline it overlaps most (`step0_links`); a map v1
outline then stands for n_pub ≥ 0 published outlines, and its label serves for
them. Stated as an approximation in the paper: map v1 outlines are mostly the
same detections turned into rectangles (step 1 of notebook 11's ladder).

**Estimators (Eastern Shore).**
- Correct published outlines Ĉ_pub = Σ N·mean(y·n_pub) over S1, S2, S3 (Eastern
  Shore) + Σ y over S9; **precision (published model)** = Ĉ_pub / 2,329.
- **Recall (published model)** = Σ N·mean(y·[n_pub > 0]) over S1–S3 (Eastern Shore)
  ÷ (Ĉ_ES + M̂ + F̂_ES), the same denominator as map v1's Eastern Shore recall.
- Gains (map v1 − published) in precision and recall, from the same bootstrap
  resamples (paired). Constant strata as §5.
- S9 houses (if any) are **not** added to T̂_L: they may overlap footprint
  candidates (S5ES was drawn without excluding them), so adding them could count
  a house twice. They enter only the published model's precision.
