# GEO-ANOM: research audit and finishing plan (2026-11-05)

Source of truth for project status from 2026-11-05. Editable copy (Claude Doc):
https://claude.ai/artifact/K5qtWvzwH5yMabAK2CknMt. If they disagree, the newer
dated section of `docs/NEXT_SESSION.md` wins.

GEO-ANOM has a reproducible statewide poultry-house map and a draft nutrient
balance, ahead of the LOI schedule. But two headline accuracy numbers rest on
informal visual checks, the lagoon half of Task 1 was not delivered, and the
detection method is adapted rather than new. The right finish is a design-based
accuracy assessment, an externally validated nutrient balance, and a paper
framed around house-scale supply and demand, not detection novelty.

## Problem statement

**What the LOI asked (2026).** Maryland's nutrient planning relies on
county-level data and outdated farm registries. GEO-ANOM would (1) detect AFOs
(poultry houses and waste lagoons) with GeoAI; (2) map crop nutrient demand from
the USDA Cropland Data Layer into a Nutrient Balance Map; and (3) site anaerobic
digestion and biochar facilities with a location-allocation model and an LCA.
Deliverables are due June 2027.

**What the evidence now supports.** The work has become a poultry study:
poultry is most of the Eastern Shore's manure, and the poultry detector is the
part that works. The defensible research question:

> How accurately can an open, published poultry-house detector, repaired with a
> foundation model (SAM), map 2023 poultry production across Maryland when
> accuracy is measured with a design-based sample? And how does a house-level
> supply estimate change where litter exceeds what cropland can use, compared
> with county-level and permit-registry approaches?

1. **RQ1, supply:** the house map's accuracy and total roof area, each with a
   95% confidence interval from a probability sample.
2. **RQ2, balance:** litter supply vs crop need on a 5 km grid and by county,
   with uncertainty, checked against what MDA's Manure Transport Program moved.
3. **RQ3, value added (LOI objective 2):** how much the surplus map changes when
   county averages or permit locations are replaced with mapped houses.

Task 3 (siting and LCA) builds on RQ2 and stays as the LOI describes it.

## Progress against the LOI

| LOI item | Promised | Delivered | Status |
|---|---|---|---|
| Objective 1: detect AFOs | Poultry houses and waste lagoons | Poultry houses statewide: 2,833 mapped, 6.98 km² roof. Lagoons: only 1 of 7 recorded lagoons was real on imagery; no lagoon map | Partial |
| Benchmark labeled dataset | Labeled AFO dataset for Maryland | 719 detections labeled by one reviewer; training chips (nb 09); USGS 2016/17 tracing (existing, not ours) | Partial: needs protocol + second reviewer |
| Methods | AlphaEarth and SAM with Landsat/Sentinel | NAIP 0.6 m + published U-Net (Robinson et al.) + SAM repair; AlphaEarth tested, not used | Changed: houses ~15 m wide, too small for 10–30 m imagery |
| Objective 2: quantify gains of GeoAI | Efficiency gain over current methods | Pieces only: registry misses ~1/5 of Somerset's houses; 81 houses >1 km from any permit | Not started as an analysis |
| Task 2: Nutrient Balance Map (Jan–Mar) | Crop-specific need from CDL, with rotations | Draft v1 (nb 13): CDL 2023 only, default coefficients, county + 5 km grid, 2,000-run uncertainty | Ahead, draft |
| Task 3: siting and LCA (Apr–Jun) | Location-allocation, SimaPro ReCiPe 2016 | Not started | On schedule |

## Results and confidence

Objective: the map itself and measurements against the USGS tracing. Not yet
defensible: every number that depends on looking at photos (one person, no
written protocol).

| Result | Number | How measured | Confidence |
|---|---|---|---|
| Houses mapped | 2,833 houses, 6.98 km² roof | Frozen release_v1, SHA-256; reruns identical | High that this is what the map says |
| Recall (Eastern Shore) | 80.5% of 3,040 traced houses | Overlap with USGS tracing (Soroka & Duren 2016/17) | Medium-high; tracing is 2016/17, photos 2023 |
| Precision vs tracing | 88.2% | Outline touches a traced house | High, as a lower bound |
| Precision incl. checked houses | 97.0% | 719 detections, one reviewer; 40 controls 100% | **Not defensible yet** |
| Missed houses still standing | 21 of 24 | Informal look, earlier session, not random | **Low; must be redone** |
| Corrected roof | 7.79 km² (7.41–7.86) | Missed footprints × 0.96 × still-standing share | Low-medium; inherits 21/24 |
| Birds on hand from roof | 42.6–84.4 M vs Census 59.5 M, MDE 69.2 M | Literature stocking/occupancy ranges | Shows scale + county pattern (r 0.96–0.99), **not completeness** |
| County ranking | Spearman 1.00 from step 2 on | Internal comparison across steps | High |
| Surplus counties | Wicomico, Somerset, Worcester in 100% of runs | Monte Carlo on default coefficients | Medium for which counties, low for tons |
| Statewide room for litter | −444 kt | Same model; ignores other manure, biosolids, fertilizer | Low; do not quote |

## Credibility record

Five stated results were withdrawn. Same pattern each time: a number was
produced faster than it was checked.

| Date | Claimed | Turned out |
|---|---|---|
| 2026-11-04 | Most missed houses torn down; bird check proves map complete | Record said 21/24 still stand; bird check too loose for completeness |
| 2026-10-07 | Counts and accuracy up to that date | Tile georeferencing bug shifted 219 of 417 tiles; all earlier numbers superseded |
| 2026-10-05 | Broiler N from project config | Coefficient gave 13.8× the AWTF statewide broiler N |
| 2026-09-23 | 3 confirmed + 2 corroborated lagoons | Only 1 of 7 recorded lagoons was real |
| 2026-09-21 | Daily cloud routine running | Had failed silently for 6 days |

**Rule from now on:** no number goes into a summary until its measurement is
written down (sample, protocol, reviewers, uncertainty) and saved with the release.

## Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| Reproducible: numbered notebooks, frozen release with SHA-256, tests | Visual checks by one person with no protocol (97%, 21/24) |
| Scored against an independent reference (USGS, 3,040 houses) at every step | That reference is 2016/17; photos are 2023 |
| Honest ladder; failed ideas reported (road rule, fine-tuning) | Detection method adapted, not new |
| Statewide coverage, all 24 counties | Lagoons, dairy, swine, beef not delivered |
| Task 2 runs from one coefficient sheet a domain expert can edit | Coefficients unreviewed; other sources, rotations, external validation missing |
| Ahead of LOI schedule | Little PI/co-PI input so far; Rafi not yet working on it |
| Farm-level data kept off the public repo | House-level data can't be released openly without an agreement |

## Impact

Applied, not methodological: an up-to-date, house-level supply map tied to crop
demand, with honest uncertainty.

**Can claim, once the accuracy assessment is done:** first 2023 statewide
house-level reproducible poultry roof map for Maryland with design-based
accuracy and a CI on total roof; a sub-county litter vs cropland balance with
uncertainty, checked against transport records; a measured comparison of what
county averages and permit locations get wrong (LOI objective 2); open code.

**Cannot claim:** a new detection method; "the first high-resolution map of
poultry houses" (USGS traced them in 2016/17); a complete AFO inventory or any
lagoon mapping; policy-ready nutrient tons before Rafi's review.

**Users:** MDA (target the Manure Transport Program), Task 3 (site digesters and
biochar plants), Extension (county planning). Farms below the CAFO threshold are
legal; the map is a planning tool, not an enforcement list.

## The right way to finish

Stop improving the detector. Measure it properly, validate the balance against
real records, then build Task 3. Each phase ends at a gate.

**Phase 1: Task 1 accuracy assessment by design (Nov–Dec 2026).** Visual
interpretation is the standard reference in remote sensing only with a
probability sample, a written protocol and independent interpreters
(good-practice guidance: Olofsson et al. 2014, Remote Sensing of Environment —
cited from memory, verify).

1. Write the interpretation protocol: what counts as a standing poultry house in
   2023, which imagery (NAIP 2023 + dated Google Earth), how to record "unsure".
2. Stratified random samples by county:
   - ~150 missed traced houses (replaces 21/24);
   - ~150 detections not on the tracing (replaces the single-reviewer 97%);
   - ~100 random 1 km cells in poultry counties, every house counted (catches
     houses neither USGS nor the model has).
3. Two interpreters label every sample blind and independently (Umesh + Jenny Ha
   or Pradeep). Report Cohen's kappa, then adjudicate.
4. Estimate recall, precision and total roof with stratified estimators and 95% CIs.
5. Cross-check missed houses against an independent automated source (e.g.
   Microsoft building footprints).
6. Ask Prof. Nakalembe: lagoons closed out, or a short separate step?

*Gate:* kappa ≥ 0.8, and every Task 1 number carries a CI from this sample.

**Phase 2: Task 2 with Dr. Lansing's team (Dec 2026–Feb 2027).**
1. Rafi reviews the coefficient sheet, starting with the five biggest levers.
2. Add other nutrient sources by county: dairy/other manure, biosolids, fertilizer.
3. Multi-year CDL for rotations (LOI).
4. Feed in the Phase 1 roof estimate with its interval.
5. Validate county balance against MDA Manure Transport Program tons and DLLC 2019.

*Gate:* surplus counties agree in direction with where litter is actually shipped out.

**Phase 3: value added and paper 1 (Feb–Mar 2027).**
1. Rerun the balance three ways: county averages (LOI Figure 1 approach),
   permit-registry locations, mapped houses. Measure how much the surplus map
   changes (LOI objective 2).
2. Draft the Task 1+2 paper for an applied venue (J. Environmental Management,
   Agricultural Systems, an ASABE journal).

*Gate:* PIs approve the draft.

**Phase 4: Task 3 and release (Apr–Jun 2027).**
1. Location-allocation siting on the Task 2 grid (Umesh); SimaPro LCA and
   facility parameters (Rafi).
2. Release county and 5 km outputs on Zenodo, code on GitHub; house-level data
   only by agreement.
3. Final report by June 2027.
