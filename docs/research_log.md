# GEO-ANOM Research Log

## 2026-09-15 — Literature survey: poultry/dairy/swine/beef/lagoon detection + labeling methodology

**Scope:** Survey of current (prioritizing 2022-2026, with foundational older work) literature on AFO structure detection from aerial/satellite imagery for all five Task 1 targets (poultry, dairy, swine, beef, lagoons), plus labeling/annotation methodology for building ground truth where none exists yet (dairy/swine/beef). Read-only survey; no pipeline code touched.

---

### 1. Poultry house / broiler barn detection

The project's existing pipeline (Robinson et al. 2022 U-Net + Tulbure et al. 2024 heuristic filter) remains the standard approach; nothing found supersedes it.

- **Robinson, C. et al. (2022).** "Mapping industrial poultry operations at scale with deep learning and aerial imagery." *IEEE JSTARS* (also arXiv:2112.10988). Microsoft Research. U-Net trained on ~2,611 labeled Delmarva images, applied to NAIP nationwide. Code/predictions: [github.com/microsoft/poultry-cafos](https://github.com/microsoft/poultry-cafos). Already the project's base model — confirmed real and current best-in-class.
- **Tulbure, M. et al. (2024).** "Earth Observation Data to Support Environmental Justice: Linking Non-Permitted Poultry Operations to Social Vulnerability Indices." *GeoHealth* 8(2), Wiley. [DOI](https://doi.org/10.1029/2024GH001179) / [PMC copy](https://pmc.ncbi.nlm.nih.gov/articles/PMC11652945/). Post-processing filter using polygon area/aspect-ratio distributions from reference datasets, validated on NC — this is the heuristic already in the project's pipeline.
- **Handan-Nader, C. & Ho, D.E. (2019).** "Deep learning to map concentrated animal feeding operations." *Nature Sustainability* 2, 298–306. Foundational older CNN (Inception V3) work on NC poultry+swine CAFOs, predates Robinson but still cited as the field's starting point. [Nature link](https://www.nature.com/articles/s41893-019-0246-x).
- **Earth Genome / Earth Index — "Finding 5 billion chickens..."** (Boyda, E., blog, Earth Genome, undated 2025/2026). Not a peer-reviewed paper — flagging as a tool/workflow, not a citable method. Produced a poultry CAFO dataset across six southeastern states using human-in-the-loop labeling on their "Earth Index" foundation-model search tool. Relevant mainly for §6 (labeling), not as a competing detector.

**Most promising lead:** Nothing displaces the current Robinson+Tulbure combination for poultry. The one thing worth tracking: **CAFOSat** (see §5/§6 below) includes poultry barn annotations alongside dairy/swine/beef/lagoon in one schema — could be used as an independent held-out validation set for the existing poultry model, since it was built by a different team with different labeling protocol than Soroka & Duren.

---

### 2. Dairy operation / freestall barn detection

This is thin. No mature, validated dairy-barn detection pipeline exists in the literature comparable to Robinson et al. for poultry.

- **Haider, U., Khalid, F., & Mason, K. (2026).** "Weakly Supervised Spatio-Temporal Candidate Discovery of Dairy Farm Sites from Seasonal Satellite Imagery." arXiv:2607.12748 (submitted July 2026, CVPR-track). Uses Sentinel multi-season imagery (spring/summer/autumn), OpenStreetMap farm points as weak labels, a Barlow Twins self-supervised encoder, and a rule-based tile score (pasture seasonality + greenness) to *rank candidate sites for human review* — explicitly not a detector, a triage tool. Reported precision: 0.60 within 500m / 0.80 within 1000m for top-5 clusters. Validated on County Cork, Ireland, not the US — transferability to Maryland dairy operations (different barn/pasture geometry, different NAIP-vs-Sentinel resolution) is untested. No code/data release found.
- **CAFOSat** (see §5) includes a dairy category with barn/pond/grazing-area annotations across 20 US states — the only US, NAIP-resolution, multi-class dataset found that includes dairy at all.
- Most other "dairy + deep learning" hits are in-barn cow-tracking/behavior camera systems (e.g. Mask R-CNN cow tracking, PMC7765358), which are a different problem (ground-level video, not aerial structure detection) and not usable here.

**Most promising lead:** No off-the-shelf dairy detector exists. The realistic path is: use **CAFOSat's dairy-labeled patches** as a bootstrap training/validation set (freestall barns look geometrically distinct — long rectangular roofs, open-sided, often paired with visible drylot/loafing areas), fine-tune a detector (e.g., the same U-Net architecture as poultry, or a YOLO detector as PRISM-CAFO does) on CAFOSat dairy examples, then supplement with Maryland-specific manual labels since Maryland dairy barn typology may differ from the CAFOSat states sampled.

---

### 3. Swine (hog) operation / confinement building detection

Real, substantial prior art exists, driven by NC/Delmarva environmental-justice research — consistent with what the project expected.

- **Handan-Nader & Ho (2019)**, above — NC-CAFO dataset explicitly includes 714 swine CAFO/lagoon images, Inception V3 classifier.
- **Magesh, V. et al. (2025).** "A comprehensive dataset of factory farms in California compiled using computer vision and human validation." *Scientific Data* 12, 1826. [DOI](https://doi.org/10.1038/s41597-025-06082-6) / [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12630652/). Covers cattle (dairy subcategory), poultry, and swine/hog in California; 57,236 human-validated building bounding boxes on 1m NAIP imagery. Directly useful as methodology reference (§6) even though it's California, not Maryland.
- **CAFOSat** (below) — swine barns + manure ponds as explicit classes.

**Most promising lead:** Swine confinement buildings are structurally closer to poultry houses (long, low, enclosed metal/gable-roof barns) than dairy or beef operations are, so **transfer learning from the existing poultry U-Net, fine-tuned on CAFOSat's swine-labeled patches and/or the NC-CAFO swine images**, is the lowest-effort starting point — more promising than starting swine detection from scratch.

---

### 4. Beef cattle operation / feedlot detection

The strongest, most directly transferable new finding of this survey.

- **Venancio Aires, U.R., Souza Martins, V., Hester, D., Lima, T., & Borges Ferreira, L. (2025).** "National-Scale Open Cattle Feedlot Detection Using Deep Learning and High-Resolution Aerial Images: Spatial Distribution and Animal Welfare Analysis." *Science of the Total Environment* (ScienceDirect: [S0048969726001117](https://www.sciencedirect.com/science/article/pii/S0048969726001117); dataset/methods record at Mississippi State's repository, [DOI 10.54718/CCPL7238](https://doi.org/10.54718/CCPL7238)). Manually labeled 11,746 open feedlots across NE/KS/TX + ~13,000 background patches from 2019-2022 NAIP imagery (1m, resampled from ~43TB GeoTIFF); trained 5 YOLO variants; YOLOv11m was best, detecting 24,000+ facilities nationwide.
- **Muenich, R.L. (lead), Saha, A., Rashid, B., Liu, T., Miralha, L. et al. (2025).** "Machine learning-based identification of animal feeding operations in the United States on a parcel-scale." *Science of the Total Environment* (Jan 2025). [PubMed 39765170](https://pubmed.ncbi.nlm.nih.gov/39765170/). University of Arkansas. Parcel-scale (not pure imagery) AFO identification across 18 states using Regrid nationwide parcel data + imagery; multi-species. Full-text access was blocked (403) during this survey — cite with the caveat that only the abstract/press coverage was verified, not the full methods/metrics.

**Most promising lead:** The Mississippi State feedlot paper is a near-exact match for open beef feedlots (unroofed pens, distinct from Maryland's likely smaller/enclosed beef operations, so expect a domain gap, but it is the clearest "adapt this" candidate found for any non-poultry category). Its NAIP-based, YOLO-based approach is also architecturally consistent with the PRISM-CAFO lagoon lead below, suggesting a YOLO-family detector could be a common backbone across beef, swine, and lagoon detection.

---

### 5. Manure/waste lagoon detection

This is where the survey found the most directly relevant new material for the project's specific failure mode (RGB/color-threshold candidate generation not generalizing statewide).

- **PRISM-CAFO** — Hoque, O.B., Mandal, N.C., Luong, K., Wilson, A., Swarup, S., Marathe, M., & Adiga, A. "PRISM-CAFO: Prior-conditioned Remote-sensing Infrastructure Segmentation and Mapping for CAFOs." WACV 2026 / arXiv:2601.11451. University of Virginia Biocomplexity Institute. **Verified real** (arXiv abstract + GitHub fetched directly: [github.com/Nibir088/PRISM-CAFO](https://github.com/Nibir088/PRISM-CAFO), CC-BY-4.0, code+masks+descriptors released). Key methodological point for this project: instead of color/solidity thresholds, it uses a **domain-tuned YOLOv8 detector** to propose candidate infrastructure (barns, feedlots, lagoons, silos), then runs **SAM2** on the YOLO boxes with component-specific geometric filtering (for ponds/lagoons: amorphous-shape + maximal mask-coverage criteria) rather than relying on raw pixel color. Important caveat verified directly from the paper text: **it does not report class-specific precision/recall for lagoons alone**, and does not explicitly discuss forest-canopy-shadow or dark-rooftop confusion — so it is a promising architecture, not a validated solution to this project's exact confounders.
- **CAFOSat** — Hoque, O.B., Mandal, N.C., Wilson, M.L., Swarup, S., Marathe, M., & Adiga, A. "CAFOSat: A Strongly Annotated Dataset for Infrastructure-Aware CAFO Mapping Using High-Resolution Imagery." arXiv:2606.00548 (also a CVPR2026 EarthVision workshop paper, PDF confirmed at [openaccess.thecvf.com](https://openaccess.thecvf.com/content/CVPR2026W/EarthVision/papers/Hoque_CAFOSat_A_Strongly_Annotated_Dataset_for_Infrastructure-Aware_CAFO_Mapping_Using_CVPRW_2026_paper.pdf)). **Verified real and publicly downloadable**: [huggingface.co/datasets/oishee3003/CAFOSat](https://huggingface.co/datasets/oishee3003/CAFOSat), CC BY 4.0. ~45,000 patches (39,257 base + 6,454 synthetic augmentations + 20,771 negatives), 833×833px, 0.6m resolution, 2023 NAIP, 20 US states, six categories (swine, poultry, dairy, beef, horses, sheep/goats), with per-patch annotations for barn count, **manure pond count**, grazing area, and other structures. This is a labeled lagoon/pond dataset that did not exist when this project's classical-CV approach was designed.
- **Montefiore, L.R., Nelson, N.G., Dean, A., & Sharara, M. (2022).** "Reconstructing the historical expansion of industrial swine production from Landsat imagery." *Scientific Reports* 12, 2189. [DOI](https://doi.org/10.1038/s41598-022-05789-5). Foundational but NOT a solution to the generalization problem: uses a changepoint/spectral-shift method on 30-year Landsat time series (dry-land-to-water reflectance change at known lagoon coordinates) to date construction of 3,405 already-located NC lagoons — it assumes lagoon locations are already known and doesn't attempt open-world detection or discrimination from forest-canopy/wetland false positives. Relevant as background, not as a fix.

**Most promising lead — the clearest actionable finding of this whole survey:** Replace or supplement the classical color/solidity candidate-generation stage with a **YOLOv8 (or similar) object detector trained on labeled examples**, following the PRISM-CAFO architecture, and use **CAFOSat's manure-pond-annotated patches** (public, CC BY 4.0, NAIP-native resolution) as either direct training data or an external validation/calibration set far larger and more geographically diverse than the project's current small calibration set. This directly targets the stated failure mode: a learned detector conditioned on shape/context features (not raw color) should generalize past forest-canopy and dark-rooftop confounders in a way NDWI/GLCM-texture thresholds could not, because it isn't relying on spectral thresholds at all.

---

### 6. Labeling / annotation methodology

- **Magesh et al. (2025)** *Scientific Data* (above, §3) is the most useful methodology reference. They used **CloudFactory** (third-party commercial labeling service) with a structured decision flowchart, cross-referencing Google Maps/Street View for ground confirmation, and a **three-stage validation** (initial labeling → construction dating → animal-type classification), reporting inter-rater reliability via **Cohen's kappa = 0.73**. This is a directly adoptable template for building Maryland dairy/swine/beef ground truth: use a flowchart-driven protocol, track inter-rater agreement, and don't rely on single-annotator labels.
- **Handan-Nader & Ho (2019)** and the **RegLab NC-CAFO dataset** ([reglab.stanford.edu/data/cafo-training-dataset](https://reglab.stanford.edu/data/cafo-training-dataset/)) used in-house "hand coders" building on prior manual enumeration by advocacy groups (Environmental Working Group, Waterkeeper Alliance) — i.e., existing registries/enumerations as a labeling seed. Access note: the dataset is downloadable directly (zip link on the RegLab page) with only a citation requirement stated, no formal license documented — treat as citation-required, not confirmed open-license.
- **CAFOSat** labeling process (per its arXiv text) combined manual annotation with synthetic augmentation to balance rare classes (dairy/beef/lagoon undersampled relative to poultry) — a relevant technique if Maryland ground truth for dairy/swine/beef ends up small.
- **Earth Genome's Earth Index** (blog source only, not peer-reviewed — flagged as such) demonstrates a **human-in-the-loop active-labeling workflow**: analyst labels a few examples, clicks "auto-label," model proposes matches for visually similar areas statewide, analyst corrects. This is the same active-learning pattern found in the building-footprint literature (e.g., Xu et al.-style deep active learning with landscape metrics for CNN building mapping, *Remote Sensing* 2022, [DOI:10.3390/rs14194738](https://doi.org/10.3390/rs14194738)) and is a practical, low-cost way to bootstrap dairy/swine/beef labels in Maryland without starting from zero manual digitization.

**Most promising lead:** For dairy/swine/beef in Maryland, the recommended methodology synthesis is: (1) seed with CAFOSat's existing multi-species patches, (2) build Maryland-specific labels via a human-in-the-loop / active-learning loop (Earth-Index-style: label a handful, auto-propose, correct) rather than pure manual digitization, and (3) adopt Magesh et al.'s multi-stage-validation + Cohen's-kappa reporting discipline so label quality is auditable the same way Soroka & Duren ground truth was for poultry.

---

### Publicly accessible datasets flagged for reuse (license/access noted)

- **CAFOSat** — [huggingface.co/datasets/oishee3003/CAFOSat](https://huggingface.co/datasets/oishee3003/CAFOSat), CC BY 4.0, ~45,000 NAIP patches, 20 states, 6 species classes incl. dairy/swine/beef + manure-pond counts. **Directly usable now**, no request/approval process found.
- **NC-CAFO training dataset** (Handan-Nader & Ho / RegLab) — direct zip download from [reglab.stanford.edu/data/cafo-training-dataset](https://reglab.stanford.edu/data/cafo-training-dataset/), citation-required, no formal license statement found (flag as unconfirmed license terms, not a hard blocker).
- **Microsoft poultry-cafos** — [github.com/microsoft/poultry-cafos](https://github.com/microsoft/poultry-cafos), already known to the project (this is Robinson et al.'s own repo).
- **Magesh et al. California factory-farm dataset** — published via *Scientific Data*; check the paper's Data Availability section for the actual repository (not independently confirmed downloadable in this survey — flag as "cited, access unverified").
- **PRISM-CAFO code + masks** — [github.com/Nibir088/PRISM-CAFO](https://github.com/Nibir088/PRISM-CAFO), CC BY 4.0, code/masks/descriptors only (not a raw imagery dataset).

---

## 2026-09-15 (experiment follow-up) — CAFOSat validation run + PRISM-CAFO feasibility check

Ran the experiment this survey recommended (§5). Two concrete findings:

**CAFOSat-audited precision for `full_registry_pc_lagoon_detections.geojson`
(the 74 unverified full-scale candidates): 2/19 = 10.5%**, using CAFOSat's
842 MD/DE patches (40 with manure_pond>0) as independent, externally-sourced
ground truth, spatially matched within 300m (`scripts/validate_lagoons_against_cafosat.py`,
full detail in `docs/cafosat_lagoon_validation_result.md`). Only 19/74
candidates had any independent CAFOSat coverage nearby — this is a partial
audit, not a full one. **This independently confirms** the project's own
10-candidate manual stratified audit (which found "~1 confirmed real," also
~10%) via a completely different method (external dataset vs. visual
inspection) — two independent checks landing on the same ~10% precision is
much stronger evidence the full-scale color/solidity approach is genuinely
broken, not an artifact of one audit's sampling.

**PRISM-CAFO is not usable on this machine as-is**: its GitHub README lists
pretrained model weights under "🔮 Roadmap" (not released — training scripts
only, `train_yolo.py`/`train_multiclass_v2.py`), and its stated environment
requires **Python 3.10**, which this machine doesn't have (system Python is
3.9.6, no Homebrew/pyenv to add another cleanly). Using PRISM-CAFO's
architecture here means training a YOLOv8 detector from scratch (on CAFOSat
and/or Maryland-specific data) in a new Python 3.10 environment — a real
GPU-scale training job and an environment-setup task, not something to
attempt casually. This is a decision for the user: whether to invest in a
Zaratan/GCP environment for this, not something to force onto this laptop.

---

## 2026-09-16 — Dynamic World + AlphaEarth zero-shot lagoon checks (both negative)

Ran the two "no-training-needed" options scoped after the CAFOSat/PRISM-CAFO
finding above. Full detail in `docs/dynamicworld_alphaearth_lagoon_check_result.md`;
summary here.

**Dynamic World (10m water-probability band): not usable.** Real lagoons
scored 0.029-0.458 (median 0.042), false positives 0.027-0.091 (median
0.036) — near-total overlap. 10m Sentinel-2 pixels are too coarse for
farm-scale lagoons, as expected going in.

**AlphaEarth Satellite Embedding: also negative, but a real bug fix landed
along the way.** `geo_anom/phase2/alphaearth_filter.py` (committed March
2026, never tested, no test coverage) had two bugs that meant it had
**never once successfully extracted a real embedding**: it filtered on a
`year` image property that doesn't exist on this collection (always matched
zero images), and guessed wrong band names (`embedding_i`/`bi` instead of
the real `A00`-`A63`), so every extraction silently fell back to an
all-zero vector. Both fixed and verified against live data this session.
With real embeddings finally flowing, a reference-mean cosine-similarity
check (6 known-real lagoons as reference, tested against 1 held-out real +
4 CAFOSat-supported + 19 CAFOSat-contradicted) still found **no separating
threshold** — false positives' similarity range (0.547-0.827) actually
exceeds real lagoons' (0.691-0.766). Caveat: this was a fast 6-point mean
baseline, not a trained classifier — doesn't rule out a properly trained
AlphaEarth-based classifier, just rules out the free/instant version.

**Running tally of what's been tried and ruled out for lagoon detection**:
color/solidity thresholds, NDWI, GLCM-texture, Dynamic World, and a naive
AlphaEarth similarity check. What's left: a real classifier trained on
CAFOSat's national presence-labeled patches (or AlphaEarth embeddings of
them), a Maryland labeling campaign, or full PRISM-CAFO-style detector
training (needs both of those plus a Python 3.10 GPU environment).

---

## 2026-09-16 (continued) — trained AlphaEarth classifier: works on CAFOSat, doesn't transfer here

Went one step past the naive mean-similarity check above: trained a real
logistic regression on AlphaEarth embeddings of ~1,400 CAFOSat points
(700 pond-positive / 700 pond-negative farms, grouped-split by
`CAFO_UNIQUE_ID` to avoid same-farm leakage). Full detail in
`docs/alphaearth_classifier_result.md`.

**On CAFOSat's own held-out test set: genuinely good** — precision 0.791,
recall 0.833, ROC-AUC 0.837. AlphaEarth embeddings do carry real signal for
"does this farm have a pond."

**On this project's own known real-lagoon vs. false-positive set: no
separation** — real lagoons mean p(pond)=0.715, false positives mean
p(pond)=0.724 (FPs actually score slightly *higher*). Best threshold gets
38% precision, barely above the 37% base rate.

**Why, and this is the useful finding**: this project's false positives
aren't generic "not a pond" examples — they're candidates that already
survived classical-CV color/solidity + SAM specifically *because* they look
pond-like (canopy shadow, dark rooftops, wetland fragments). CAFOSat's
negative class is an easy "farm with no pond," not "thing that already
fooled a first-stage pond detector." A classifier needs to be trained
against *this project's own* false-positive population (or comparably
adversarial examples) to help at this stage of the pipeline — a generic
external pond/no-pond dataset, however large, doesn't transfer to it.

This closes out the "cheap, no-labeling-campaign" options. What's left is
what was scoped before: a Maryland-specific labeling effort (ideally
including these exact false-positive shapes as explicit hard negatives),
or full detector training.

### Compute note (informational only, not a recommendation)

Fine-tuning a YOLOv8/YOLOv11-class detector or a U-Net on CAFOSat-scale data (~45,000 patches, 833×833px) plus any Maryland-specific fine-tuning is a realistic single-GPU training job (comparable in scale to the existing poultry U-Net training) — the kind of job typically run on a single mid-to-high-end cloud GPU instance (e.g., one A10/A100/L4-class instance) over hours to a low number of days, not a multi-GPU or multi-week job. SAM2 inference at scale (statewide lagoon refinement) is more compute-hungry per-image than the detector step, since it runs a large image encoder per candidate region; this is the same class of cost the project's existing SAM lagoon step already incurs, just potentially applied to more candidates if a learned detector proposes more/different regions than the classical CV step did. Actual sizing (instance type, hours, cost) is left to the user's own evaluation.

---

## 2026-09-16 through 2026-09-21 — six blocked daily cloud cycles, consolidated finding recovered

**What happened:** the daily scheduled `geo-anom-researcher` cloud routine ran every day 2026-09-16 through 2026-09-21 and did real research each time, but **every single run failed at the final push/PR step** with `403 Resource not accessible by integration` against `xylem-lab/GEO-ANOM-dashboard` — the Claude GitHub App has read access to this repo but not write access. Both raw `git push` and the GitHub API tools (`create_branch`, `push_files`, `create_pull_request`) failed identically across all 6 runs. Each cloud run's local commit almost certainly did not survive, since these are disposable per-run sandboxes — "committed locally, safe once access is restored," which some of those runs told the user, was not an accurate claim. This entry reconstructs and lands the substance of that work from the session transcripts (still readable via the routine's run history) rather than letting six days of real findings sit lost. Fixing the GitHub App's write permissions for this org (an org-admin action, not something a cloud session can do itself) is required before this routine can deliver on its own again — see `docs/AUTONOMOUS_CYCLE.md` guardrails, which assumed working push access.

**The consolidated finding, triangulated independently across four of the six runs (09-17, 09-19, 09-20, 09-21):** the 2026-09-15 survey's framing that "dairy/swine/beef detection does not exist yet... is genuinely new research" is **wrong for swine and beef specifically**. `docs/labeling_guide.md` already documents, from real audited detections, that the *unmodified* poultry U-Net + Tulbure filter pipeline correctly detects swine confinement barns (Grand View Farm, registered `swine_55_lbs`) and confined-beef/heifer barns (Bistate Feeders, registered `cattle_includes_heifers`) — because those structures share poultry houses' long, low, enclosed gable-roof geometry closely enough to pass the existing shape filter. This was found incidentally during poultry QA, never systematically exploited.

**Dairy is the real, still-open gap**, and a specific, testable cause was identified: of ~14 sampled dairy farms, 11 show zero detections. Cross-referencing free-stall dairy barn engineering specs (standard 4-row barns run ~30.5m wide) against `scripts/unet_detect.py`'s existing shape filter (`WIDTH_MAX_M = 30.0`, `ASPECT_MIN, ASPECT_MAX = 2.5, 18.0` — tuned only against poultry house dimensions) shows the width cap sits almost exactly at the point where standard dairy barns get excluded. Two competing hypotheses were logged: (1) a same-day filter-threshold fix (raise `WIDTH_MAX_M`, re-run against the same 14 farms, check for new false positives), vs. (2) a deeper issue — naturally-ventilated dairy barns have a ridge-vent/curtain-sidewall roof signature that may not segment the same way as a poultry house's roof even before the shape filter is applied, meaning a threshold tweak alone wouldn't be enough.

**Two secondary corrections** surfaced across these runs, both worth keeping:
- CAFOSat's annotations are patch-level presence counts, not per-instance bounding boxes (independently suspected by the 09-18 run from indirect evidence, and separately confirmed directly against the live dataset in an interactive session the same week — see the "trained AlphaEarth classifier" work). The 2026-09-15 survey's framing of CAFOSat as directly detector-trainable needed this caveat.
- PRISM-CAFO's GitHub repo has no visible LICENSE file (09-18 run) — the 09-15 survey's "CC BY 4.0" label for it should be treated as unconfirmed until checked directly, not restated as settled.

**Not a real finding, a correction to a cloud run's own inference**: the 09-19 run noticed two branches (`experiment/cafosat-lagoon-validation-2026-09-15`, `experiment/dynamicworld-alphaearth-lagoon-check-2026-09-16`) with no PR ever opened and guessed they'd hit this same GitHub App issue. They didn't — those came from an interactive session using different git credentials, and were simply pending user review, unrelated to this bug.

**Recommended next experiment** (ground-truth-checkable, laptop-feasible, no new data/compute needed): raise `unet_detect.py`'s `WIDTH_MAX_M` past 30.5m (and re-check `ASPECT_MIN`/`ASPECT_MAX` against real dairy barn aspect ratios), re-run detection against the same ~14 dairy farms referenced in `docs/labeling_guide.md`, and check two things: (a) does detection recall on those farms improve, and (b) does it introduce new false positives elsewhere (re-run the existing 35-farm precision audit sample). This directly tests hypothesis (1) above and would either close the dairy gap cheaply or prove it's actually hypothesis (2), the deeper roof-signature issue.

---

## 2026-09-21 (same day, later) — the WIDTH_MAX_M hypothesis above is wrong; ran it against real data

The recommended experiment above was run for real, immediately, against the actual 14 dairy farms (`data/raw/naip_tiles_pc_4band_full/manifest.json`, filtered to `animal_type` containing "dairy") using the real U-Net checkpoint (`scripts/diagnose_dairy_filter.py`, raw output in `docs/dairy_filter_diagnosis.json`). This is exactly the kind of thing the six blocked cloud cycles above could *reason about* from specs but never actually *run* (no model weights or imagery in their sandboxes) — worth doing before spending any code-change effort on their hypothesis.

**Baseline reconfirmed first**: 13/14 dairy farms currently show zero detections (not 11/14 as `docs/labeling_guide.md` states — likely drift since that note was written, given several pipeline changes landed 2026-09-09 through 09-14; not investigated further, noted as a discrepancy).

**The WIDTH_MAX_M hypothesis is wrong.** Zero of the 14 farms have a raw candidate polygon failing *only* on width. What's actually happening:
- 4/14 farms (Lester C. Jones & Sons, Horizon Organic Dairy, Oak Bluff Dairy Farms, Matthew Fry/Fair Hill Farms) produce **zero raw candidate polygons at all** — the U-Net isn't segmenting anything roof-shaped on these tiles, before the Tulbure filter is even applied.
- The remaining farms mostly produce small fragments (200-470 m²) that fail on **AREA and LENGTH being too small** (well under the 500 m² / 55m floors), not width being too large. None resemble a real barn shape that's merely too wide.
- Oakland View Farms (the one farm that already works, per `labeling_guide.md`) is the only one producing a full-size passing candidate.

**Conclusion: this is hypothesis (2), not (1).** The gap is in the U-Net's segmentation step itself, not the post-filter thresholds. The model most likely wasn't trained on dairy free-stall barn roof signatures (open-sided, curtain-sidewall, ridge-vented — visually different from an enclosed poultry house roof) and largely doesn't recognize them as building-like at all. **Raising `WIDTH_MAX_M` would fix nothing and was not implemented.** This is a real course-correction on a hypothesis that looked reasonable on paper (dairy barns being ~30.5m wide, right at the old cutoff) but didn't survive contact with real data — exactly the failure mode this project's process is built to catch before it reaches a deck or a paper.

**What this actually means for dairy detection**: a filter tweak won't help. The realistic paths are the ones already scoped in the 2026-09-15/16 entries — a classifier or detector trained on real dairy barn examples (CAFOSat's dairy patches, and/or Maryland-specific labels), not a threshold adjustment to the existing poultry-trained model.

---

## 2026-09-21 (evening) — full-registry species audit: real numbers for every animal type, one beef fix landed, one important drift finding flagged unresolved

Prompted by wanting a complete, honest Task 1 status in one sitting. The active registry (417 farms) breaks down as: 389 poultry-type (chickens_not_laying_hens/laying_hens_dry_manure/turkeys/ducks), 14 dairy, 3 beef (cattle_includes_heifers), 1 swine, 9 "unknown", 1 horses. Full breakdown: `docs/task1_species_completeness.md`, generated by `scripts/finalize_task1_species_scope.py`.

**Swine: fully covered.** The state's only swine farm (Grand View Farm) has 1/1 detection, already documented in `docs/labeling_guide.md`.

**Beef: fixed, 1/3 -> 3/3.** Diagnosed the 2 previously-zero farms (`scripts/diagnose_species_filter.py`) and found real, plausible barn-shaped candidates (700+ m², aspect ~2.0-2.25) failing just below `LENGTH_MIN_M=55`/`ASPECT_MIN=2.5` — a materially different, more tractable failure mode than dairy's (see the 09-21 entry above: dairy's problem is no segmentation at all, not a filter threshold). A full-registry rerun with those thresholds globally loosened to 40.0/2.0 confirmed it recovers both beef candidates, but also introduced **169 new, unverified detections on poultry farms** — rejected as an unacceptable, unaudited risk to the validated 99.7% poultry precision. Implemented instead as a species-scoped exception in `scripts/unet_detect.py` (`SPECIES_FILTER_OVERRIDES`, applies only to `cattle_includes_heifers`) and added the 2 newly-recovered beef detections directly to `full_registry_unet_tulbure_detections.geojson` as a minimal, reviewable diff (2 lines appended, nothing else touched) rather than replacing the file with a full regeneration.

**Data-quality fix, zero risk**: removed 4 detections on MD Jockey Club/Pimlico Race Course (`animal_type=horses`, not a Task 1 target species) from the canonical output — a documented false-positive class (grandstand/stable roofs), now excluded rather than contaminating the poultry-house count. See `docs/task1_species_completeness.md`.

**Real, unresolved finding: a full-registry rerun today does NOT reproduce the committed baseline, even for farms where no filter logic changed.** Testing the beef fix required a full 417-farm regeneration to check for regressions. That regeneration showed 15 non-beef (poultry) farms gaining new detections that have nothing to do with the beef filter change — confirmed directly: Todd Hite/Hite Farms, LLC (85,400-bird farm, 0 detections in the committed file) produces 18 valid detections today using the exact unmodified poultry thresholds. This means either the model's raw output, the tile imagery, or the manifest's tile-to-farm mapping has drifted since the committed file was generated — **not investigated further tonight** (no visual image access to verify which of today's or the original run's output is more correct, and re-auditing precision needs the same 35-farm visual protocol used originally). **Do not regenerate the full registry detection file and adopt it wholesale until this is understood** — the existing R²=0.655/99.7%-precision numbers in `docs/task1_metrics.md` describe the *committed* file specifically, and a fresh full run is not guaranteed to match it.

**Lagoon ground-truth correction**: `full_registry_sam_lagoon_detections.geojson`'s 7 features do NOT all have `qa_status: visually_confirmed` — only 3 do (Dulin, Todd, Tran); the other 4 (Jabar Rahim + 3 Paul Aaron Hutchison candidates) are `uncertain_needs_review`, never resolved. The 2026-09-15/16 CAFOSat/Dynamic World/AlphaEarth validation work treated all 7 as confirmed real lagoons — a real error in that test set's construction, not caught until now. Doesn't overturn those checks' negative conclusions (if anything, diluting the "real" class with 4 uncertain examples would bias toward *less* apparent separation, not more), but worth a note if that work is revisited: a cleaner test should use only the 3 fully-confirmed lagoons as positive ground truth.

**Consolidated Task 1 status as of tonight**:
- **Poultry** (389 farms): validated (R²=0.655, 99.7% object precision, 0.9% true-miss rate on the committed detection file) — 358/389 with detections including layers/turkeys/ducks.
- **Swine** (1 farm): 1/1, complete.
- **Beef** (3 farms): 3/3, complete as of tonight's fix.
- **Dairy** (14 farms): 1/14 — real, root-caused gap (U-Net doesn't segment most dairy barn roof signatures), needs training data, not a threshold fix. Open.
- **Lagoons**: full-scale candidate precision ~10% (CAFOSat-audited and manual-audited agree), not usable as a count. 3 fully visually-confirmed real lagoons, 2 more independently corroborated via CAFOSat, 4 more still unresolved "uncertain." Multiple no-training approaches tried and ruled out (color/solidity, NDWI, GLCM, Dynamic World, naive and trained AlphaEarth similarity). Open — needs a labeling campaign or full detector training.
- **9 "unknown" registry entries**: all 9 have real detected structures despite missing species/headcount data in the registry — a data-completeness gap in the MDE source data, not a pipeline failure. Flagged, not resolved (would need an authoritative source to assign real animal_type, not an inference from detection shape alone).

---

## 2026-09-23 — first look at the actual imagery behind the detections: several standing conclusions were wrong

Prompted by building a field guide with real satellite crops (`scripts/render_field_screenshots.py`; figures in `docs/Task1_Field_Labeling_Guide_2026-09-23.pdf`, points in `data/processed/detections/GEO-ANOM_Task1_Field_Map.kmz`). Until now every conclusion in this log about lagoons and non-poultry farms was made from coordinates and statistics without anyone looking at the pixels. Looking changed five things.

**1. The registry permit coordinate is often far from the real barns.** Detected structures vs. the geocoded permit point: Brandenburg (beef) 861 m, Bistate (beef) 845 m, Lester Jones (dairy) 618 m, Oakland View (dairy) 615 m, Panora (beef) 423 m, Horizon (dairy) 94 m. Two dairy permits are not on a dairy at all: Matthew Fry (permit point at an empty road junction; the only dairy-looking complex is ~1 km west at the tile edge) and Oak Bluff (woods and a quarry; no dairy visible). Consequences: (a) some "zero detection" farms are registry geocode errors rather than model failures; (b) a 2 km tile centered on a bad point can miss the farm; (c) nutrient-supply-by-location needs the detected structure position, not the permit point.

**2. Correction to the 2026-09-21 dairy diagnosis.** "4 of 14 dairy farms produce zero raw model output, so the U-Net can't see dairy roofs" was only half right. Lester Jones and Horizon Organic are real, conventional-looking dairies (4 long-roof barns + 3 manure lagoons; a cross-shaped barn + 3 ponds) sitting at the permit location -- true model misses. Fry and Oak Bluff are registry errors. The other 10 zero-detection dairies have not been looked at. The `WIDTH_MAX_M` filter hypothesis stays refuted (the model outputs nothing for the two real ones).

**3. Detection outlines on non-poultry farms are partial.** Brandenburg's outline covers about half of a ~65 x 27 m barn; Panora's covers part of one barn in a complex of several plus two round manure tanks; Oakland View outlines about half of one of two long barns. Farm-level "detected" (beef 3/3) is not building-level coverage, and floor-area-based supply estimates for these farms are underestimates. The beef fix itself is confirmed sound: both added detections are real barns.

**4. The hand-recorded "confirmed lagoons" do not survive imagery review.** Of the 7 records in `full_registry_sam_lagoon_detections.geojson`: Dulin looks like a real lagoon (aligned on both imagery sources); Hoa Tran's polygon sits on a poultry-house roof; Roland Todd's outlines three poultry houses on MD iMAP imagery and lands on field/wood edge on Planetary Computer (the two sources disagree about that location by several hundred meters); Jabar Rahim is a small pond beside a farmhouse (the labeling guide's "river fragment" reason was wrong, the "not a lagoon" conclusion stands); Hutchison's three "uncertain" candidates sit on plain crop field. The 2026-09-15/16 CAFOSat/Dynamic World/AlphaEarth checks and the 2026-09-21 deck used these records as positives ("5 confirmed lagoons"); that count should be read as **1**. The four CAFOSat-"corroborated" automated candidates at Hite/Nguyen are two building roofs, one small building and one lawn patch -- CAFOSat's loose 300 m patch-level match does not validate the specific polygons. Recorded `qa_status` values were left as recorded (except Jabar: `likely_false_positive_house_pond`); the corrected reading lives in the labeling guide and the KMZ.

**5. The dominant lagoon false positive is a blue-gray metal roof**, not canopy shadow or dark garages: Tran, Wolf Farm, William Moore and Hite/Nguyen candidates are all roofs. Untested cheap idea: reject lagoon candidates that coincide with a roof (building polygons, or NIR/brightness signature). Also: the lagoon step's barn-proximity filter means missed barns imply missed lagoons -- Lester Jones's and Horizon's six real lagoons are absent from every file -- and round concrete manure tanks (Panora) are a lagoon-type store the rectangular-pond detector cannot find.

**Hypothesis tested and rejected along the way (do not re-try):** the MD iMAP GeoTIFFs' embedded latitude span is ~1.28x the manifest bbox for all 417 tiles (georeferenced as equal degrees). Rebuilding the transform from the bbox displaced Dulin's confirmed lagoon by ~90 m, so the file georeference is the one the detections used; the mismatch is just how the tiles were downloaded. The iMAP-vs-Planetary-Computer disagreement near Roland Todd remains unexplained.

**Tooling note:** overlays can be checked by eye -- render a crop and open it with the image viewer -- so future validation of detections should include looking, not only counting.

---

## 2026-09-30 — Hands-on imagery audit: 33 new farms, real screenshots, real findings

While waiting on Stephanie's Extension non-CAFO farm list, did a direct trial-and-error
pass rather than more planning: rendered real crops from the 417 tiles already on disk
(`data/raw/naip_tiles_pc_4band_full`) for a stratified sample of 33 farms never looked
at before — every remaining dairy farm (9), every remaining laying-hen farm (4), all 9
"unknown species" registry entries, the second duck farm, and 10 randomly sampled
ordinary broiler farms. Script: `scripts/render_species_audit_batch.py` (extracted from
the still-unmerged `docs/field-guide-imagery-kmz-2026-09-23` branch's `field_imagery.py`
module). Full writeup: `docs/task1_imagery_audit_2026-09-30.md`.

Headline findings:
- **Dairy census now complete (14/14 farms)**: 13 of 14 return zero detections, not
  "11 of ~14" as previously stated — corrected in `labeling_guide.md`. The missed
  structures are consistently wide/blocky/clustered, not a threshold-tuning gap.
- **4 real-looking manure lagoons at dairy sites the lagoon detector never proposed a
  box for at all** (Teabow, Arbaugh's, Patterson, Deerspring) — all read brownish-olive
  on screen, not the bright teal the color check was calibrated on. Plausible root
  cause for the candidate-generation step silently missing this class of water.
- **Round manure tanks confirmed at a second site** (David Pyle, 2 tanks) beyond Panora
  Acres — a recurring, currently untracked structure type.
- **6 of 9 "unknown species" registry entries are confidently, visually identifiable as
  ordinary poultry operations** — a direct, low-effort registry fix. 1 (Alan & Kristin
  Hudson) is not a standard livestock building at all and may be correctly unclassified.
  2 have no visible structure near the registry point (same geocode-error pattern as
  Fry/Oak Bluff).
- **Registry-point/structure mismatch is not dairy-specific**: 3 of 10 randomly sampled
  ordinary broiler farms also had the registry coordinate in an empty field with nothing
  visible nearby (Boi & Nawl, Maurice Blake, Smithville View/MacDonald).
- **One unexplained miss with no shape excuse**: Cobb Heritage LLC/Pocomoke Farm #4 has
  a textbook-clean 7-8 house complex directly at the registry point — zero detections,
  with no obvious reason from the imagery. Worth checking whether this tile actually ran
  through inference before assuming it's a model failure.
- **VALO BioMedia North America LLC** is registered as `laying_hens_dry_manure` but its
  coordinate sits on what looks like an industrial/biologics building, not a poultry
  farm — flagged as a possible registry miscategorization, not a detection gap.

Five concrete questions for the AGNR team are listed at the end of
`docs/task1_imagery_audit_2026-09-30.md`, each tied to a specific farm and finding
rather than a general ask.

## 2026-10-05 — pipeline refactor and full rerun: drift explained, duplicates found, broiler N coefficient off ~14x

Branch `refactor/task1-pipeline-notebooks-2026-10-05`. Task 1 now runs from `geo_anom/task1/` via `scripts/map_buildings.py` + `scripts/compute_supply.py`, with notebooks `01_map_buildings` / `02_supply_check` calling the same code. Refactor verified bit-identical to the old `unet_detect.py` (same mask, same polygons) on 10 farms.

- **09-21 "drift" = gap, not drift.** Full rerun vs. committed file: 401/416 farms identical; 15 farms had 0 committed and detections now, all in tile block site_0151–0231. Hite (18 detections) checked by eye: all real houses. Runs are deterministic on current tiles.
- **Cross-tile duplicates: 2,828 per-tile detections = 2,251 unique buildings.** The committed 2,726-feature file counts ~541 barns twice (overlapping 2 km tiles). Buildings are now de-duplicated (>50% overlap) and attributed to the nearest permit point (`assigned_distance_m` recorded).
- **Cobb Pocomoke #4**: was in the gap; today 2 kept, ~7 real houses rejected because adjacent houses merge into one oversized blob. New concrete failure mode (merged-blob rejection) — candidate fix to test: split blobs by width before filtering, or a smaller close kernel only for oversized blobs. Not tried.
- **Broiler N**: config 0.91 lb N/bird/flock x 6.5 flocks -> 300.8M lb/yr statewide vs AWTF 21.85M (2019) = 13.8x. AWTF implies ~0.08 lb/bird. Not changed — needs Lansing lab.
- Partial-roof outlines underestimate floor area (affects the area-weighted N split).
- Beef: 2/3 farms in a fresh run (09-21's two hand-added detections aren't reproduced).
- Still to recheck against the new baseline: the 0.9% unexplained-miss rate and the 14-farm zero-detection root-cause list (`task1_metrics.md` §4) — some of the 14 may be gap farms.

## 2026-10-07 — 53% of tiles were shifted/stretched by a download bug; fixed, all tiles rebuilt, new baseline 1,831 buildings

See `docs/NEXT_SESSION.md` 2026-10-07 for the full account. Root cause: windowed read past a NAIP quarter-quad edge, clipped then stretched over the full tile (219/417 tiles, offsets up to ~500 m). Fix: warp + mosaic all intersecting items onto a fixed 1 m grid (`tiles.download_tile`). Verification: stored-vs-source offset 0 m on rebuilt tiles; same-barn cross-tile distance median 0.2 m (was 68 m). Every number computed on `naip_tiles_pc_4band_full/` tiles (R^2 0.655, 99.7% precision, 0.9% unexplained-miss, 82% MDE crosscheck, lagoon positions, registry-offset estimates) needs recomputing before it is cited again. Lesson: a per-farm overlay can't reveal a georeferencing error because image and boxes share it -- cross-tile consistency (same object, two tiles) and comparison with the source are the checks that catch it.

## 2026-10-10 — Somerset county grid run (notebook 04): registry-independent detection works; dark roofs are the main miss

Grid run over all of Somerset (365 tiles). Vs USGS hand tracing (all houses, registered or not): P 99% / R 66% / F1 0.79; grid finds 79 more traced houses than registry-centred tiles. 81 houses >1 km from any permit are all real. Misses are concentrated in dark/rust roofs (brightness 145 vs 175; R−B +5 vs −10). Next experiment candidates: (1) fine-tune the U-Net on Delmarva dark-roof houses using the hand tracing as labels (held-out counties for testing); (2) dual threshold — accept lower-probability shapes only if long/narrow and house-sized — measured on Somerset before/after. Do (2) first: cheap, no training.

