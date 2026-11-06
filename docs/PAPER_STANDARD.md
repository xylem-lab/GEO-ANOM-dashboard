# Task 1 paper: research standard (draft v0.2, 2026-11-06, for approval)

Names: **map v1** = release_v1 (frozen, never edited); **verification v1.1** =
the accuracy assessment of map v1 (`docs/TASK1_ACCURACY_PROTOCOL.md`); **map v2**
= an improved map, only if verification v1.1 shows it's needed.

Status: **draft, not approved.** Once approved it is frozen: its SHA-256 goes
into `sample_meta.json` and the paper's manifest, and it is not edited after
that. Later changes get a new version, a date, a reason, and a note saying
whether anyone had seen labels or estimates at the time (§10).

Checked on 2026-11-05: `Task1_results/accuracy_v1/` holds only `frame.geojson`
and `sample_meta.json`. **No labels exist yet**, so this standard is set before
any accuracy result.

## 0. How this relates to the protocol

- `docs/TASK1_ACCURACY_PROTOCOL.md` (verification protocol v1.1, frozen 2026-11-06) governs **how** we measure:
  frames, sample, labels, interpreters, adjudication, estimators. This document
  does not change any of that.
- This document governs **what the paper may claim** from those measurements:
  primary measures, success thresholds, what we write if a threshold is missed,
  error analysis, reproducibility and the claims check.
- Anything reported in the paper that is not listed here is labelled
  *exploratory* in the text.

### Changes from the brief, and why

1. **Scope of the claim (v0.1).** Verification protocol v1.1 (frozen 2026-11-06)
   makes houses, recall and roof statewide over **list frames** (map, tracing,
   western detector output, western permit cells, footprints). Houses on no
   list are a separate residual line with its own bound, not inside the CI.
   So the claim is "Maryland had N houses on these lists (CI), plus at most R
   on none", with developed land west of the Bay assumed to hold no poultry
   houses (a 30-item spot check, protocol §4). (v0 scoped it to the Eastern
   Shore because the first protocol draft measured
   nothing west of the Bay except precision.) §1.
2. **Per-county figures are secondary.** The sample has as few as 5 items per
   county in some strata. County CIs will be wide; no threshold applies to them.
3. **Significance test.** McNemar assumes a simple random sample, and our
   sample is stratified with unequal weights. The primary test is the
   design-based paired difference (bootstrap CI). McNemar on the 3,040 traced
   houses is reported as a secondary, descriptive comparison. §3, T4.
4. **The published model cannot yet be scored on the 2023 sample.** Notebook 14
   samples only release_v1's outlines and the traced houses it misses. Its
   recall can be estimated as a subset of the same sample, but its precision
   needs its own outlines that are not in release_v1 in the frame. Decision D1.
5. **Kappa with skewed classes.** In S1 almost every item will be a house; kappa
   can then be low even when the interpreters almost always agree. The
   threshold applies to the pooled kappa across object strata, reported with
   raw agreement and prevalence.
6. **The roof CI covers sampling error only.** The outline-to-roof ratio
   (k = 0.963) and the outline geometry add error that the bootstrap does not
   see. They are reported separately (§4.3), not hidden inside the CI.

## 1. The claim

Template (gaps filled only from frozen notebook 14 outputs):

> On 2023 NAIP imagery, Maryland had [NB14:T_L] standing poultry houses
> (95% CI [NB14:T_L_lo]–[NB14:T_L_hi]) on the map, the 2016/17 tracing, the
> detector's candidates, permit sites or a building-footprint inventory,
> covering [NB14:roof] km² of roof (95% CI [NB14:roof_lo]–[NB14:roof_hi]).
> Houses on none of these are estimated at [NB14:R] (95% upper bound
> [NB14:R_u]). [NB14:T_west] of the houses are west of the Chesapeake Bay.
> Developed land west of the Bay is assumed to hold no poultry houses
> ([NB14:S5WD_found] found in a spot check of 30 footprint candidates there).
> The map finds [NB14:recall] of them (95% CI […]); [NB14:prec_all] of the
> 2,833 mapped outlines sit on a standing poultry house (95% CI […]).

The Eastern Shore figures are reported as well (same estimators, 9 counties).

Litter tons go in only if the coefficient gate in §8 is passed. Otherwise the
paper stops at roof area and says so in the abstract.

"In 2023" means the NAIP 2023 flight date of each site (the flights span
several weeks; the range is reported).

## 2. Measures

### 2.1 Primary (all with 95% CIs; estimators from protocol §5)

| ID | Measure | Scope | Unit of evidence |
|---|---|---|---|
| P1 | Houses on a list, T̂_L (protocol §10.4) | Maryland (and Eastern Shore) | S1–S5, S7, S8 |
| P2 | Roof of the houses in T̂_L, km² | Maryland (and Eastern Shore) | Same, with outline/traced/footprint areas |
| P3 | Precision = Ĉ / mapped outlines | Statewide (2,833) and Eastern Shore (2,807) | S1–S3 |
| P4 | Recall = (Ĉ_ES + C_W) / T̂_L | Maryland (and Eastern Shore) | S1–S5, S7, S8 |
| P6 | Residual: houses on no list, design (cells) and model (capture rates), with bounds (protocol §10.5) | Maryland | S6, S6W, S8; tracing geometry |
| P5 | Cohen's kappa, house vs not, before adjudication | Pooled S1–S4 sampled items (pilot + main), unweighted | Two interpreters' raw labels |

### 2.2 Secondary (reported, no thresholds)

- Precision and recall per county, with CIs (wide where n is small; said so).
- Share of houses per stratum (Wilson and exact CIs).
- 5-class kappa; per-stratum kappa with raw agreement and prevalence; cell
  agreement (exact agreement and linear-weighted kappa on counts 0–6+).
- Monica's labels vs the adjudicated labels (so agreement doesn't rest on UA,
  who saw S2 in notebook 07).
- Recall 0.805 and precision 0.882 against the 2016/17 tracing (census,
  unchanged).
- The published model's recall on the same sample (and precision if D1 is
  approved).
- Protocol sensitivity rows: `unsure` = house; `under construction` = house;
  each interpreter alone.
- Variance share per stratum for P1 and P2 (which stratum makes the CI wide).

### 2.3 Not measured, stated as limits

Houses on no list beyond what the residual line bounds (in particular western
cells farther than 1 km from any known building); poultry buildings outside the
protocol's dimensions (counted, not estimated); per-county western figures;
lagoons; dairy, swine and beef; whether a house was stocked (idle houses count
as standing).

## 3. Success thresholds, and what we write if one is missed

Thresholds apply to **measurement quality and to the improvement claim**, not
to the accuracy values themselves. Precision and recall are reported as they
come out; there is no "good enough" bar on them.

| ID | Threshold | How it is checked | If met, we write | If missed, we write |
|---|---|---|---|---|
| T1 | κ ≥ 0.80 (P5, point estimate; CI reported) | Notebook 14 §7, pre-adjudication labels | "Two independent interpreters agreed strongly (κ = […], 95% CI […])." | "Agreement was κ = […], below the 0.8 we set in advance. Estimates use adjudicated labels; we report each interpreter's estimate and treat their spread as extra uncertainty." The benchmark is described as having moderate agreement, not as a reference standard. |
| T2 | CI half-width of T̂ ≤ 5% of T̂ | Notebook 14 §9 | "±[…]%" | "The CI is ±[…]%, wider than the 5% we aimed for, mainly from stratum [variance table]." |
| T3 | CI half-width of roof ≤ 5% of roof | Notebook 14 §9 | as T2 | as T2 |
| T4a | Recall gain of release_v1 over the published model, on the 2023 sample: 95% paired bootstrap CI excludes 0 | Same sampled units scored for both maps (resampled together) | "SAM repair and tone matching raised recall from […] to […] (gain […], 95% CI […])." | "Against the 2016/17 tracing recall rose from 0.670 to 0.805, but on the 2023 sample the gain was [not distinguishable from zero / smaller than interpreter disagreement]." The ladder is then presented as a comparison against the tracing only. |
| T4b | Lower CI bound of that gain > interpreter spread, defined as \|recall(UA alone) − recall(Monica alone)\| for release_v1 | Sensitivity rows | (part of T4a) | (part of T4a) |
| T4c | ~~Precision does not fall by more than 2 points from the published model to release_v1~~ Not tested: D1 left out (2026-11-06) | Same as T4a | "…with no loss of precision" | "Recall rose, but precision fell by […]" |

**Notes on T2 and T3, written down now so they are not a surprise later.**
These are design facts, not results:
- The S6 cell weights are large: each sampled cell in sub-stratum B stands for
  2,748 / 150 ≈ 18 cells, and in C for 5,476 / 100 ≈ 55. One unmapped house
  counted in a C cell adds ~55 houses to T̂ and widens its CI a lot.
- (v0.1) T2/T3 apply to the list-frame total T̂_L and its roof, not to the
  residual. Reason: a zero-hit cell stratum has an exact upper bound of
  hundreds of houses (S6C alone: ~160 cells), so no feasible cell sample can
  give ±5% on a total that includes houses on no list. The residual is
  reported next to the total with its bound (proposal §3.1).
- So T2/T3 can be missed even if the map is good. If they are, the variance
  table says which stratum is responsible.

**Allowed once: a variance-driven top-up (decision D2).** If T2 or T3 is missed,
we may label more items from the pre-drawn reserve of the stratum with the
largest variance share, in reserve order, up to a size fixed before looking at
its labels. The decision rests on the variance table only, never on which way
the estimate moves, and the paper reports it as a two-phase sample. No other
added sampling after results are seen.

**The pilot gate stays as in the protocol** (κ ≥ 0.8 on the 75 pilot items, or
protocol v2 and new pilot items from the reserve). A failed pilot is reported
in the paper.

## 4. Error analysis (categories fixed now)

Every category gets a count in the sample, a weighted estimate with a 95% CI
where n allows, and example photos for the gallery (no farm names,
coordinates rounded or removed, no permit IDs).

### 4.1 Wrong outlines (S1–S3 items adjudicated *not* `house`)

Coded from the label and the interpreter's note into exactly one of:

| Code | Meaning |
|---|---|
| FP-livestock | Other livestock barn (dairy free-stall, other) |
| FP-building | Other building: warehouse, shed, greenhouse/hoop house |
| FP-nonbuilding | Not a building: road, slab, sand, field |
| FP-gone | Demolished or roofless house (a slab where a house was) |
| FP-construction | House under construction |
| FP-unsure | Stayed `unsure` after adjudication |

UA assigns the code during adjudication for every *not* item, Monica checks all
of them, disagreements go to the adjudicator. Codes are assigned before the
estimates in notebook 14 §9 are run.

### 4.2 Missed houses (S4 items adjudicated `house`, and S6 counts)

Assigned by rule from recorded data, not by judgement:

| Code | Rule |
|---|---|
| M-dark | The site's 2023 flight is one of the flights tone-matched in notebook 08 (list fixed from `Task1_results/experiments/tone_match_2021/` before scoring) |
| M-small | Traced footprint below the median footprint of found traced houses in release_v1 (threshold computed from the release, not the sample) |
| M-pipeline | Stage that lost it: no candidate / piece rejected by the length filter / merged with a neighbour, **if** recoverable from the release_v1 run records; otherwise reported as not recoverable |
| M-both | Counted in S6 (found by neither the map nor the tracing) |

Codes can overlap (a house can be dark and small); the table shows overlaps.

### 4.3 Roof measurement error (S1 houses confirmed `house`)

- Ratio of outline area to traced polygon area: median, interquartile range,
  share below 0.8 ("partial roof").
- The roof estimate is reported with k = 0.963 and, as a sensitivity row, with
  k at its 10th and 90th percentile over found houses. This is reported next to
  the sampling CI, not folded into it.

### 4.4 Reference staleness (feeds contribution 3)

- New builds: S2 + S3 items adjudicated `house` (standing in 2023, not in the
  2016/17 tracing).
- Gone: S4 + S1 items adjudicated `gone`.

### 4.5 Recall by flight date

Recall per NAIP 2023 flight (date and mean brightness), descriptive. Flights
and counties overlap, so this is not presented as a causal effect.

## 5. Contribution 3: how wrong tracing-based scores are

Reported whichever way it comes out, in one table:

| | Against 2016/17 tracing | Design-based, 2023 | Difference (95% CI) |
|---|---|---|---|
| Recall | 0.805 | [NB14] | [NB14] |
| Precision (Eastern Shore) | 0.882 | [NB14] | [NB14] |

with the parts that explain the difference: new builds (§4.4), traced houses
gone, houses missed by both (Ŷ). If the difference's CI includes 0, we say the
tracing gave an unbiased score here and drop the "lesson" framing.

## 6. Contribution 4: the ladder

The ladder (published → rectangles → brightened → SAM → checked) stays scored
against the tracing, as in notebook 11 (census of 3,040 houses, no CI needed for
sampling, but the reference is 2016/17). Only the two ends (published model and
release_v1) are scored on the 2023 sample (T4). Middle steps are not, and the
text says so. The fine-tuned model and the road rule are reported as tested and
not adopted, with the notebook 10/11 numbers.

## 7. Reproducibility and the claims check

### 7.1 What is frozen and recorded

`Task1_results/paper_v1/MANIFEST.json` (drive), with an anonymous copy in git
at `docs/paper/manifest_public.json` (hashes and counts only):

- code commit of notebooks 11, 12, 14 runs;
- model checkpoint SHA-256 (published U-Net; SAM vit_b);
- release_v1 MANIFEST SHA-256; USGS tracing SHA-256;
- protocol SHA-256 (v1.1 + any amendments); this standard's SHA-256;
- `frame.geojson` SHA-256 (d649666f…), seed 20261105, bootstrap seed;
- NAIP 2023 item IDs (from run_meta), package versions;
- label files and adjudication log SHA-256 (drive only);
- estimates table SHA-256.

Rerun check: Restart → Run All of notebook 14 on the frozen labels gives the
same estimates table (same SHA-256).

### 7.2 Claims checklist (`docs/paper/claims.csv`)

One row per number or factual claim in the manuscript:

`claim_id, section, text as written, value, source (notebook + section/cell id, or release file + field), source SHA-256, checked_by, date_checked`

Rules:
- A number with no row is taken out of the text.
- "First", "novel", "only", "largest" need a row whose source is a checked
  reference (DOI or official page) showing it holds. Default: don't use them.
- Never claim: a new method; the first map of these houses (USGS traced them in
  2016/17); lagoon detection; a complete AFO inventory; N or P totals.
- Vocabulary: manure and litter are a resource; farms below the CAFO threshold
  are legal; the map is a planning tool, not an enforcement list.
- Two weeks before the submission deadline: every row re-checked against the
  frozen files by someone other than the person who wrote the section.

## 8. Litter gate

Litter tons appear only if all of these hold before the internal draft goes to
the PIs:
1. Rafian Aziz has reviewed the coefficient sheet (dated, version recorded);
2. Dr. Lansing approves showing litter tons;
3. the tons are computed from P2 with its CI, propagated together with the
   coefficient ranges (notebook 13 Monte Carlo), and shown as a range.

N and P are never shown. If the gate is not passed, the paper says: "We
estimate roof area; converting it to litter needs coefficients that are under
expert review."

## 9. Decisions needed before this is frozen

| ID | Decision | My recommendation | Who | Deadline |
|---|---|---|---|---|
| D1 | ~~Add a stratum of published-model outlines not in release_v1 on the Eastern Shore~~ → **not included in verification v1.1**: the published model is compared with map v1 on recall only (T4a/T4b); T4c (precision) is not tested | Decided by the user 2026-11-06: "Leave it out" | You | Done |
| D2 | Allow the one-time variance-driven top-up in §3 | Yes | You | Now |
| D3 | Thresholds as in §3 (κ 0.8, ±5%, 2-point precision margin) | Yes | You | Now |
| D4 | ~~Claim scoped to the Eastern Shore~~ → statewide list-frame claim + residual line (verification v1.1) | Decided by the user 2026-11-06; tell Prof. Nakalembe | You, then Prof. Nakalembe | Done |

## 10. Versions

| Version | Date | Change | Labels or estimates seen? |
|---|---|---|---|
| v0 | 2026-11-05 | Draft for approval | No (no labels exist) |
| v0.1 | 2026-11-06 | Claim, P1/P2/P4, new P6, §2.3, T2/T3 note and D4 follow protocol draft "v1.2" (statewide list frames + residual) | No (no labels exist) |
| v0.2 | 2026-11-06 | Naming: map v1 / verification v1.1 / map v2; claim adds the developed-land assumption (S5WD); D1 decided: left out | No (no labels exist) |
