# GEO-ANOM-dashboard — instructions for Claude sessions

GeoAI for Maryland animal feeding operation (AFO) mapping and nutrient supply
(AIM seed grant; PIs Catherine Nakalembe, Stephanie Lansing). This repo holds
the pipeline. Proposal/decks live in the sibling `../GEO-ANOM` repo (LOI:
`Nakalembe_Lansing__AIM_LOI2026_Final.docx`).

## Read first
1. `docs/NEXT_SESSION.md` — **top dated section only**; it supersedes
   everything below it. Never cite a number from an older section without
   checking the newer ones.
2. `docs/research_log.md` — latest entries, so you don't re-try rejected ideas.
3. `notebooks/README.md` — how to run Task 1.

`START_HERE.md`, `STATUS.md`, `EXECUTIVE_SUMMARY.md`, `REALISTIC_ACTION_PLAN.md`
and the other root-level `*.md` files are from the March 2026 dashboard
prototype. They are stale; don't treat them as current status.

## How Task 1 runs (since 2026-10-05)
- All detection/supply code: `geo_anom/task1/` (tiles, detect, merge,
  species, kmz, supply, viz).
- `scripts/map_buildings.py` → `data/processed/task1/<run>/` (buildings,
  farms.csv, KMZ by animal type, run_meta.json with commit/checkpoint/manifest
  hashes). Then `scripts/compute_supply.py <run_dir>` for N/P.
- `notebooks/01_map_buildings.ipynb`, `02_supply_check.ipynb` call the same
  functions for step-by-step checks.
- Current baseline: `data/processed/task1/run_2026-10-07/` (1,831 unique
  buildings) on tiles in `data/raw/naip_tiles_pc_4band_v2/`. **Tiles in
  `naip_tiles_pc_4band_full/` and `_delta/` are shifted/stretched for 219/417
  sites (download bug fixed 2026-10-07) — never use them**, and treat every
  number computed from them (`run_2026-10-05`, the 2,726-feature
  `full_registry_unet_tulbure_detections.geojson`, R² 0.655, 99.7% precision,
  82% MDE crosscheck) as superseded until recomputed.
- Change detection logic in `geo_anom/task1/`, not in new one-off scripts.
  `scripts/unet_detect.py` / `unet_inference.py` are compatibility wrappers.
  After any change, rerun a few farms and compare with the baseline before
  claiming an improvement.

## Rules this project has learned the hard way
- **Ground truth over self-reported numbers.** Look at the imagery (render
  crops with `geo_anom/task1/viz.py` and view the PNG) before calling a
  detection real or a number validated. Several "confirmed" results were
  wrong when someone finally looked (lagoons: 1 of 7 real).
- **Do not present N/P totals.** The broiler N coefficient in
  `configs/maryland.yaml` gives 13.8x the AWTF 2023 statewide figure; it's
  unresolved and is a domain call for Stephanie Lansing's lab.
- Farm names and tile file names are not unique keys; use the full tile path
  (`geo_anom.task1.tiles.site_id`).
- Registry permit points can be hundreds of metres from the real barns, so
  attribution of buildings to farms (nearest permit point) is approximate.
- When checking georeferencing, compare the same object across overlapping
  tiles or against the source image — a single-farm overlay can't show it,
  because the image and the boxes share the error.
- Species comes from the registry permit, not from the detector. Dairy barns
  and lagoons are mostly not detected.
- Git: work on a branch (`experiment/…`, `research/…`, `refactor/…`), open a
  PR, never commit straight to `main`, never auto-merge. No `gh` CLI on the
  user's laptop — give the user the PR URL.
- Compute: this laptop (Apple Silicon, MPS, Python 3.9 — no 3.10+ syntax at
  runtime). Never provision cloud compute or spend funds without asking.
- Document as you go: prepend a dated section to `docs/NEXT_SESSION.md` and
  append to `docs/research_log.md` in the same branch as the work.
