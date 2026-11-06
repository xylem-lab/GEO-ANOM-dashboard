# Task 1 accuracy assessment: protocol and sample design (v1.2, 2026-11-06)

Status: **v1, approved 2026-11-05 and frozen before the sample was drawn.** Its
SHA-256 is written into `sample_meta.json` and every result of notebook 14. Any
later change gets a new version (v2, ...), the reason, and is reported. Changes
from the reviewed draft v0 are listed in §8; amendments after the draw in §9.
**v1.2 (2026-11-06) extends the scope to all of Maryland: §10 governs where it
differs from §1–§7.**

Notebook: `notebooks/14_accuracy_assessment.ipynb`. Reusable code:
`geo_anom/task1/accuracy.py`. Labels and samples: shared drive
`Task1_results/accuracy_v1/` (they name locations, so never git).

Replaces: the single-reviewer 97% precision, the informal 21/24 still-standing
check, and the corrected roof 7.79 km² built on it. Method follows the
good-practice pattern of Olofsson et al. 2014 (sampling design, response
design, analysis; *verify the citation before use*).

## 1. What we estimate

Map: `Task1_results/final/release_v1/maryland_poultry_houses.geojson`
(MANIFEST SHA-256 recorded). Reference date: the 2023 NAIP flight of each site.

| Parameter | Definition |
|---|---|
| Precision | Share of map outlines that sit on a standing poultry house in 2023 |
| Houses standing | Total standing poultry houses on the Eastern Shore in 2023 |
| Recall | Map houses that are correct ÷ houses standing |
| Roof | Total roof area of standing houses, km² |

Each with a 95% CI. Scope: precision statewide (all 2,833 outlines); recall,
houses and roof on the 9 Eastern Shore counties *(v1.1; v1.2 makes houses,
recall and roof statewide, see §10)*. West of the Bay, omissions are
out of scope (Extension: almost no houses there; 07 found 36 among 417
detections) and this is stated as a limitation.

## 2. Response design (how an item is labelled)

**Unit.** One building at a point (centre of the map outline or of the traced
polygon). Interpreters see a crosshair at the point, **not** the map outline or
the USGS polygon (the shape would give away whether it is a detection or a
traced house). Photo: `accuracy.render_object`.

**Imagery.** Primary: NAIP **2023 only** (newest 2023 image covering the point;
the flight date is printed on the photo), 1 m, surroundings 500 m + close-up
160 m. Cells: the same at 1.2 m (one of the image's own overview levels; a house
is still ≥ 10 pixels wide). Secondary, when unsure: Google Earth Pro historical imagery
nearest to 2023; the interpreter records the date used. Caveat to report: the
primary imagery is the map's own input, so dark 2023 flights hurt both.

**Standing poultry house (2023).** All of:
- long, narrow, single-storey building: roughly 12–20 m wide, 100–200 m long
  (40×400 to 66×650 ft), length ≥ 5× width;
- roof complete;
- poultry cues, at least one: tunnel fans or doors on an end, feed bins along a
  side, parallel siblings on the same farm, manure shed or composter nearby.

Idle or rusted houses **count** as standing (idle can't be told from imagery;
Extension: rust is not a reliable sign). Turkey and layer houses count.
Not a house: dairy free-stall barns (wider, open sides, silos and lagoons
nearby), hoop/greenhouses, warehouses, sheds, roads, bare slabs.

**Labels** (one per item):
1. `house` — standing poultry house
2. `gone` — a house was here but is demolished, roofless or a bare slab
3. `under construction` — house frame/roof incomplete on the 2023 photo
4. `not a house` — some other object or nothing
5. `unsure`

plus a `low confidence` tick and an optional note. One map outline counts as
one house (in release_v1, 2,450 outlines touch 2,446 traced houses, so merged
and split outlines nearly cancel; stated as an approximation). For the analysis, `house` = yes;
everything else = no; `unsure` is reported both ways (sensitivity bound), never
dropped.

**Cells** (S6 below): the 1 km square (dashed, with a 100 m margin and a faint
3×3 grid) shown with every known building (map outlines and USGS polygons, one
neutral colour). Question: *how many standing poultry houses have their centre
inside the square and no outline?* Answer 0–5 or 6+, and say where in the note
(e.g. "NE ninth, 3 houses"). Photo: `accuracy.render_cell`.

**Interpreters.** Two, independent and blind: Umesh Adari (UA) and Monica
(decided 2026-11-05, §9). Each gets the full sample, own random order, strata
mixed, no county, model score, stratum or earlier label shown, and no access to
the other's file until both are done. Known limit: Umesh labelled most of S2 in
notebook 07 a week ago; Monica has not seen those labels. We report Monica's
agreement with the adjudicated label separately so the result doesn't rest on
Umesh alone.

**Calibration (before the pilot).** 30 items that can never enter the sample or
the reserve: the last 10 items of the random orders of S1, S2 and S4, spread
over counties. Both label, compare, discuss. If the discussion shows §2 is
unclear, write v2 before the pilot.

**Pilot and gate.** A random 25 items of each of S1, S2 and S4 (75) are the
pilot, labelled before the rest (S3 is a census, so it has no reserve and is
not in the pilot). Cohen's kappa on house / not house:
- κ ≥ 0.8 → continue; pilot labels are kept.
- κ < 0.8 → revise §2 (new version), discard the pilot items, replace them from
  the pre-drawn reserve, rerun the pilot. Never relabel the same items after
  seeing the disagreements.

**Adjudication.** After both finish: every disagreement is reviewed jointly
with the note of who said what; reason recorded. If still split, a third person
(Prof. Nakalembe or Extension) decides; if they can't, the item stays `unsure`.
A cell still split takes the larger of the two counts (conservative for recall).
Report kappa (5-class and binary, bootstrap 95% CI) on the **pre-adjudication**
labels, per stratum and overall.

## 3. Sampling design

Frames are built from the frozen release and the USGS tracing (SHA-256
recorded), matched as in `final.score` (outline intersects traced polygon;
traced extent = hull + 500 m). Within each stratum, stratified by county with
proportional allocation (minimum 5 per county where available, or all if
fewer). Seed fixed and recorded. Each stratum is drawn as a full random
permutation: the first n are the sample, the next ones are the reserve, the last
ones are the calibration items. The sample file is saved with its SHA-256 before
anyone labels, and notebook 14 refuses to draw again once it exists. Seed:
20261105.

| Stratum | Frame | N | n | Expected 95% half-width | Replaces |
|---|---|---|---|---|---|
| S1 map ∩ tracing | Outlines touching a traced house | 2,450 | 100 | If 100/100: stratum ≥ 96.4% (exact) | the assumption that these are all right |
| S2 map, not traced | Outlines in the traced extent, touching no traced house | 327 | 150 | ±3.5 pts at p≈0.9 | 97% precision |
| S3 map outside tracing | Outlines outside the traced extent (30 ES + 26 west) | 56 | 56 (all) | none (census) | — |
| S4 traced, not mapped | Traced houses no outline touches | 594 | 150 | ±5 pts at p≈0.85, ±7 at 0.5 | 21/24 |
| S5 footprint candidates | Long narrow buildings in an independent footprint dataset touching neither map nor tracing (optional, §4) | tbd | ≤150 or all | tbd | — |
| S6 1 km cells | Eastern Shore cells, 3 sub-strata (below) | 9,375 | 400 | upper bound, see below | houses neither source has |

S6 sub-strata (9,361 cells whose centre is in an Eastern Shore county):

| Sub-stratum | Cells | n |
|---|---|---|
| A: contains a mapped or traced house | 1,137 | 150 |
| B: within 1 km of one | 2,748 | 150 |
| C: farther | 5,476 | 100 |

**Honest expectation for S6.** Houses neither traced nor mapped are rare
(rough guess from 07: tens, mostly beside existing farms). With 150 cells in A
and zero hits, the 95% upper bound is ~20 cells ≈ 60 houses; in B, ~64 cells.
So cells alone give a weak upper bound. That is why S5 exists: an independent
footprint dataset finds most such buildings directly, and the cells only have
to bound what *both* sources miss.

Labelling time (rough, per interpreter): ~460–610 objects × 15 s ≈ 2–2.5 h;
400 cells × 40 s ≈ 4.5 h; calibration + pilot ≈ 1 h. About 8 h each.

## 4. Optional S5: independent footprints

Candidate: Microsoft Global ML Building Footprints (open licence; check the
licence and imagery dates before use). Filter: length ≥ 60 m, length/width ≥ 4,
inside the Eastern Shore, touching no map outline and no traced house. Label
like S2. Needs a one-time download (~hundreds of MB for Maryland; I'd ask first).
It also gives the audit's step 5 cross-check of missed houses for free (share of
S4 houses that have a footprint).

## 5. Estimators

N_h = frame size, n_h = sample size, y = 1 if adjudicated `house`.

- Stratum share: p̂_h = Σy / n_h, variance (1 − n_h/N_h) p̂_h(1 − p̂_h)/(n_h − 1),
  combined over county sub-strata.
- **Correct map houses**: Ĉ = Σ_{S1,S2,S3} N_h p̂_h. **Precision** = Ĉ / 2,833
  (statewide) and Ĉ_ES / 2,807 (Eastern Shore).
- **Still-standing missed traced houses**: M̂ = N_S4 p̂_S4.
- **Houses neither source has**: Ŷ = Ŷ_S5 + Σ_g (C_g / c_g) Σ counts in sampled
  cells of sub-stratum g (minus any already counted in S5).
- **Houses standing**: T̂ = Ĉ_ES + M̂ + Ŷ. **Recall** = Ĉ_ES / T̂.
- **Roof**: map outline area of correct houses, expanded per stratum
  (Σ N_h × mean(area·y)), + S4 standing traced footprints × k (outline/trace
  ratio on found houses, 0.963 in release_v1), + Ŷ × mean area of S4 standing
  houses.
- CIs: 95%, rescaled stratified bootstrap (2,000 resamples within each stratum
  and county; each resampled mean's deviation scaled by √((1 − n/N)·n/(n − 1)),
  so a census stratum has no sampling error; seed recorded) for ratios and totals; Wilson/Clopper-Pearson reported
  per stratum. A stratum with zero errors uses its exact bound so the combined
  interval is not falsely narrow.
- Sensitivity rows: `unsure` = house vs not; `under construction` = house vs
  not; each interpreter alone vs adjudicated.

Reported next to the objective numbers vs the tracing (recall 80.5%, precision
88.2%), which stay as they are.

## 6. Outputs

- Drive `Task1_results/accuracy_v1/`: frames, sample + reserve (SHA-256), raw
  labels per interpreter, adjudication log, estimates, run_meta (protocol SHA,
  release MANIFEST SHA, USGS SHA, seed, code commit).
- Git: this protocol, notebook 14 (outputs cleared), `accuracy.py` + tests, and
  an anonymous summary table (strata sizes, kappa, estimates with CIs; no
  locations).

## 7. Decisions (defaults in v1 until decided)

1. Second interpreter: **Monica** (decided 2026-11-05).
2. S2: sample 150. (Labelling all 327 would add ~1 h each; possible later as v2
   only before S2 labels are opened.)
3. S5 footprints: **off** until the download is approved. S6 still runs; with S5
   off, Ŷ comes from the cells alone and is reported as weak.
4. Third-person adjudicator: Prof. Nakalembe or Extension. *Open.*
5. Under construction = **not standing** for 2023 (sensitivity row shows the other way).

## 8. Changes from draft v0 (made before the sample was drawn)

- Calibration items come from the tail of the random orders, not 07's western
  detections (no extra frame needed; never sampled).
- Pilot is 25 each from S1, S2, S4 (75), not 20 from each of four strata: S3 is a
  census with no reserve to replace discarded pilot items.
- Dropped the "outline covers two or more houses" flag: it can't be judged blind.
- Cells: count + note instead of clicking each house; centre-inside rule; 1.2 m.
- Bootstrap is finite-population corrected (rescaled).
- Every photo is NAIP 2023 (the tile fetcher otherwise takes the newest year).

## 9. Amendments after the sample was drawn

| Version | Date | Change | Affects the sample? |
|---|---|---|---|
| v1.1 | 2026-11-05 | Second interpreter named: Monica (§2, §7) | No (decided before any labelling) |
| v1.2 | 2026-11-06 | Scope extended to Maryland: strata S7, S8, S6W added, S5 turned on in both regions, list-frame total + separately reported residual, exact bounds for constant strata (§10). Made before any label was recorded (`accuracy_v1/` held only `frame.geojson` and `sample_meta.json`) | No: v1.1 frame, sample, seed and reserve unchanged; new strata drawn separately |

Each amendment's SHA-256 is added to `protocol_amendments` in `sample_meta.json`,
so notebook 14 accepts it without the protocol warning.

## 10. v1.2: statewide scope (approved 2026-11-06, before any label)

Why: the paper's claim must be about Maryland, not only the Eastern Shore.
v1.1 measured houses, recall and roof on the Eastern Shore only. Design review
and its evidence: `docs/TASK1_PROTOCOL_v1.2_PROPOSAL.md`. Where this section
differs from §1–§7, this section governs. Everything not named here is
unchanged: response design (§2), labels, interpreters, calibration, pilot and
kappa gate (S1/S2/S4), adjudication, and the v1.1 frame, sample, seed
20261105 and reserve.

### 10.1 What we estimate

| Parameter | Definition |
|---|---|
| Houses on a list, T̂_L | Standing poultry houses in Maryland in 2023 that are on at least one list: the map, the USGS tracing, the notebook-05 detector output west of the Bay, a western poultry permit cell (S8), or the footprint frame (S5) |
| Residual, R | Standing houses on none of those lists, reported on its own line (10.5), never inside the CI of T̂_L |
| Recall (Maryland) | Correct map houses ÷ T̂_L; sensitivity row with T̂_L + R at its upper bound |
| Roof (Maryland) | Roof of the houses in T̂_L, km²; residual roof reported separately |
| Precision | As v1.1 (statewide and Eastern Shore) |

The Eastern Shore figures are still reported on their own (same estimators,
restricted to the 9 counties).

### 10.2 New and changed strata

All new strata are west of the Bay (county = one of the 15 counties not in
`C.EASTERN_SHORE`), except S5, which runs in both regions.

| Stratum | Frame | n | Labelled as |
|---|---|---|---|
| S7 | Notebook-05 detections in western counties (`county_buildings` of each `county_<name>/buildings.geojson`) whose outline touches no release_v1 outline: 359 rejected + 8 unsure in notebook 07 = 367 expected | all (census) | object (§2) |
| S8 | 1 km cells (grid of §3) with centre in a western county, intersecting a 1 km buffer of a western MDE poultry permit point (`data/reference/mde_afo_registry_snapshot.json`, SHA-256 recorded; types `chickens_not_laying_hens`, `laying_hens_dry_manure`, `turkeys`, `ducks_liquid_manure`: 6 permits, ~49 cells) | all (census) | cell |
| S6W-A | Western cells not in S8 intersecting a western notebook-05 detection or release outline | 40 | cell |
| S6W-B | Western cells not in S8 or S6W-A within 1 km of one | 60 | cell |
| S5 (on) | Microsoft US Building Footprints, Maryland file (ODbL; SHA-256 and per-feature capture dates recorded): minimum rotated rectangle length ≥ 60 m and length/width ≥ 4, touching no release outline, no traced polygon and (west) no notebook-05 detection. Two sub-strata: S5-ES and S5-W | per sub-stratum: all if ≤ 150; else 150 (ES) / 200 (W) | object (§2) |

Western cells farther than 1 km from every known building are **not sampled**:
with a feasible n their zero-hit bound is meaningless (proposal §3.1). Houses
there count only through S5 or the residual.

Allocation: proportional by county with at least 5 per county (as §3).
Each new stratum is drawn as a full random permutation per county with seed
**20261106**: first n = sample, rest = reserve (cells beyond n: not drawn). No
pilot or calibration items come from the new strata. The draw writes
`Task1_results/accuracy_v1/frame_v1.2.geojson` and `sample_meta_v1.2.json`
(SHA-256, footprint and registry SHA-256, this protocol's SHA-256);
`frame.geojson` and `sample_meta.json` are not rewritten. Notebook 14 refuses to
draw the new strata again once `frame_v1.2.geojson` exists, and refuses to draw
them at all if any label exists for an S5/S7/S8/S6W key.

Phases: the new objects (S5, S7) are labelled in a phase `v1.2 objects` after
`main`; the new cells (S8, S6W) in `v1.2 cells` after `cells`. Same blind
photos, each interpreter's own random order, strata mixed.

### 10.3 Response design additions

- **Known buildings on every cell photo (S6, S6W, S8):** release outlines ∪
  traced polygons ∪ western notebook-05 detections ∪ S5 frame footprints, one
  neutral colour. The count is houses with their centre in the square that have
  **none** of these. (This changes the S6 photo from v1.1 by adding the last
  two layers, so a house is never counted both as an object and in a cell.)
- **Poultry building outside §2's dimensions** (e.g. a wide or multi-storey
  layer house, a short duck house): label `not a house`, note
  `poultry, other form`. Counted in a separate row; not in T̂_L.
- S7 items were all seen by UA in notebook 07 (as S2). Monica's agreement with
  the adjudicated label is reported for S7 separately.

### 10.4 Estimators (list frames)

y = 1 if adjudicated `house`; cells give a count.

- Correct map houses: Ĉ_ES (S1, S2, S3-ES), C_W (S3-west, census).
- Missed traced houses standing: M̂ (S4).
- Western detector houses not on the map: R̂_W = Σ y over S7 (census).
- Footprint houses: F̂_ES, F̂_W = Σ N_h p̂_h over S5 sub-strata × county.
- Permit-cell houses: P_W = Σ counts over S8 (census).
- **T̂_L = Ĉ_ES + C_W + M̂ + R̂_W + F̂_ES + F̂_W + P_W.**
- Recall (Maryland) = (Ĉ_ES + C_W) / T̂_L; recall (Eastern Shore) =
  Ĉ_ES / (Ĉ_ES + M̂ + F̂_ES).
- Roof (Maryland) = Σ N_h·mean(area·y) over S1–S3 (outline area) + S4 traced
  area × k + S7 rectangle area (minimum rotated rectangle, as release step 1) +
  S5 footprint area × k_f + P_W × mean roof of standing western houses (S3-west
  + S7; if none, of S4 houses). k_f = release outline area ÷ footprint area on
  S1 houses that have a footprint (geometry only, recorded).
- CIs as §5 (rescaled stratified bootstrap, seed recorded). **Constant strata:**
  where every sampled y in a stratum is equal (all houses or none), the CI side
  that stratum cannot move is recomputed with that stratum at its exact
  one-sided 95% bound (Clopper-Pearson for objects; for cells N·(1 − 0.05^(1/n))
  positive cells) and the others at their point estimates; the wider interval is
  reported. This implements §5's sentence, which v1.1 code did not.
- T2/T3 (±5%, PAPER_STANDARD) apply to T̂_L and roof (Maryland).

### 10.5 Residual: houses on no list

Reported on its own line, two ways, never added into T̂_L's CI:

1. **Design (cells).** Ŷ = Σ_g (N_g / n_g) Σ counts over S6A/B/C and
   S6W-A/B, with the bootstrap CI, and for each zero-hit cell stratum its exact
   one-sided 95% bound in cells, converted to houses with the mean count per
   positive cell over all positive cells in S6, S6W and S8 (3 if there are
   none, stated as an assumption). Unsampled western far cells: not covered;
   said so.
2. **Model (capture rates).** q_ES = share of the 3,040 traced houses touched
   by neither a footprint nor a release outline; q_W = share touched by neither
   a footprint nor a step-0 published-model detection (both pure geometry, no
   labels; binomial 95% CI). R_x = L_x · q_x / (1 − q_x), where L_x = houses in
   T̂_L of region x not on the tracing (ES: Ĉ in S2 + S3-ES + F̂_ES; west: all).
   Assumes traced houses are representative of houses off the tracing, and,
   for the west, that Eastern Shore capture rates transfer. Both assumptions
   are stated with the number.

### 10.6 Decisions changed

- §7.3 S5 footprints: **on**, both regions (approved with v1.2, 2026-11-06;
  Microsoft Maryland file, ~400 MB, ODbL; attribution and share-alike apply to
  any derived database we publish).
- NAIP coverage note: in Calvert, Anne Arundel, St. Mary's, Harford, Allegany
  and Garrett some notebook-05 tiles mosaic 2017–2022 items where the newest
  photo does not cover the tile. Labels still use 2023 only (§2); the affected
  tiles are listed in the run record and reported.

### 10.7 Labelling time (per interpreter, rough)

S7 367 × 15 s ≈ 1.5 h; S5 ≤ 350 × 15 s ≈ 1.4 h; S8 ~49 + S6W 100 cells × 40 s
≈ 1.7 h. About 4.6 h added: ~12.5 h each in total.

### 10.8 What v1.2 still cannot support

A CI that includes houses on no list; houses in western cells farther than
1 km from any known building other than through S5 or the model residual;
per-county western estimates; poultry buildings outside §2's dimensions;
stocking (idle houses count as standing).
