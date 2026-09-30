# Start Here — Project Status as of 2026-09-21

Read this file first in any new session working on GEO-ANOM. It's the
single pointer to everything else. This supersedes the 2026-09-02 version
below it, which is kept for history.

## 2026-09-21 — daily cloud research routine was silently broken for 6 days; fixed and findings recovered

**The daily `geo-anom-researcher` cloud routine (set up 2026-09-15) has
been failing at its final push/PR step every single day since 2026-09-16**
with `403 Resource not accessible by integration` against
`xylem-lab/GEO-ANOM-dashboard` — the Claude GitHub App has read access but
not write access to this repo. Six days of real research ran and got
stuck; see `docs/research_log.md`'s "2026-09-16 through 2026-09-21"
entry for the consolidated, recovered findings (the actual research was
good — the delivery mechanism was broken, not the research).

**Action needed before the routine can deliver on its own again**: an org
admin needs to reinstall/reauthorize the Claude GitHub App for the
`xylem-lab` org with write access — https://github.com/apps/claude/installations/select_target
— or reconnect GitHub under claude.ai Settings → Connectors. Until that's
done, treat the daily routine as research-only-with-manual-recovery, not
fully autonomous; check its run history periodically rather than assuming
silence means nothing happened.

**The recovered finding, still good**: the poultry U-Net pipeline already
incidentally detects swine and beef confinement barns (see
`docs/labeling_guide.md`) — dairy is the real, still-open gap.

**But the cloud routine's specific hypothesis for *why* was wrong, and this
was caught same-day**: it guessed `unet_detect.py`'s `WIDTH_MAX_M=30.0`
filter was excluding ~30.5m-wide free-stall barns. Run for real against the
actual 14 dairy farms and the real U-Net checkpoint
(`scripts/diagnose_dairy_filter.py`, 2026-09-21): zero farms have a
candidate shape failing only on width. The real problem is upstream — the
U-Net mostly isn't segmenting dairy barn roofs as building-like at all (4/14
farms produce zero raw candidates before any filter runs). This needs a
model/training fix (CAFOSat dairy patches or Maryland-specific labels), not
a threshold tweak — see the same-day follow-up entry in
`docs/research_log.md` for the full diagnosis.

## 2026-09-15 — three-agent autonomous cycle set up

Task 1's scope is now explicit: map every poultry, dairy, swine, beef, and
lagoon AFO (not poultry+lagoon only). To work toward that with continuous
research/experiment/documentation while keeping git clean and staying
inside scope, a three-role subagent system was set up:
`.claude/agents/geo-anom-{researcher,experimenter,teacher}.md`, orchestrated
per `docs/AUTONOMOUS_CYCLE.md` — read that file before running or scheduling
a cycle. Dairy/swine/beef detection is new research, not a known transfer of
the existing poultry U-Net; that's the researcher's first assignment.
Compute defaults to this laptop; UMD Zaratan or GCP only gets used once a
specific cycle identifies a real need for it, and only with the user's
explicit go-ahead. All experiment work happens on `experiment/*` branches
with a PR for review — no more direct commits to `main` from automated work.

## 2026-09-09 through 2026-09-14 — read this before citing any lagoon or
## recall number below

## 2026-09-09 through 2026-09-14 — read this before citing any lagoon or
## recall number below

**Lagoon registration bug: root-caused AND fixed. Full-scale lagoon
detection precision: a new, deeper problem found, unresolved.** The user
opened this project's own KMZ exports in Google Earth and found real
problems — lagoon markers sitting on open fields, poultry houses visibly
offset. Root cause: houses are detected from **Planetary Computer** NAIP
imagery; lagoons were detected from a **different source — MD iMAP** RGB
tiles, with a real ~70-100m mutual georeferencing offset (source-data
limitation, not a bug in our reprojection code). **Fix built and
verified 2026-09-14**: `scripts/ndwi_lagoon_detect.py` moves lagoon
candidate generation onto Planetary Computer imagery (same source as
houses). Direct coordinate comparison confirms the fix: previously-real
lagoons (Dulin, Tran) now land within ~5m of their prior positions;
Roland Todd's farm (the original bug-diagnosis example) shows the ~100m
offset directly when you look for the real lagoon at the old coordinate —
confirming the bug's cause and magnitude exactly as diagnosed, and
showing the offset is spatially variable (not one constant global shift).

**But the color/solidity candidate-generation filters, even after honest
recalibration, do not generalize to full scale.** Thresholds calibrated
on MD iMAP's color rendering don't transfer to Planetary Computer's
(measured directly: a known-false natural-pond candidate that MD iMAP
correctly rejected passed on PC imagery). Recalibrated on a 7-farm test
set — but a position-level check caught the recalibration's own labeling
mistake (a "confirmed real" candidate, matched only by farm name, turned
out to be a different false positive ~1km from the real lagoon, which
was too shadowed to generate a candidate box at all — a new recall
failure mode). Full-scale run (417 farms): 74 candidates; a 10-candidate
stratified audit found only ~1 confirmed real. New false-positive
classes found: dark building rooftops, forest-edge/hedgerow shadow,
river/wetland fragments — see `docs/labeling_guide.md` and
`docs/task1_metrics.md` §5 for full detail and exact numbers. **Treat
`data/processed/detections/full_registry_pc_lagoon_detections.geojson`
as unverified candidates requiring individual review, not a trusted
detection count.** The registration-bug fix itself is real and should be
kept; the candidate-generation approach needs either a labeled training
set for a real classifier or full manual verification before any lagoon
count from this pipeline is usable — neither done here.

**NDWI and GLCM-texture were tested as a water-discrimination signal and
neither worked — a real, honestly-reported negative result.** The idea:
since the RGB color approach kept reopening new false-positive classes
each time one was patched (river → pool → forest canopy, across this
project's history), switch to NDWI = (Green−NIR)/(Green+NIR) using
Planetary Computer's 4-band imagery, since water should absorb NIR
strongly regardless of RGB color. Tested against the correctly-scoped
target (dense forest canopy false positives, not the water bodies that
are legitimately water spectrally like ponds/quarries/rivers): NDWI
ranges for real lagoons and canopy false positives overlap: no clean
threshold separates them on this imagery at this resolution. Local
pixel-variance texture was also tried as a smoothness proxy; same
outcome. **SWIR-based indices (WNDWI/MNDWI/AWEI, better for turbid
water) were not testable — NAIP has no SWIR band.** Worth citing as a
limitation/future-work item in any write-up, not silently dropped.

**Formal, publication-grade metrics now exist for building detection**,
replacing informal ratio/correlation numbers: `geo_anom/phase1/evaluation.py`
(R²/RMSE/MAE/Pearson/Spearman via sklearn+scipy, precision/recall/F1 from
a manual audit — unit-tested against synthetic known values in
`tests/test_evaluation.py`) applied in `docs/task1_metrics.md`. Headline
results: farm-level count regression R²=0.655 vs. Soroka & Duren 2016/17
ground truth (n=353); ~99.7% object-level precision from a real 35-farm
stratified visual audit; farm-level recall **now a fully-audited, closed
number** (14/341 zero-detection farms, all 14 individually root-caused —
see `docs/task1_metrics.md` section 4) with a true unexplained-model-miss
rate of **0.9%**, not the less-informative blanket figures used earlier
in this project. A genuine methodological finding from this work: total
detected floor area is a materially better predictor of registry
headcount than raw house count (R²=0.256 log-log vs. 0.043) — applied to
`supply_calculator.py`, which now apportions each farm's nutrient total
by floor-area share rather than an even per-structure split.

**Reproducibility confirmed**: re-running `unet_detect.py` /
`sam_lagoon_refine.py` against the same on-disk `manifest.json` produces
identical output every time (MPS-backend PyTorch inference and Census
geocoding are both empirically deterministic). The only real source of
non-reproducibility is the **live MDE registry itself changing between
pulls** (observed 414→384 active permits within about a week — normal
churn, not a bug) — but the detection scripts never hit the live registry
on their own; only the separate acquisition scripts
(`full_registry_imagery_extraction.py`, `run_phase1.py`) do, and only
when explicitly run to refresh the farm list / manifest.

**Repo hygiene**: a substantial amount of real, tested pipeline code and
these findings sat uncommitted for a long time (some of it going back to
the original U-Net+SAM build). Committed in this session's consolidation
pass — see `git log` for the actual commit history rather than trusting
this narrative alone for what's landed vs. still pending.

**Two loose ends closed this pass**: the 5 previously-unaudited
zero-detection farms (done — see `docs/task1_metrics.md` §4) and the
floor-area apportionment fix to `supply_calculator.py` (done, see above).
**Not done, low priority**: carrying a stable registry ID
(`ai_id`/`registration_no`) through as a join key instead of `farm_name`
(a real but minor risk — one known name collision, "Chaudhry Farm,
LLC/Pervaiz Akhtar," two distinct farms 13km apart).

**Still gated, no progress possible without external input**: nutrient-
supply regression against Stephanie's county-level assessment data
(needs requesting it), and a CAFOSat feasibility check as independent
lagoon ground truth (86GB dataset, needs a region-filtered subset check).

**2026-09-02 update, FOURTH session (same day) — read this first, it changes
how to interpret ground-truth comparisons everywhere else in this file.**
User asked to check everything for AFOs with lat/lon as accurately as
possible before starting unpermitted-farm search. Two major findings:

1. **The Soroka & Duren 2016/17 ground truth has a real positional-accuracy
   problem — up to 100-450m per point, varying by farm, not a fixed
   offset.** Found while building a stricter spatial-matching precision/
   recall check (got a scary 45-50%, investigated instead of reporting it
   at face value): direct visual overlay on 3 real 2023 NAIP tiles shows
   our detections sit exactly on the real houses; the GT points sit
   hundreds of meters away on open field. Ruled out a CRS bug on our end
   (tested 6 candidate CRS interpretations of the GT shapefile's raw
   coordinates; only the as-declared one is even close). **Practical
   upshot: don't do point-level spatial matching against this GT dataset —
   it's unreliable. The aggregate count-in-a-shared-buffer ratio this
   project has used throughout (currently 0.81) is NOT affected by this
   and remains the right metric.** Full detail in the plan file.
2. **Full visual QA of all 11 lagoons found 4 were false positives**: Brian
   Harding's 3 (natural ponds in forest clearings — that farm has zero
   detected poultry houses AND zero 2016/17 ground truth anywhere on its
   entire tile, so 3 real manure lagoons there was never plausible) and
   Christopher Both's 1 (a quarry/borrow-pit pond, visible excavated
   ground around it). **Lagoon count is now 7, not 11** — `full_registry_
   sam_lagoon_detections.geojson` and `full_registry_lagoons.kml` both
   updated in place. 2 of the 7 are high-confidence (clearly rectangular,
   directly adjacent to real detected houses); 5 carry `qa_status:
   uncertain_needs_review` (plausible but near residential-looking
   clusters, not unambiguous farm complexes) — flagged, not silently
   trusted or dropped. The same QA pass on 35 stratified house-detection
   sites (all 12 counties, low/mid/high headcount) found exactly one real
   false positive out of 300+ detections reviewed (also on Christopher
   Both, coincidentally — a residential building mistaken for a house).

Also extended coverage to the ~88 farms newly usable after the registry
coordinate fix (see the third-session block below) — imagery acquired for
both sources, U-Net/lagoon detection run, merged into the full-coverage
outputs, then filtered to drop 15 farms that dropped out of active+geocoded
status between registry pulls (stale, not re-checked further). **Final
numbers for the complete, current (402-permit) registry: 2,724 houses, 7
lagoons (2 confirmed, 4 under review, 1 confirmed via this round's spot
check), ground-truth ratio 0.83 (3,236 GT vs. 2,678 detected within
GT-covered farms) — consistent with, slightly better than, the 0.81 figure
on the smaller 329-farm set, a good sign the pipeline holds up at the wider
scale.** `full_registry_unet_tulbure_detections.geojson`,
`full_registry_sam_lagoon_detections.geojson`, and both KML exports all
regenerated to match. Technical Deep Dive Slide 7 updated to these final
numbers (was corrected twice more this session as the coverage/lagoon
numbers kept moving — the version now in the file should be the last
correction needed, but has NOT been visually re-confirmed by the user since
this last edit — get a fresh screenshot before trusting it fully).

**2026-09-02 update, THIRD session (same day) — read this before the block
below it**: worked the priority list left by the second session, in order.
Checked the Task Tracker first: item #2 still "Pending" since 7/2, no PI
update — proceeded on the existing priority order.

1. **Root-caused the ~2.9% true-miss rate** (was "domain shift, unconfirmed").
   Re-measured post-recalibration first (still 9/308 = 2.9% — structurally
   expected, since the filter recalibration can't change raw=0 sites). Then
   actually root-caused each of the 9 individually (ground-truth cross-check
   + visual NAIP inspection, not just re-counting): 1 is outside the model's
   Delmarva training region entirely (Carroll County), 2 are real land-use
   change / no structures visible now despite 2016/17 ground truth existing,
   3 are not-yet-built-out permits (no structures visible near the registry
   point at all), and only **3/308 (~1%)** are genuine unexplained model
   failures on clearly-visible houses — with one concrete, testable lead
   (roof color: the 2 misses aren't uniform, one has a distinctly
   red/brick roof vs. the training set's predominantly white/metal roofs).
2. **SAM lagoon proximity filter**: built it as scoped, found a real
   precision bug in the *already-deployed* pipeline along the way (some
   "confirmed" lagoons were actually rivers/wetlands up to 42,879 m², now
   capped via a new `MAX_AREA_M2` check), but found via full-scale testing
   (not just the 4-farm pilot that looked fine) that the recall-widening
   half over-triggers on cropland/forest at scale. Shipped the precision fix
   as the default; the recall-widening code exists but is off by default
   (`--enable-recall-widening`) pending more work (ideally NDWI/NIR, not
   available in these RGB-only tiles). **Full-scale re-run with the fix:
   11 lagoons (was 17 — the 6 removed were the implausibly-large false
   positives, not real detections lost)**. `full_registry_sam_lagoon_detections.geojson`
   and `full_registry_lagoons.kml` both regenerated to match. **The "17
   lagoons" figure anywhere below this point (including the whole second-
   session write-up right under this one) is now stale — 11 is current.**
   Full detail incl. the exact false positives found:
   `/Users/umeshadari/.claude/plans/eager-waddling-graham.md`.
3. **Fixed the registry coordinate gap**: two real, independent bugs (a
   geocoding-trigger mask that only matched a placeholder value, never true
   NaN; and a Census API response parser that used a naive comma-split
   instead of real CSV parsing, so it silently matched 0 addresses even once
   triggered). Active permits missing lat/lon: **95/414 (23%) → 12/414
   (2.9%)**. Not yet re-run through imagery acquisition this session — the
   ~80 newly-geocoded farms aren't in the current 329-site detection run.
5. **Reworked Technical Deep Dive Slides 7-8 in place** (text-only edits via
   python-pptx run reassignment, no shape/slide add-remove-reorder — the
   corruption-safe approach given last time's `_sldIdLst` bug): Slide 7 now
   states the corrected filter-is-the-gap finding (was the older "mostly
   demolition" framing) with updated numbers (2,242 houses, ratio 0.81, 11
   lagoons). Slide 8 now shows this session's 3 resolved items plus the
   genuinely-still-open ones. Zip integrity and slide count verified
   programmatically (`zipfile.testzip()` clean, 20 slides, no duplicate
   entries) — **but this machine has no LibreOffice, so the actual visual
   render (text overflow, overlap) has NOT been confirmed. Get a real
   screenshot from the user before trusting this is visually clean** (a
   backup of the pre-edit file is at
   `/private/tmp/claude-501/-Users-umeshadari-XylemLab-GEO-ANOM/ce48462e-1217-4468-b4e0-bc411c626b07/scratchpad/Deep_Dive_before_slide78_edit.pptx`
   if a revert is ever needed — path is session-scoped and won't survive,
   copy it out if you need it later).

Still open, in priority order: (4) unpermitted-farm search via
`temporal-cluster-matching` — not started; (6) PI decision on priority
(unpermitted vs. known-AFO) — still unanswered as of this write-up,
re-checked the tracker directly.

**2026-09-02 update (second session), read before citing any accuracy number below**: found
and downloaded the actual ground truth Microsoft's model was trained on
(Soroka & Duren 2020, 6,013 hand-labeled houses, USGS,
`data/raw/external/soroka_duren/`) and compared it against our detections.
Real finding: our filter (not the model) is the dominant source of the gap
vs. 2016/17 ground truth — raw model output matches ground truth almost
exactly (ratio 1.07), but the Tulbure filter keeps only ~63-69% of it,
uniformly across farm sizes. **Acted on it, same session**: found 10 clean
near-miss cases (real houses, 60-106m long, rejected only for being below
Tulbure's NC-derived 100m length floor); verified the fix couldn't reopen
the one confirmed false positive (still fails independently on width/area);
applied in `scripts/unet_detect.py` (`AREA_MIN_M2` 500, `LENGTH_MIN_M` 55,
`ASPECT_MIN` 2.5); re-ran full scale. Result: **2,242 houses (was 1,965),
ground-truth ratio 0.70 -> 0.80**, zero regression on the Alan C. Eck
validation anchor (still 9/9), visually re-confirmed on the fragmentation
case study (Sheng Lin Farm) with no new false positives. Also: the
"17 lagoons vs. 1,965 houses" comparison in earlier framing was apples-to-
oranges — broiler operations (92% of the registry) don't use lagoons at
all (dry litter management); 17 is plausible for the ~13 permits that are
actually lagoon-relevant types. Full detail, including a real python-pptx
pitfall hit while updating the deck (deleting slides via `_sldIdLst`
without removing the underlying part causes duplicate zip entries — real
corruption risk, caught via `zipfile.testzip()`, reverted to a clean
backup), is in `/Users/umeshadari/.claude/plans/eager-waddling-graham.md`.
KML exports for both layers are done:
`data/processed/detections/full_registry_poultry_houses.kml` and
`full_registry_lagoons.kml`. The Technical Deep Dive deck's Slides 7-8
still have the OLDER, less accurate "mostly demolition" framing — needs
a redo with the corrected finding before next use.

## What this project is

GEO-ANOM: GeoAI framework to map AFO (Animal Feeding Operation) manure
supply and crop nutrient demand in Maryland, then optimize where to put
waste-to-resource facilities. Three tasks: Nutrient Supply Mapping (NSM),
Nutrient Demand Mapping (NDM), Geospatial Optimization Modeling (GOM).
Team task tracker (Google Sheet, shared Drive) assigns Umesh: AFO
extraction/clustering from satellite imagery. As of this write-up, Task
Tracker item #2 has been "Pending" since 2026-07-02 with no update in the
live sheet — check it for anything newer than this file.

## Where things actually stand — Task 1 (NSM)

**The technical approach changed this session.** The 2026-07-20 write-up's
from-scratch classical CV detector (color/shape heuristics) hit a real
ceiling: five different discriminators were tried to fix its one known
false-positive class (farm roads) and none worked without cutting real
recall (see `imagery_extraction_experiment_2026-07-20.md` and the code
comments in `scripts/classical_cv_detector.py` for the full account). That
dead end led to research that found this problem already has a validated,
openly-licensed answer, and the pipeline now uses it instead of continuing
to hand-tune heuristics.

### Poultry house detection — now a real, validated ML pipeline

- **Model**: Robinson, Chugg, Anderson & Ho (2022), *Mapping industrial
  poultry operations at scale with deep learning and aerial imagery*, IEEE
  JSTARS — a U-Net trained specifically on Delmarva poultry barns.
  MIT-licensed code, published checkpoint. Training labels: Soroka & Duren
  (2020), USGS data release, doi:10.5066/P9MO25Z7 (6,013 hand-labeled
  barns, our exact region). **This is a validated baseline we're building
  on, not our own detector — cite it as such in any deck or write-up.**
- **Filter**: Tulbure, Caineta et al. (2024), *GeoHealth* — a
  literature-validated false-positive filter (area/length/width/aspect/
  road-distance), tighter than Microsoft's own, built for exactly the
  eventual "find unpermitted operations" goal. Length/area upper bounds
  were widened from their NC-derived values after direct visual
  verification that Maryland's largest farms have genuinely longer houses
  (confirmed on Minh Vinh, our highest-headcount permit — see
  `scripts/unet_detect.py` for the exact thresholds and reasoning).
- **Imagery**: switched from MD iMAP (confirmed RGB-only via its ArcGIS
  service metadata — the model needs true 4-band RGB+NIR) to the
  **Microsoft Planetary Computer NAIP STAC API** — public, no-auth,
  current (2023) imagery. Resampled to ~1m during the read (native MD
  imagery there is 0.3m, which would both bloat file size ~10x and badly
  mismatch the model's trained-on scale).
- **Results (329 active permits with usable coordinates), superseded by the
  filter recalibration at the top of this file**: originally 1,965 filtered
  poultry-house detections (Spearman ρ=0.470, p<0.00001, between registry
  headcount and detection count), later improved to **2,242 detections**
  after fixing the filter's overly-strict length floor (see top note) —
  ground-truth accuracy went 0.70 to 0.80. Headcount correlation dipped
  slightly to ρ=0.435 as a side effect (more small houses now counted).
  Stratified visual QA (20 sites, 6 counties, headcount 36K-595K): **zero
  false positives found** in the sample (pre-recalibration; re-confirmed
  no new false positives on the fragmentation case study post-recalibration
  too). Known limitation (pre-recalibration numbers, likely improved some
  by the fix but not re-measured): ~7.8% of poultry farms show zero passing
  detections, split between ~2.9%
  genuine unexplained misses (root cause not pinned down — domain shift
  is the leading hypothesis) and ~4.9% raw-detections-filtered-out (partly
  a real "fragmentation" failure mode — a single house's mask patchy
  along its length gets split into pieces each too short to pass the
  length filter individually — partially mitigated with a morphological
  close, not fully solved).
- Old classical-CV output (`data/processed/detections/top10_classical_cv_detections.geojson`,
  122 houses/2 lagoons on 10 pilot tiles) is kept as a comparison baseline,
  not the primary result.

### Lagoon detection — real progress, still the weaker half

No open pretrained lagoon model exists (checked: PRISM-CAFO's code has no
license and no published weights; DASAM's code is request-only with no
confirmed weights; CAFOSat has real labeled data but is 86GB with no
pretrained model — a next-project-scale undertaking, not something to
start mid-session). Built a working refinement pipeline instead:
**classical CV's existing lagoon color-detector generates candidate boxes
→ Meta's Segment Anything Model (SAM, Apache 2.0, no training needed)
refines each into a pixel-accurate mask → a solidity filter
(mask_area/convex_hull_area ≥ 0.85) rejects irregular natural
ponds/lakes.** Empirically validated: on a deliberately loosened candidate
threshold, the known natural lake on site_04 scores solidity=0.603
(correctly rejected) vs. real lagoons at 0.908/0.970 (correctly kept).
**Important caveat found in the same test**: loosening the candidate
threshold for better recall also picks up residential swimming pools,
which are just as geometrically regular as real lagoons — solidity alone
can't tell them apart. Safely exploiting that recall gain would need an
additional filter (e.g. proximity to a detected poultry house, using the
barn detector's own output) — not built this session; the deployed
pipeline uses the original tight threshold, so it matches prior recall
with better boundary precision, not a recall improvement yet.
Script: `scripts/sam_lagoon_refine.py`. Full-scale results: see
`data/processed/detections/full_registry_sam_lagoon_detections.geojson`.

### A downstream bug this session found and fixed

`geo_anom/phase2/supply_calculator.py` (pre-existing code, never exercised
against real multi-barn-per-farm detection volume before) had two bugs
that would have silently corrupted any nutrient-supply number computed
from this pipeline's output:
1. Animal-type string matching was exact-match only and didn't recognize
   the registry's real raw values (`"chickens_not_laying_hens"`, etc.) —
   the dominant type, broilers, silently computed to **zero** nitrogen/
   phosphorus. Fixed with a keyword classifier (careful of the
   `"not_laying"` vs `"laying"` substring trap — see code comments).
2. Nutrient totals were attached in full to every detected barn at a farm
   with no per-barn division, so summing across a multi-barn farm
   overcounted by however many barns it had (invisible with the old
   ~71-detection dataset; certain with the new pipeline's 5-20 barns/farm).
   Fixed: now apportions each farm's total across its `n_structures_at_farm`.

Both fixed and verified with synthetic tests this session — see the code
and `/Users/umeshadari/.claude/plans/eager-waddling-graham.md` for details.

## Open decision — still not answered by the PIs

Unchanged from 2026-07-20: "find unpermitted AFOs" vs. "quantify structures
at known AFOs" was never answered in the Task Tracker (still "Pending" as
of this write-up, 6+ weeks later). This session proceeded on direction from
Umesh directly: master the detector against known registry targets first
(a tractable, well-defined problem with real ground truth to validate
against), with unpermitted-farm search as the explicit next phase — not a
PI-level resolution of the original question, just a practical way to make
progress while it's outstanding. **Check the Task Tracker / meeting notes
before assuming this is settled.**

The concrete next-phase mechanism for unpermitted-farm search, found this
session: Microsoft's `temporal-cluster-matching` (MIT-licensed) was built
specifically using poultry-barn footprints from the Delmarva Peninsula — it
detects when a structure was built by diffing NAIP imagery across years.
Not started; a real, well-scoped next step once someone picks this back up.

## Where the rest of the project material lives

- **Team Task Tracker** (Google Sheet, shared Drive folder
  `0AAmNA5LcjvWmUk9PVA`) — source of truth for who's doing what. Checked
  directly this session (2026-09-01): item #2 still "Pending," no notes
  added since 2026-07-02.
- **Resources doc** — "GEO-ANOM – Data Sources & Tools" (Google Doc, same
  shared Drive folder). One correction found this session: its listed
  Socrata resource ID for the MDE registry (`xwak-3f7s`) 404s; the working
  one is `s4e3-7tuu` (already correct in `configs/maryland.yaml`).
- **`/Users/umeshadari/XylemLab/GEO-ANOM/`** (separate local folder,
  git-initialized 2026-08-13) — proposal decks. Not updated with this
  session's findings yet — see "Still open" below.
- **This session's full technical narrative and plan**:
  `/Users/umeshadari/.claude/plans/eager-waddling-graham.md` — every
  finding, dead end, fix, and verification from this session in detail,
  more granular than this file.

## Practical notes for continuing work here

- This machine's Python is 3.9 (system CommandLineTools python) — no
  Homebrew, no Node, no LibreOffice.
- **Newly installed this session**: `torch` 2.8.0 (was already present,
  unexpectedly — Apple Silicon, MPS backend available, no CUDA),
  `segmentation-models-pytorch`, `segment-anything`. All small,
  Python-3.9-compatible, no issues.
- **Model checkpoints on disk** (gitignored, `data/models/`):
  `train-all_unet_0.5_0.01_rotation_best-checkpoint.pt` (poultry barn
  U-Net, 60MB — Microsoft's README says 465MB, that figure is stale) and
  `sam_vit_b_01ec64.pth` (SAM, 358MB).
- NAIP imagery: MD iMAP (`geo_anom.phase1.naip_downloader`) is confirmed
  **RGB-only** (checked its ArcGIS service metadata directly — no NIR
  despite the "RGBN" name previously in the config comments, now
  corrected). For 4-band imagery, use `scripts/planetary_computer_naip.py`
  (Microsoft Planetary Computer, public, no auth, but resamples native
  0.3m MD imagery to 1m — read the code comments before changing that).
  **Known bug in that script**: with concurrent downloads
  (`--max-workers`), `manifest.json` entries land in completion order, not
  submission order. Any code touching that manifest must read the stored
  `tile_path` field directly — never reconstruct filenames from list
  position (this caused a real, corrupted validation result this session
  before being caught and fixed).
- GCP/Earth Engine credentials: still never configured on this machine,
  still not needed for anything built so far (all data volumes this
  session stayed in the single-digit GB range even at 329-site scale).

## Still open for the next session (as of 2026-09-02; superseded by the
## 2026-09-14 block at the top of this file — kept here for history)

1. ~~Two `supply_calculator.py` bugs~~ — fixed.
2. ~~Stratified visual QA at full scale~~ — done (20 sites), found the
   fragmentation issue, partially fixed.
3. Root-cause the remaining ~2.9% true-miss rate (domain shift is the
   leading hypothesis, unconfirmed).
4. ~~Lagoon detection~~ — SAM refinement pipeline built and validated;
   recall improvement path (proximity-to-barn filter to safely loosen the
   candidate threshold) identified but not built.
5. **Update the Technical Deep Dive and Progress Tracker decks** with this
   session's results and the PI-facing framing (cite Microsoft/Tulbure/SAM
   properly; the real novel contribution is registry cross-referencing +
   lagoon detection + Task 2/3 integration, not the barn detector itself)
   — in progress as of this write-up.
6. Registry coordinate gap (95/424 permits with no usable lat/lon —
   `geocode_with_census`'s fallback only triggers on the MD-centroid
   placeholder, never on true NaN) and the unpermitted-farm search itself
   — both flagged, neither started.

## Still open as of 2026-09-14 (current priority order)

1. ~~Lagoon detection rebuild on Planetary Computer imagery~~ — done,
   registration bug confirmed fixed. **New open item**: full-scale
   candidate-generation precision (~1/10 on a preliminary audit) — needs
   either a labeled training set for a real classifier, or full manual
   verification of the 74 candidates in
   `full_registry_pc_lagoon_detections.geojson` before any lagoon count
   is usable. Not started; see `docs/task1_metrics.md` §5.
2. External validation (nutrient regression vs. Stephanie's county data,
   CAFOSat feasibility) — gated on outside input, not actionable yet.
3. Stable registry ID as a join key instead of `farm_name` — real, minor,
   independent cleanup, not urgent.

---

## Appendix: 2026-07-20 write-up (superseded above, kept for history)

Zero-shot detection (YOLO-World, `yolov8x-worldv2.pt`, no training data)
tested on the 10 highest-headcount AFO permits. **Result: 0 poultry
houses, 0 lagoons found**, even on sites with 12+ houses clearly visible
by eye — a model-capability gap, not a data problem. Pivoted to classical
computer vision (OpenCV, color + shape filtering). **Result: 122 poultry
houses + 2 lagoons found, no training data needed**, precision good but
not perfect (one false positive on site 6, lagoon recall likely
incomplete). Full writeup:
[`imagery_extraction_experiment_2026-07-20.md`](imagery_extraction_experiment_2026-07-20.md).
Known bug flagged then and since fixed: `configs/maryland.yaml` had
`yolo_world.confidence_threshold: 0.01`, producing an unreliable
70-detection sample.
