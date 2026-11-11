# Fresh start: GEO-ANOM from 2026-11-05

Read this first in any new session. Then read `docs/PROJECT_AUDIT_2026-11-05.md`
(status, confidence, finishing plan) and the top dated section of
`docs/NEXT_SESSION.md`.

## Prompt for a new chat

Open the new chat in `~/XylemLab/GEO-ANOM-dashboard` and paste:

```markdown
GEO-ANOM (UMD; PIs Catherine Nakalembe and Stephanie Lansing; LOI deliverables due June 2027).
Repo: GEO-ANOM-dashboard (this folder). Shared drive: AIM-GEO-ANOM.

Read first, in order: docs/FRESH_START.md, docs/PROJECT_AUDIT_2026-11-05.md,
the top section of docs/NEXT_SESSION.md, CLAUDE.md.

State as of 2026-11-05:
- Task 1: frozen poultry-house map, release_v1 (2,833 houses, 6.98 km2 roof).
  Eastern Shore recall 80.5% and precision 88.2% against the USGS 2016/17 tracing
  (notebooks 11-12). The 97% precision and the missed-house correction (7.79 km2)
  rest on single-viewer checks and are NOT yet defensible.
- Task 2: draft v1, notebook 13. Coefficient sheet Task2_results/coefficients.csv,
  defaults not yet reviewed by Rafian Aziz. Other nutrient sources, rotations and
  external validation are missing.
- Task 3: not started.

Goal: finish with defensible science, in this order.
1. Design-based accuracy assessment for Task 1 (notebook 14): written protocol,
   stratified random samples (missed traced houses, untraced detections, random
   1 km cells), two blind interpreters, kappa, stratified estimators with 95% CIs.
   This replaces the 21/24 and 97% figures.
2. Task 2 with Rafi: reviewed coefficients, other nutrient sources, multi-year CDL,
   validation against MDA Manure Transport Program tons.
3. LOI objective 2: compare the balance from county averages, permit locations and
   mapped houses.
4. Task 3 siting and LCA.

Rules:
- Every new task is a numbered notebook in notebooks/ (next: 14).
- Branch and PR only; never commit to main; never auto-merge.
- Farm-level data stays on the shared drive, never in git (the repo is public).
- No N/P totals in public outputs until decided.
- No number goes into a summary without its sample, protocol and uncertainty written down.

First step: propose the protocol and the sample design for notebook 14 for my
review before writing code.
```

## Where things are

| What | Where |
|---|---|
| LOI | `../GEO-ANOM/Nakalembe_Lansing__AIM_LOI2026_Final.docx` |
| Task 1 code | `geo_anom/task1/` (`final.py` = ladder, freeze, `miss_correction`; `review.py` = labels, Wilson CI) |
| Task 1 notebooks | 07 (by-eye review; section 8 = blind second-reviewer sample, unfinished), 11 (build + freeze), 12 (validation) |
| Task 1 release (drive only) | `Task1_results/final/release_v1/` (map, county table, ladder, validation, `miss_correction.csv`, MANIFEST.json); KMZ `Task1_results/final/maryland_poultry_houses_final_v1.kmz` |
| Task 1 labels (drive only) | `Task1_results/review/` |
| USGS reference | Soroka & Duren 2016/17 tracing, 3,040 Eastern Shore houses; downloaded and checked by `geo_anom/task1/env.py` |
| Task 1 public summary | `docs/TASK1_RESULTS.md` (county totals only) |
| Task 2 code | `geo_anom/task2/nutrients.py`; notebook 13 |
| Task 2 coefficients | `data/reference/task2_coefficients.csv` → drive `Task2_results/coefficients.csv`; how-to `docs/TASK2_COEFFICIENTS.md` |
| Task 2 outputs (drive) | `Task2_results/draft_v1/` (`translocation_*.csv` there are stale, from before transport was removed) |
| Briefs (drive) | `Task1_results/Task1_completion_summary_2026-11-04.docx` (**hold**: presents 7.79 km² and the 21/24 check); `Task2_results/Rafian_brief_Task2_Task3_2026-11-04.docx` |

## Git state (2026-11-05)

- `main` does not yet have Task 1 or Task 2.
- `task1/final-2026-11-03`: PR open (created by the user). Includes all earlier experiment branches.
- `task2/nutrient-balance-2026-11-03`: on top of task1; no PR yet.
- `docs/fresh-start-2026-11-05`: these handoff files, on top of task2. Merge order: task1 → task2 → this.
- No `gh` CLI on the laptop: give the user compare URLs.

## Open decisions (owner)

- Lagoons: close Task 1 on poultry only, or a short lagoon step? (Nakalembe)
- N/P lb in the paper, or litter tons only? (Lansing / Rafi)
- Include Delaware cropland? Include the 26 houses west of the Bay (currently excluded in Task 2)?
- Second interpreter for Phase 1: ~~Jenny Ha or Pradeep?~~ Monica (decided 2026-11-05).
- Coefficient sheet v1 date with Rafi.

## Do not trust / do not quote

- 97% precision (single reviewer, no protocol) and 21/24 still standing (informal, not random).
- Corrected roof 7.79 km² and the corrected bird numbers built on it.
- Task 2 tons, statewide −444 kt "room", anything N/P.
- Anything computed from `naip_tiles_pc_4band_full/` or `_delta/` tiles (pre-2026-10-07 bug).
- Root-level `*.md` files from the March 2026 prototype.
- Bird-count agreement as proof of completeness (ranges ~2× wide; shows scale and pattern only).

## Unverified references (check before citing)

Olofsson et al. 2014 (RSE, accuracy assessment good practice); Kellogg et al. 2000;
Gollehon et al. 2001; DLLC 2019 mass balance; Spiegal et al. 2020 "Manuresheds";
Kleinman et al. 2012; Lansing et al. 2023 MD Animal Waste Technology report;
Höhn et al. 2014; Silva et al. 2014; Sharara et al. 2017; Sampat et al. 2018;
Huijbregts et al. 2017 (ReCiPe 2016).
