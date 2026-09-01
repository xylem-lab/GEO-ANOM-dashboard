# Start Here — Project Status as of 2026-07-20

Read this file first in any new session working on GEO-ANOM. It's the
single pointer to everything else.

## What this project is

GEO-ANOM: GeoAI framework to map AFO (Animal Feeding Operation) manure
supply and crop nutrient demand in Maryland, then optimize where to put
waste-to-resource facilities. Three tasks: Nutrient Supply Mapping (NSM),
Nutrient Demand Mapping (NDM), Geospatial Optimization Modeling (GOM).
Team task tracker (Google Sheet, shared Drive) assigns Umesh: AFO
extraction/clustering from satellite imagery, plus a data-sources/tools doc.

## Where things actually stand

**Task 1 (NSM) — the only task with real experimentation so far:**
- Zero-shot detection (YOLO-World, `yolov8x-worldv2.pt`, no training data)
  tested on the 10 highest-headcount AFO permits. **Result: 0 poultry
  houses, 0 lagoons found**, even on sites with 12+ houses clearly visible
  by eye. Confidence stuck at 0.01–0.02. This is a model-capability gap,
  not a data problem — confirmed by manually viewing the raw tiles.
- Pivoted to classical computer vision (OpenCV, color + shape filtering —
  poultry houses are bright/elongated, lagoons are teal/turquoise).
  **Result: 122 poultry houses + 2 lagoons found, no training data
  needed.** Spot-checked visually against 3/10 annotated tiles: precision
  is good but not perfect (found one false positive — a farm road boxed
  like a house, on site 6) and lagoon recall is unverified/likely
  incomplete (one darker lagoon was missed on site 4, next to the one
  correctly found). **Not yet checked across all 10 sites.**
- Full writeup: [`imagery_extraction_experiment_2026-07-20.md`](imagery_extraction_experiment_2026-07-20.md)
- Script: `scripts/classical_cv_detector.py`. Output:
  `data/processed/detections/top10_classical_cv_detections.geojson`,
  annotated images in `docs/imagery_experiment_assets/`.
- **Known bug worth fixing/flagging**: `configs/maryland.yaml` has
  `yolo_world.confidence_threshold: 0.01` — the *old* 70-detection sample
  dataset shown in the dashboard came from that artificially low
  threshold and isn't reliable signal.

**Tasks 2 (NDM) and 3 (GOM):** not started for real. Task 3 has an
existing PuLP P-median solver prototype (pre-dates official kickoff,
per `STATUS.md`) but it only runs on self-reported permit headcounts,
not on anything from Task 1 — and its financial outputs (NPV, hub count,
payback period) are explicitly flagged as unverified, not for citation,
until the PIs review the prototype.

## Open decision — needs a PI answer

Two different things could count as "continuing the imagery work," and
they're not the same effort level:
1. **Find AFOs the registry is missing** (unpermitted/new farms) — a
   simpler "find any ag-building cluster" problem.
2. **Quantify structures at AFOs we already know about** (count/size
   poultry houses, measure lagoon area) — the actual differentiator vs.
   just using self-reported headcounts, and what Task 1 in the proposal
   is really about.

This was raised as a talking point for the 2026-07-20 team meeting but
not yet answered as of this writeup. **Check the Task Tracker / meeting
notes for the answer before picking a direction.**

## Where the rest of the project material lives

- **Team Task Tracker** (Google Sheet, shared Drive folder
  `0AAmNA5LcjvWmUk9PVA`) — source of truth for who's doing what, due dates,
  status. Check this first for anything that changed after 2026-07-20.
- **Resources doc** — "GEO-ANOM – Data Sources & Tools" (Google Doc, same
  shared Drive folder) — data sources/tools list with links.
- **`/Users/umeshadari/XylemLab/GEO-ANOM/`** (separate local folder, now
  git-initialized as of 2026-08-13) — the original AIM LOI proposal deck,
  plus two decks that were substantially rewritten this session:
  - `GEO-ANOM_Technical_Deep_Dive.pptx` — rewritten twice: first to strip
    grant-pitch language and ground every claim in actual repo state
    (built/tested vs. prototype vs. not-started), then restructured again
    so Tasks 1–3 each list **candidate approaches** (tried and untried)
    instead of a single linear pipeline. Slide 5 (Task 1) is the most
    substantive — it has the real zero-shot-vs-classical-CV comparison.
  - `GEO-ANOM_Progress_Tracker.pptx` — filled in real numbers (442 permits,
    350 geocoded, 41.2M animals) where verified; deliberately left NPV/
    payback/hub-count as TBD since those come from the unreviewed
    prototype.
  - Neither deck has been visually rendered/QA'd — this machine has no
    LibreOffice or Node.js, so all edits were text-only via python-pptx
    with no visual preview. Worth a skim in real PowerPoint before reuse.

## Practical notes for continuing work here

- This machine's Python is 3.9 (system CommandLineTools python) — no
  Homebrew, no Node, no LibreOffice. `ultralytics`/`torch` aren't
  installed; `geopandas`/`rasterio`/`opencv-python`/`shapely` are.
  Anything requiring `str | None`-style modern type syntax or `match`
  statements will fail on this interpreter.
- The dashboard repo (`GEO-ANOM-dashboard`) is the one with real code,
  data, and git history — work there, not in the proposal folder, for
  anything beyond slide edits.
- NAIP imagery pulls (`geo_anom.phase1.naip_downloader`) need no
  credentials — public MD iMAP ArcGIS REST endpoint. Everything else
  needing GCP/Earth Engine credentials (`.env`) has never been configured
  on this machine — treat as unavailable until proven otherwise.
