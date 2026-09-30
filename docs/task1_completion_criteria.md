# Task 1: What "Scientifically Done" Means, and How to Get There

Written 2026-09-30, after the Task 1 pipeline audit (`task1_pipeline` artifact) and a
literature scan for how other groups have handled the same sub-problems. This is a
targeted search grounded in the actual gaps found this project, not a systematic
review — read the primary papers before committing to a method, not just this
summary.

**Update, same day**: the architectural fix under criterion 3 (supply
calculation must not require a registry lookup) is now implemented, not
just planned — see §5.

## 1. What "done" actually requires

Three separate criteria, from three separate sources — Task 1 isn't finished until
all three are met:

| # | Criterion | Source | Status |
|---|---|---|---|
| 1 | Detect and map AFO features (poultry houses + lagoons, minimum) | Proposal, Objective 1 | Partially — buildings work moderately, lagoons mostly don't (see `task1_pipeline`) |
| 2 | Quantify the efficiency gain of the GeoAI approach vs. the county-level baseline | Proposal, Objective 2 | **Not started.** No comparison metric exists anywhere in the codebase. |
| 3 | Show the model works on facilities it wasn't trained on, not just facilities already in the registry | Catherine Nakalembe, 2026-09-09 meeting | **Partially implemented.** The pipeline no longer *requires* a registry match to produce a poultry supply number (§5) — but there's still no independent (non-registry) dataset to validate that number against, which is the other half of this criterion. |

Criterion 3 is the one this session has been circling — it's not an extra nice-to-have,
it's a named requirement from the PI, and nothing currently satisfies it.

## 2. Metrics, matched to method, per criterion

### Criterion 1 — detection quality

- **Building detection**: precision/recall/F1 against a held-out hand-labeled set,
  the same protocol Robinson et al. use in the paper the current U-Net is built on —
  [Mapping Industrial Poultry Operations at Scale with Deep Learning and Aerial
  Imagery](https://arxiv.org/pdf/2112.10988) (trained on USDA NAIP 1m imagery, the
  same imagery class as Planetary Computer/MD iMAP). This project already has this
  partly — the 2016/17 Soroka & Duren ground truth — but it's only been used for
  threshold calibration, never reported as a clean held-out precision/recall number.
- **Lagoon detection**: the same P/R/F1 framing, but right now there's no clean
  benchmark — the "~1/7 confirmed real" figure is a small manual audit, not a
  reportable metric. [CAFOSat](https://arxiv.org/pdf/2606.00548) and
  [PRISM-CAFO](https://arxiv.org/pdf/2601.11451) both report infrastructure-level
  precision/recall on multi-state datasets — their evaluation protocol is a direct
  template.
- **Species-specific structures**: a national-scale cattle feedlot detector using
  YOLO on NAIP imagery exists and reports per-facility metrics — [National-scale open
  cattle feedlot detection using deep learning and high-resolution aerial
  images](https://www.sciencedirect.com/science/article/pii/S0048969726001117) — directly
  comparable to the beef-detection gap found this session.

### Criterion 2 — efficiency gain vs. county-level baseline

No paper found addresses this directly for this domain — it needs to be defined
before it can be measured. A defensible version: spatial resolution improvement
(farm-level vs. county-level) × count/area accuracy against the same 2016/17 ground
truth, reported as "this many more locatable facilities per county than the NASS/
USDA county aggregate Stephanie's team already uses." This is a scoping conversation
with Catherine and Stephanie, not an engineering task — the metric doesn't exist yet
because nobody has picked one.

### Criterion 3 — validity beyond the registry

This is the one with real methodological literature behind it, and it reframes the
problem usefully:

- **The core issue is structurally a Positive-Unlabeled (PU) learning problem**: the
  registry gives confirmed positives, but everything else isn't "confirmed negative,"
  it's unlabeled — could be a real, unregistered facility, or could be nothing.
  Treating unlabeled tiles as negatives (which is what a standard precision/recall
  calculation implicitly does) systematically punishes the model for finding real,
  unregistered farms. [Object Detection as a Positive-Unlabeled
  Problem](https://arxiv.org/pdf/2002.04672) (Yang, Liang, Carin) gives the
  formal framing and a loss function that doesn't make this assumption; [A Positive
  and Unlabeled Learning Algorithm for One-Class Classification of Remote-Sensing
  Data](https://www.researchgate.net/publication/220051774) applies the same idea
  specifically to remote sensing with only positive labels available — which is
  exactly this project's situation.
- **The closest real precedent found**: [Nationally Consistent, Locally Incomplete: A
  Bayesian Remote-Sensing Audit of Rooftop Photovoltaic Registries](https://arxiv.org/pdf/2609.16294).
  Same shape of problem — a registry (French rooftop solar interconnection data) that's
  accurate in aggregate but locally incomplete. Their Bayesian-corrected remote-sensing
  estimate matched the national total to within 3.3%, while finding local
  under-reporting up to 61% in some areas. That's the right shape of result to aim
  for here: don't just report "X% of our detections match the registry," report a
  corrected estimate with an uncertainty band, and expect — and say out loud — that
  it will disagree with the registry locally even if it agrees with it statewide.

## 3. What's missing, matched to a method or an honest gap

| Missing piece | Candidate method / template | Literature support |
|---|---|---|
| Species classifier (no vision-based species ID exists at all) | CNN/YOLO classification per structure, same architecture family as the cattle-feedlot and CAFOSat/PRISM-CAFO work | Strong — direct precedent exists |
| Capacity/headcount from geometry alone (currently R²=0.256, empirical, poultry-only) | Allometric space-allowance equations (`area = k·W^0.667`) from livestock housing design standards, as a physically-grounded complement to the empirical fit | Moderate — [Space allowances for confined livestock and their determination from allometric principles](https://www.researchgate.net/publication/43506484); [FAO livestock housing design standards](https://www.fao.org/4/i2433e/i2433e07.pdf). These are design standards, not remote-sensing papers, but they give a per-species area-to-headcount relationship that doesn't depend on registry self-reporting at all — worth testing against the existing empirical fit rather than replacing it blindly. |
| Manure storage-type detection (lagoon vs. round tank vs. dry litter vs. uncollected pasture) | **No remote-sensing literature found doing this.** | **None found.** This appears to be a genuinely open sub-problem, not one with a standard solution to look up. If built, it would likely be a real, citable contribution of this project rather than an application of existing work — worth knowing before committing effort, since there's no shortcut here. |
| Independent validation set (Extension non-CAFO list) | PU-learning-style evaluation (above), not naive precision/recall | Strong — directly addresses the exact incompleteness problem in the literature above |
| Unpermitted-facility search across un-anchored tiles | Lower-res, higher-cadence time-series change-point detection rather than single-snapshot high-res tiles — [Enhancing Environmental Enforcement with Near Real-Time Monitoring: Likelihood-Based Detection of Structural Expansion of Intensive Livestock Farms](https://arxiv.org/pdf/2105.14159) (Planet 3m/pixel, AUC=0.86 on 1,513 CAFOs, explicitly built to catch *unpermitted* expansion, not just monitor known sites) | Strong — this is arguably a better-matched method for Priority 4 than scaling the current single-snapshot high-res pipeline statewide, since it's built for exactly this enforcement-relevant, registry-independent use case |

## 4. Sequence to actually finish

This matches the roadmap already agreed (`afo_supply_roadmap` artifact), now with a
method attached to each step instead of just a status:

1. Get the Extension non-CAFO farm list from Stephanie (independent validation set —
   no method needed, just the data).
2. Fix `supply_calculator.py` for manure collectibility (pasture vs. feedlot) — a
   code/domain-knowledge fix, not a literature gap.
3. Build the species classifier, trained on the MDE registry and validated on the
   Extension list, using the CAFOSat/PRISM-CAFO/cattle-feedlot precedent as the
   architecture template.
4. Re-run the capacity/headcount estimate with the allometric approach alongside the
   existing empirical regression, and report both — don't discard the empirical fit
   without a real comparison.
5. Evaluate the whole pipeline with PU-learning-aware metrics against the Extension
   list, reporting a Bayesian-style corrected estimate with an uncertainty band in
   the style of the rooftop-PV audit paper, not a naive precision/recall number.
6. Only after 1–5: decide whether to attempt manure-storage-type detection as original
   work, or scope it out of Task 1 entirely — it has no existing method to borrow,
   so it's a real research decision, not an engineering task.
7. Define the Objective 2 efficiency-gain metric with Catherine and Stephanie — this
   can happen in parallel with 1–6, since it's a scoping conversation, not something
   blocked on the pipeline.

Steps 1–2 can start immediately and don't depend on anything else. Step 6 is a
decision point, not a task — it should be made deliberately, not by default.

## 5. Implemented 2026-09-30: supply calculation no longer requires a registry match

The core objection that triggered this: if species and headcount only ever come
from a registry lookup, the vision pipeline isn't actually driving the number
that matters — it's decoration. That's now fixed for the ~85% of the active
registry that's poultry-shaped:

- `scripts/train_capacity_model.py` fits headcount-from-floor-area on 357
  poultry-type farms (the only species with enough detected examples to
  validate anything), held-out cross-validated **R² = 0.23** — a real, honest,
  moderate signal, not the training-set 0.256 an earlier informal study
  reported. See `docs/species_capacity_model_metrics.md` for the full
  writeup, including exactly why this is poultry-only: of 417 active
  farms, only 372 have any detection at all, and within those dairy has 1
  farm with a detection, beef 3, swine/turkey/ducks 1 each — nowhere near
  enough to fit or validate a classifier. The deeper reason isn't sample
  size alone: the existing shape filter already restricts every detected
  building to a narrow poultry-like shape band by construction, so there's
  almost no shape variance left to separate species by. **Fixing dairy/beef
  requires retraining the segmentation step on real non-poultry examples
  (CAFOSat's patches, or Maryland-specific labels) — not a downstream
  classifier**, which is why one wasn't built.
- `geo_anom/phase2/species_capacity.py` loads that model and predicts
  headcount from detected floor area alone, no registry lookup involved.
- `geo_anom/phase2/supply_calculator.py` now uses that prediction as the
  primary source of headcount for every poultry-shaped detection —
  registered or not. A detected building cluster with no permit anywhere
  nearby is spatially grouped (DBSCAN) and still gets a real N/P₂O₅ number.
  A matched permit's specific poultry subtype (turkey/layer/broiler) still
  picks which nutrient coefficient applies — using information that's
  available isn't the same as depending on it — but the headcount itself is
  always vision-derived for poultry. Non-poultry species (dairy, beef,
  swine, horses) still fall back to registry headcount where a permit
  match exists, explicitly flagged `capacity_source: "registry_fallback"`
  rather than presented as vision-derived; with no match and no poultry
  default to fall back on, the result is `"no_data"`, honestly, not a
  fabricated number.
- Found and fixed along the way: a real, pre-existing bug where
  `calculate_supply()` read an unqualified `"headcount"`/`"farm_name"` key
  after a spatial join — silently wrong (defaulting to 0/blank) any time
  the input polygons carried their own `headcount`/`farm_name` properties,
  which every real detection file does. The unit test fixtures never
  triggered it because they didn't include those columns; running against
  the real full-registry file did. Fixed by renaming the permit table's
  columns before the join instead of relying on pandas' collision
  suffixes. 6 new/updated tests in `tests/test_phase2_pipeline.py` cover
  both this and the new vision-first behavior, including one that asserts
  directly that an unregistered detection gets a nonzero number — the
  actual point of this change.
- **Known remaining limitation, not fixed today**: farm grouping is still
  by nearest-registered-permit, so a building physically closer to a
  neighboring farm's permit point than to its "own" farm's point gets
  grouped (and its headcount predicted) with that neighbor instead —
  visible in testing as two different predicted headcounts across one
  farm's buildings (Hannah Jones, 8 buildings, split across 2 predicted
  values). This predates this change; the DBSCAN clustering added here
  only applies to buildings with no permit match at all.

## 6. References

- Robinson, C. et al. [Mapping Industrial Poultry Operations at Scale with Deep Learning and Aerial Imagery](https://arxiv.org/pdf/2112.10988). The base model this project's U-Net detector is built on.
- Hoque, T. et al. [CAFOSat: A Strongly Annotated Dataset for Infrastructure-Aware CAFO Mapping Using High-Resolution Imagery](https://arxiv.org/pdf/2606.00548).
- [PRISM-CAFO: Prior-conditioned Remote-sensing Infrastructure Segmentation and Mapping for CAFOs](https://arxiv.org/pdf/2601.11451).
- [National-scale open cattle feedlot detection using deep learning and high-resolution aerial images: Spatial distribution and animal welfare analysis](https://www.sciencedirect.com/science/article/pii/S0048969726001117).
- Yang, Y., Liang, K.J., Carin, L. [Object Detection as a Positive-Unlabeled Problem](https://arxiv.org/pdf/2002.04672).
- [A Positive and Unlabeled Learning Algorithm for One-Class Classification of Remote-Sensing Data](https://www.researchgate.net/publication/220051774).
- [Nationally Consistent, Locally Incomplete: A Bayesian Remote-Sensing Audit of Rooftop Photovoltaic Registries](https://arxiv.org/pdf/2609.16294).
- [Enhancing Environmental Enforcement with Near Real-Time Monitoring: Likelihood-Based Detection of Structural Expansion of Intensive Livestock Farms](https://arxiv.org/pdf/2105.14159).
- [Space allowances for confined livestock and their determination from allometric principles](https://www.researchgate.net/publication/43506484).
- FAO. [Livestock Housing, Ch. 10](https://www.fao.org/4/i2433e/i2433e07.pdf).
- [Public Computer Vision Datasets for Precision Livestock Farming](https://arxiv.org/pdf/2406.10628) — survey, useful for scoping what other labeled datasets exist before building one from scratch.
