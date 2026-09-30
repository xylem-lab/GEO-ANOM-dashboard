# Task 1: What "Scientifically Done" Means, and How to Get There

Written 2026-09-30, after the Task 1 pipeline audit (`task1_pipeline` artifact) and a
literature scan for how other groups have handled the same sub-problems. This is a
targeted search grounded in the actual gaps found this project, not a systematic
review — read the primary papers before committing to a method, not just this
summary.

## 1. What "done" actually requires

Three separate criteria, from three separate sources — Task 1 isn't finished until
all three are met, and right now none of them is:

| # | Criterion | Source | Status |
|---|---|---|---|
| 1 | Detect and map AFO features (poultry houses + lagoons, minimum) | Proposal, Objective 1 | Partially — buildings work moderately, lagoons mostly don't (see `task1_pipeline`) |
| 2 | Quantify the efficiency gain of the GeoAI approach vs. the county-level baseline | Proposal, Objective 2 | **Not started.** No comparison metric exists anywhere in the codebase. |
| 3 | Show the model works on facilities it wasn't trained on, not just facilities already in the registry | Catherine Nakalembe, 2026-09-09 meeting | **Not started.** No independent validation set exists yet. |

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

## 5. References

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
