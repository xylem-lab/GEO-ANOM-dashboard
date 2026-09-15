# Publishing GEO-ANOM: A Practical Guide

Added 2026-09-15, from a literature-grounded research pass (not project-internal
analysis) on what it takes to turn this project's work into a published,
peer-reviewed paper. Treat citations here as a starting point to verify
yourself, not settled fact — flagged items at the end are explicitly
unverified.

## 1. Target venues

This work sits at the intersection of two publishing traditions, and could
go either way depending on which contribution is foregrounded.

**Methods-focused venues** (care about the U-Net/SAM pipeline, accuracy
metrics, novelty of the detection approach):
- **Remote Sensing** (MDPI) — broad Earth-observation scope, impact factor
  ~4.3, Q1, first decision typically 60-90 days, acceptance rate ~40-45%,
  APC ~CHF 2,700. High volume, fast, less prestige per paper than the next
  two.
- **ISPRS Journal of Photogrammetry and Remote Sensing** — the field's most
  prestigious specialist journal (2-yr IF ~11.3, CiteScore 17.6, Q1).
  Reviewers scrutinize the segmentation methodology itself (architecture
  choices, SAM prompt strategy, validation protocol) more than the
  environmental application.
- **International Journal of Applied Earth Observation and Geoinformation**
  (Elsevier) — IF ~8.2, Q1, monthly. Sits between methods and application;
  explicitly welcomes applied geospatial-ML work with a real-world use case
  — good fit for GEO-ANOM as a whole.
- **PE&RS (Photogrammetric Engineering & Remote Sensing)** — ASPRS's
  journal, IF ~3.0, Q2, less selective, historically friendly to applied
  U.S.-agency-adjacent work (USGS/NAIP-based studies).

**Application/policy-focused venues** (care about the AFO counts, Chesapeake
Bay nutrient-loading implications, water-quality relevance):
- **Journal of Environmental Quality** (ASA/CSSA/SSSA) — natural home for a
  nutrient-management/watershed framing; IF ~2.3, established CAFO-adjacent
  outlet, but publishes less remote-sensing-method detail.
- **Science of the Total Environment** (Elsevier) — broad environmental
  scope, IF ~8.0, ~18% acceptance rate, ~60 days to first decision. Would
  accept the paper framed as "mapping AFOs to quantify nutrient-loading
  risk" rather than as a CV methods paper.
- **JAWRA (Journal of the American Water Resources Association)** — natural
  fit if the nutrient-transfer optimization model and Bay water-quality
  implications are the centerpiece.
- **GeoHealth** (AGU/Wiley) — a very close analog already exists here:
  Tulbure et al., "Earth Observation Data to Support Environmental Justice:
  Linking Non-Permitted Poultry Operations to Social Vulnerability
  Indices," *GeoHealth* 8(12), 2024 — NAIP imagery + manual digitization of
  poultry barns in North Carolina, linked to social vulnerability data.
  Structurally close to what a Maryland/Chesapeake framing could look like.

**Direct precedent papers worth reading before picking a venue**:
- Handan-Nader & Ho, "Deep learning to map concentrated animal feeding
  operations," *Nature Sustainability* 2019 — high-tier, probably a reach,
  but proves the topic clears top-journal bars.
- Robinson et al., "Mapping industrial poultry operations at scale with deep
  learning and aerial imagery," arXiv:2112.10988 — the same U-Net lineage
  this project's poultry detector is built on.
- "A Comprehensive Dataset of Factory Farms in California Compiled Using
  Computer Vision and Human Validation," *Scientific Data*, 2025
  (PMC12630652) — closest template for the validation-and-anonymization
  write-up (see section 3).

**Recommendation**: a single paper rarely satisfies both audiences well.
Consider splitting into a methods paper (IJAEOG or Remote Sensing) on the
U-Net+SAM pipeline/validation, and an application paper (JEQ, STOTEN, or
JAWRA) on Maryland AFO distribution and nutrient-transfer implications — or
write one paper for a bridging venue like IJAEOG.

## 2. Paper structure and reviewer expectations

Reviewers in this space now expect, as close to non-negotiable:
- **A code and data availability statement.** MDPI's *Remote Sensing* and
  most Elsevier journals require one in every submission; if the full
  dataset can't be released (section 3), state why and offer code/model
  weights, with data "available on reasonable request." Editors increasingly
  screen for this at desk-review.
- **Ground-truth validation with standard metrics** — precision/recall/F1
  or IoU, a confusion matrix against the USGS ground truth, ideally an
  independent held-out set, not just training accuracy. The Cal-FF paper
  (section 1) reports Cohen's kappa (0.73) for inter-annotator agreement
  plus a stratified-sampling completeness estimate (98%, 95% CI [82%,98%])
  across 26 geographic strata — that's the level of explicit
  coverage/completeness estimate that separates "we ran a model" from a
  validated mapping product.
- **Honest framing of accuracy** — per-class performance (poultry vs.
  lagoon vs. background), where the model likely under/over-counts, no
  single blended number hiding failure modes.

**On the failed NDWI lagoon experiment**: not a reason to omit it — this is
exactly the material a "Limitations" or "Alternative approaches" subsection
is for. The original NDWI paper (McFeeters 1996) itself reports cases where
the index breaks down; framing this project's result as "we tested
NDWI-based thresholding first, it failed under [algae/turbidity/mixed-pixel]
conditions, which motivated the CV+SAM approach" turns a negative result
into methodological justification. Reviewers generally read that as rigor,
not weakness — cutting it would look more suspicious than including it.

## 3. Data and ethics considerations

The part of this question with the most direct precedent.

- **IRB**: remote sensing of land parcels/structures via aerial/satellite
  imagery is not human-subjects research under the Common Rule — no
  interaction with living individuals, no identifiable private information
  about a person. None of the comparable papers found (GeoHealth 2024,
  Scientific Data 2025, Nature Sustainability 2019) report IRB approval or
  determination. That said, OHRP guidance says investigators shouldn't
  self-determine "not human subjects research" status — get a formal
  exemption/non-HSR determination letter from UMD's IRB office before
  submission; it costs little and some editors ask.
- **Anonymization precedent**: the Cal-FF (*Scientific Data*) paper states
  directly: "To protect privacy, we withhold the names of parcel owners in
  our public release." They publish county and parcel number but strip
  ownership identity — a workable template: publish facility
  locations/counts/type at whatever resolution serves the nutrient model,
  strip owner names/addresses from any public release.
- **Real, unresolved gap**: neither the GeoHealth non-permitted-operations
  paper nor the Cal-FF dataset paper discusses anonymization/ethics for
  identifying *non-permitted* (i.e., potentially out-of-compliance)
  operations in any depth. This project would be setting precedent here,
  not following an established one — worth an explicit ethics/data
  statement rather than assuming the literature has this settled.
- **Real controversy in this space, not hypothetical**: the animal-ag
  industry has a documented history of resisting CAFO location disclosure
  (an EPA FOIA settlement limited disclosure to city/county/zip rather than
  full addresses/GPS); in Australia, a public "Farm Transparency Map" led to
  federal legislation criminalizing its use to incite trespass. Worth a
  short explicit "Ethical considerations" paragraph stating this project's
  anonymization policy.

## 4. Realistic timeline and process

A rough, honest timeline for a team publishing in this venue type for the
first time:
1. **Internal drafting** (4-8 weeks): full draft circulated to the PI and
   co-PI (Stephanie Lansing) — expect at least 2 rounds of co-author
   revision before submission-readiness.
2. **Preprint (optional, increasingly normal)**: EarthArXiv or ESSOAr are
   well-accepted in geoscience/remote sensing; most major publishers
   (Elsevier, Wiley, Springer Nature) explicitly permit preprints. ~1 day of
   formatting work, no real time cost otherwise.
3. **Submission → first decision**: 60-90 days typical (Remote Sensing,
   STOTEN both roughly this range); ISPRS Journal and IJAEOG can run longer
   given selectivity.
4. **Revision cycle**: expect at least one major-revision round; 4-8 weeks
   to turn around a strong revision, then another 4-8 weeks re-review.
5. **Total realistic timeline**, results-solid to published: **8-14 months**
   for a first submission at a methods/applied remote-sensing journal,
   assuming one revision round and no rejection-and-resubmit-elsewhere
   detour (which would add another 3-6 months).

## 5. Funding and acknowledgment requirements

If federal funding (e.g., USDA NIFA) underlies this project, federal rules
(2 CFR Part 415) require an acknowledgment in essentially every publication
or public material resulting from the award, using the funder's specified
language — for NIFA specifically: *"This work is supported by the [full
program name], project award no. [XXXXXXX], from the U.S. Department of
Agriculture's National Institute of Food and Agriculture."* **Confirm the
actual funder and exact grant number/program name with the grants office
before drafting the acknowledgment** — not verified here.

---

## Unverified / flagged items (from the research pass, not confirmed)

- GEO-ANOM's specific funder and grant number — use the actual award letter.
- No published paper was found combining manure-lagoon detection + CV/SAM +
  Chesapeake Bay specifically — treat the lagoon-detection contribution as
  more novel than the poultry side, and expect more reviewer scrutiny on it.
- The GeoHealth/Scientific Data papers' silence on ethics for
  non-permitted-operation identification is a genuine literature gap, not
  something resolved elsewhere — this project would likely be setting some
  precedent itself on that question.
