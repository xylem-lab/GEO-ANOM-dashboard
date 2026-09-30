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

### Compute note (informational only, not a recommendation)

Fine-tuning a YOLOv8/YOLOv11-class detector or a U-Net on CAFOSat-scale data (~45,000 patches, 833×833px) plus any Maryland-specific fine-tuning is a realistic single-GPU training job (comparable in scale to the existing poultry U-Net training) — the kind of job typically run on a single mid-to-high-end cloud GPU instance (e.g., one A10/A100/L4-class instance) over hours to a low number of days, not a multi-GPU or multi-week job. SAM2 inference at scale (statewide lagoon refinement) is more compute-hungry per-image than the detector step, since it runs a large image encoder per candidate region; this is the same class of cost the project's existing SAM lagoon step already incurs, just potentially applied to more candidates if a learned detector proposes more/different regions than the classical CV step did. Actual sizing (instance type, hours, cost) is left to the user's own evaluation.

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
