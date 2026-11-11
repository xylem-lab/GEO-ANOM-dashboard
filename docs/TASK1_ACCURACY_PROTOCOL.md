# Verification protocol v1.1, revision 2: accuracy assessment of map v1 (frozen 2026-11-10)

| Name | What it is |
|---|---|
| **Map v1** | `Task1_results/final/release_v1/` (2,833 houses, 6.98 km² roof; MANIFEST SHA-256 recorded). Frozen, never edited. |
| **Verification v1.1** | This protocol and its measurement of map v1 (notebook 14). |
| **Map v2** | An improved map, made only if this verification shows it is needed. Corrections found here go into v2, never into map v1. |

**History.**
1. 2026-11-06: verification v1.1 frozen (first sample and statewide addendum drawn); amendment A1 added the published model's Eastern Shore outlines (S9), before any label.
2. 2026-11-10: pilot 1 failed the kappa gate (κ 0.58, 95% CI 0.37–0.77). Most disagreements were `unsure` against `house` or `gone`, because `unsure` was doing two jobs: a label and a "check later" flag.
3. 2026-11-10, **revision 2** (this document, before any round-2 label): forced-choice labels with a separate *check later* tick and a narrow *can't tell: photo unreadable* label (§2). Calibration and pilot replaced from the reserve (§3). Samples otherwise unchanged.

The SHA-256 of this document goes into `sample_meta_r2.json` and every result of
notebook 14. Earlier versions' SHA-256 are in Appendix A. Any later change gets a
new revision, a date, a reason and a note on whether it affects the sample.

Notebook: `notebooks/14_accuracy_assessment.ipynb`. Code: `geo_anom/task1/accuracy.py`.
Samples and labels: shared drive `Task1_results/accuracy_v1/` (they name places;
never in git). Interpreter guide: inside notebook 14 ("How to decide") and
`docs/TASK1_LABELLING_GUIDE.md`.

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
| Published model (Eastern Shore) | Precision and recall of the notebook-05 step-0 outlines, from the same labels (§5) |

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
pixels wide). Optional: Google Earth Pro imagery nearest to 2023, date noted.
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
is not a reliable sign). Turkey and layer houses count.

**Labels (revision 2).** One per item, forced choice:

| Label | Use when |
|---|---|
| `house` | It meets all three points above |
| `gone` | A house was clearly here: bare slab, scar or roofless frame |
| `under construction` | Frame or unfinished roof (counts as not standing in 2023) |
| `not a house` | Anything else, including look-alikes: equipment sheds, greenhouses / hoop houses, manure sheds, long barns with no poultry cues, dairy free-stall barns, warehouses, roads, fields |
| `can't tell` (button: *can't tell: photo unreadable*) | The photo doesn't show the ground at the crosshair: cloud or haze, heavy blur, black or cut-off tile edge, or no 2023 photo loaded |

If the building can be seen but the interpreter can't decide what it is,
`can't tell` is the wrong label: they pick the most likely label and tick
**check later**.

**Check later** (a tick, not a label; replaces round 1's *low confidence*): "not
sure, or want this photo looked at again". It never changes the label, which
still counts. A note says why. Also a `poultry, other form` tick (with `not a
house`, for a poultry building outside the shape rule, e.g. a wide or multi-storey
layer house or a short duck house; its own row, never in T̂_L) and a note box.

**Pace.** About 10 s a photo is normal. The labelling screen warns when the last
10 photos took less than 3 s each (median). Median seconds per photo, notes written
and ticks are reported per interpreter and phase.

One map outline counts as one house (2,450 outlines touch 2,446 traced houses, so
merged and split outlines nearly cancel; stated as an approximation). Analysis:
`house` = yes, everything else = no; `can't tell` and `under construction` are
also reported counted as yes (sensitivity rows).

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

**Calibration (round 2).** 30 items that never enter the sample: 10 each of S1,
S2 and S4 (§3). Both label, compare, discuss. If the wording proves unclear, a new
revision comes before the pilot.

**Pilot and gate (round 2).** 74 sampled items (25 S1, 24 S2, 25 S4; §3),
labelled before anything else. Gate: Cohen's kappa on house / not house ≥ 0.8 on
the complete pilot (`can't tell` counts as not house, so `house` against `can't
tell` is a disagreement), **and** `can't tell` on at most 5% of the pilot labels.
Above 5%: stop and look before going on. κ ≥ 0.8 → continue (pilot labels kept);
κ < 0.8 → revise §2, set the pilot aside, replace it from the reserve, rerun.
Never relabel the same items after seeing the disagreements. Reported: the number
of photos flagged *check later*, and agreement on flagged and unflagged photos.
The round-1 rule (`unsure` = house would have given κ 0.77) is a sensitivity
check of round 1 only, never a gate rule.

**Adjudication.** Every disagreement, every `can't tell` and every photo ticked
*check later* is reviewed jointly with the notes; decision and reason recorded. If
still split, a third person (Prof. Nakalembe or Extension) decides; if they can't,
the item stays `can't tell`. A cell still split takes the larger count
(conservative for recall). Kappa (5 labels and binary, bootstrap 95% CI) is
reported on the **pre-adjudication** labels, per stratum and overall.

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
| S9 | Published-model (notebook-05 step-0) outlines on the Eastern Shore touching no map v1 outline | 30 | all |
| S8 | Western cells within 1 km of a western poultry permit (types `chickens_not_laying_hens`, `laying_hens_dry_manure`, `turkeys`, `ducks_liquid_manure`: 6 permits) | 49 | all |
| S6A / S6B / S6C | Eastern Shore cells containing a known house / within 1 km / farther | 1,137 / 2,748 / 5,476 | 150 / 150 / 100 |
| S6WA / S6WB | Western cells (not S8) containing a western detection or map outline / within 1 km | 235 / 1,068 | 40 / 60 |

Western cells farther than 1 km from every known building (15,902) are not
sampled: a feasible n gives a meaningless bound. Houses there count only through
S5 or the residual. S9 outlines (Cecil 13, Worcester 6, Caroline 5, Wicomico 3,
Somerset 1, Dorchester 1, Queen Anne's 1) touch no traced house.

**Allocation.** Within each stratum, proportional by county (largest remainder)
with at least 5 per county, or all of a county's items if fewer. Where those
minimums alone exceed n (e.g. S6WA: 14 counties, n 40), the minimum is lowered one
step at a time until it fits; no county is trimmed below it.

**Draws.** Each stratum × county is a full random permutation: the first n are
the sample, the next the reserve (cells beyond n: not drawn), the last items of
S1, S2 and S4 the calibration set. Three draws, each once, before any label of
their items:
- *First sample* (S1–S4, S6), seed **20261105**, 2026-11-05: `frame.geojson` +
  `sample_meta.json`.
- *Addendum* (S5ES, S5WR, S5WD, S7, S8, S6WA, S6WB), seed **20261106**, 2026-11-06,
  no pilot or calibration: `frame_addendum.geojson` + `sample_meta_addendum.json`.
- *S9* (census; the seed **20261107** sets the order only), 2026-11-06:
  `frame_a1.geojson` + `sample_meta_a1.json`.

**Round 2 (2026-11-10).** No new random numbers: every choice follows the ranks
drawn with seed 20261105 (`accuracy.start_round2`), saved as `frame_r2.geojson` +
`sample_meta_r2.json`; `frame.geojson` is not rewritten.
- Pilot: each round-1 pilot item becomes *discarded pilot*, and the reserve item
  with the lowest rank in its stratum and county takes its place in the sample and
  the pilot (72 items). Where a county has no reserve (S2 Cecil, a census of 1; S2
  Dorchester, all 4 sampled), dropping the item would leave the county short, so
  the 3 round-1 items stay in the sample, are kept out of every labelling queue and
  get their label by adjudication (recorded with a reason). They are not in any
  kappa. Dorchester's 2 remaining sampled items join the pilot; S2's pilot is 24.
- Calibration: each round-1 calibration item becomes *used calibration*, and the
  reserve item with the highest rank in its stratum and county becomes calibration
  (from the other end of the order, so it never meets the pilot replacements). One
  S2 county with no reserve takes the stratum's highest-ranked reserve item
  elsewhere.
- Refused if any round-2 calibration, pilot or sampled item (other than the 3 kept)
  was labelled in round 1. The main sample is unchanged: nobody has seen it.

Notebook 14 refuses to draw any of these again once its file exists. Phases, in
order: calibration, pilot, main (first-sample objects), addendum objects (S5, S7,
S9), cells (S6), addendum cells (S8, S6W).

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
- **Published model (Eastern Shore).** Each of the other 2,299 Eastern Shore
  published-model outlines is linked to the map v1 outline it overlaps most
  (`step0_links`), so a map v1 outline stands for n_pub ≥ 0 published outlines
  (an approximation, stated: map v1 outlines are mostly the same detections turned
  into rectangles). Ĉ_pub = Σ N·mean(y·n_pub) over S1–S3 (Eastern Shore) + Σ y over
  S9; **precision** = Ĉ_pub / 2,329; **recall** = Σ N·mean(y·[n_pub > 0]) over S1–S3
  (Eastern Shore) ÷ (Ĉ_ES + M̂ + F̂_ES). Gains (map v1 − published) from the same
  bootstrap resamples (paired). S9 houses are **not** added to T̂_L (they may
  overlap S5ES candidates and be counted twice).
- **CIs:** rescaled stratified bootstrap, 2,000 resamples within each stratum ×
  county, each resampled mean's deviation scaled by √((1 − n/N)·n/(n − 1)) (a census
  has no sampling error); seed recorded. **Constant strata:** where every sampled
  y of a sampled (not census) stratum is equal, that stratum is moved to its exact
  one-sided 95% bound (Clopper-Pearson for objects; for zero-hit cells
  N·(1 − 0.05^(1/n)) positive cells × mean houses per positive cell), one stratum at
  a time with the others at their point estimates, and the wider interval is kept.
  S5WD is exempt (§4).
- Per stratum: share with Wilson and exact 95% intervals.
- Sensitivity rows: `can't tell` = house; `under construction` = house; each
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
  Bay Program land use/land cover), if added: the layer is named in a revision
  **before adjudication**.

Covariates give error breakdowns (e.g. where false detections occur). They never
change an estimate. A breakdown used to design map v2 is reported as such.

## 8. Outputs

- Drive `Task1_results/accuracy_v1/`: the frames and metas (SHA-256), labels per
  interpreter (round 1 in `labels/archive_round1/` with `pilot1_record.json`),
  guide examples (`guide_examples.csv`), adjudication log, `strata.csv`,
  `estimates.csv`, `residual.csv`, `agreement.csv`, `run_meta.json` (protocol
  SHA-256, map v1 MANIFEST SHA-256, tracing, footprints and registry SHA-256,
  seeds, code commit).
- Git: this protocol, notebook 14 (outputs cleared), `accuracy.py` + tests, and an
  anonymous summary (strata sizes, kappa, estimates with CIs; no locations).
- Methods section: pilot 1 is reported (κ, table, date, what changed), not hidden.

## 9. Decisions

1. Interpreters: UA and Monica.
2. S2: sample 150 (not a census).
3. Footprints: on (download approved by the user 2026-11-06); western split by
   density, not by a land-use layer.
4. Third-person adjudicator: Prof. Nakalembe or Extension. *Open.*
5. Under construction = not standing (sensitivity row shows the other way).
6. Revision 2 labels, flag, gate rule and naming: approved by the user 2026-11-10.

## 10. What this verification cannot support

An interval that includes houses on no list; houses in western cells farther than
1 km from any known building, other than through S5 or the model residual;
poultry houses on developed land beyond the stated assumption; per-county western
estimates; poultry buildings outside §2's shape; stocking (idle houses count).

Labelling time, rough, per interpreter, at about 10 s an object and 40 s a cell:
first-sample objects ~455 ≈ 1.3 h; addendum objects ~750 ≈ 2 h; cells (400 + 149)
≈ 6 h; calibration + pilot ≈ 20 min. About 10 h each.

## Appendix A. Earlier versions

SHA-256 of each is in the sample metas (`protocol_sha256`, `protocol_amendments`);
the documents are in git history.

| Version | Date | SHA-256 (first 12) | What it set |
|---|---|---|---|
| "v1" | 2026-11-05 | 461665a6c9f6 | Frozen; first sample drawn under it |
| "v1.1" | 2026-11-05 | 0505a1fc58c1 | Second interpreter: Monica |
| "v1.2" | 2026-11-06 | 7d589b117021 | Statewide scope (S5, S7, S8, S6W), list-frame total + residual, exact bounds |
| Verification v1.1 | 2026-11-06 | e5a710851f8f | Consolidation (with the density split); addendum drawn under it |
| + amendment A1 | 2026-11-06 | 168f5507b75a | S9 and the published model's precision/recall; round 1 labelled under it |
| **Revision 2** | 2026-11-10 | (this document) | Labels, check later, gate rule, round-2 calibration and pilot |
