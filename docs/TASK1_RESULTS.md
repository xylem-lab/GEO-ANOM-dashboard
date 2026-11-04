# Task 1 results: poultry houses in Maryland from aerial photos (frozen 2026-11-03)

Rebuilt and scored by `notebooks/11_task1_final_map.ipynb`; validated in `notebooks/12_task1_validation.ipynb`.
The house-level map is on the shared drive only (`Task1_results/final/release_v1/`, with `MANIFEST.json` checksums);
this page holds county totals only.

## From the published model to the final map

Eastern Shore, scored against the USGS hand-traced houses (Soroka & Duren 2020, 2016/17; 3,040 houses) inside the traced area.

| step | houses | roof km² | recall | precision (checked by eye) | roof covered |
|---|---|---|---|---|---|
| 0 published model (Robinson et al. 2022 + Tulbure filter) | 2,329 | 4.85 | 0.670 | 0.990 | 79% |
| 1 rectangle outlines | 2,329 | 5.97 | 0.671 | 0.990 | 91% |
| 2 brightened photo (darkest 2023 flights tone-matched to 2021) | 2,628 | 6.45 | 0.757 | 0.977 | 91% |
| 3 SAM repair (strict house shape) — map v1 | 2,823 | 6.93 | 0.805 | 0.965 | 92% |
| **4 checked by eye — frozen** | **2,807** | **6.91** | **0.805** | **0.970** | **92%** |
| tested, not adopted: road rule (20 m) | 2,810 | 6.92 | 0.802 | 0.966 | 92% |
| tested, not adopted: fine-tuned U-Net (held-out Wicomico + Queen Anne's) | | | 0.787 (map v1: 0.790) | 0.88–0.90 (map v1: 0.96–0.995) | |

The SAM shape rule holds on counties it was not chosen on: picked on one half of the Eastern Shore and scored on the other, recall 0.789 / 0.825 vs 0.786 / 0.823 for the rule in use (no SAM: 0.751 / 0.762).

Precision against the 2016/17 tracing alone is ~0.88 at every step; the difference is mostly houses built since.

## Frozen map

**2,833 houses, 6.98 km² (1,724 acres) of roof, average house 26,500 ft²**: 2,807 on the Eastern Shore + 26 confirmed by eye west of the Bay.

| county | houses | roof acres | recall | precision (checked) |
|---|---|---|---|---|
| Wicomico | 602 | 347 | 0.78 | 0.96 |
| Worcester | 566 | 347 | 0.75 | 0.97 |
| Caroline | 517 | 324 | 0.89 | 0.99 |
| Somerset | 474 | 276 | 0.78 | 0.97 |
| Dorchester | 285 | 177 | 0.86 | 0.99 |
| Queen Anne's | 220 | 152 | 0.83 | 0.99 |
| Talbot | 62 | 33 | 0.77 | 0.91 |
| Kent | 51 | 30 | 0.83 | 0.88 |
| Cecil | 30 | 21 | 0.85 | 1.00 |
| Frederick, Carroll, Washington, Harford | 26 | 18 | — | checked by eye |

## Correcting for the houses the map misses (notebook 12, section 5)

594 of 3,040 traced Eastern Shore houses have no outline. By eye, 21 of 24 of them still stand in 2023 (88%, Wilson 95% range 69–96%), so they are real misses: mostly older, smaller houses on the darkest 2023 flights (traced footprint 1,617 m² vs 2,503 m² for found houses).

**Added roof = traced footprint of the missed houses × outline/footprint ratio k (0.96) × share still standing.** The low end also drops the 3% of outlines not confirmed. The 26 houses west of the Bay are not corrected (no tracing there).

| | houses | roof km² |
|---|---|---|
| mapped | 2,833 | 6.98 |
| **estimated real total** | **~3,350 (3,160–3,400)** | **7.79 (7.41–7.86), +12%** |

Largest corrections: Worcester +15%, Somerset +14%, Wicomico +12%; smallest Caroline +6%. New houses missed outside the tracing are not added, so this is slightly low.

## Validation: does the mapped roof hold the birds Maryland reports?

Roof → floor (0.90–0.96) → birds per ft² at placement (0.9–1.3) → share of days with birds (0.70–0.90) → flocks a year (5–6).

| check | from the map | reported | agreement across counties |
|---|---|---|---|
| birds on hand | 42.6–84.4 M (mid 61.5) | Census of Agriculture 2017: 59.5 M; MDE CAFO 2017: 69.2 M | r = 0.96 / 0.98; Census inside the range in 8 of 8 counties |
| capacity | 60.8–93.7 M (mid 76.8) | MDE permits: 50.9 M | r = 0.99; permits below capacity in every county (below-threshold farms, idle houses) |
| birds a house a year | 107k–199k (mid 149k) | DCA 2024 Delmarva average: 122k | inside the range |

## Why Task 1 stops here

1. The mapped roof is the right size and has the right county pattern: three independent bird counts fall within the assumption ranges (r 0.96–0.99 across counties). This check is too loose to show completeness (its ranges are wider than the misses), so completeness is measured and corrected separately (above).
2. The map misses about 1 in 5 traced houses; we measured the misses and correct the roof for them (+12%). Task 2 uses the corrected roof.
3. The county ranking has not changed since step 2 (Spearman 1.00).
4. The misses sit on the darkest 2023 flights; the two further methods tried did not beat the map. More houses need a brighter NAIP flight, not more model work.

Caveats: one reviewer so far (a second-reviewer sample is set up in notebook 07 section 8); 2017 inventories vs 2023 photos; density and occupancy are literature ranges; the 26 western houses look like another kind of poultry or idle houses (Frederick: 0.57 M birds by roof vs 0.07 M in the Census) and are flagged for Task 2.
