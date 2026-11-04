# Task 2 coefficients: how to change them

Notebook 13 (`notebooks/13_task2_nutrient_balance.ipynb`) reads every number from one sheet:
**`Task2_results/coefficients.csv` on the shared drive.** The repo keeps the defaults in
`data/reference/task2_coefficients.csv`; the first run copies them to the drive.

To change a number:
1. Open `Task2_results/coefficients.csv` (Excel or Google Sheets; save it back as CSV with the same columns).
2. Edit `low`, `mid`, `high` (keep low <= mid <= high; set all three equal to fix a value), and put
   where it comes from in `source`. Set `status` to `confirmed` once it is agreed.
3. Rerun notebook 13. Every table, map and the translocation update. The notebook lists the rows that
   differ from the defaults, and each run records the sheet's SHA-256 in `Task2_results/draft_v1/run_meta.json`.

| column | meaning |
|---|---|
| name | the coefficient (don't rename) |
| low / mid / high | the range; tables use mid, the uncertainty draws between low and high (triangular) |
| unit | what the number is |
| step | supply (houses -> litter -> nutrients) or demand (cropland need) |
| status | literature / assumption / contested / confirmed |
| source, note | where it comes from |

**Most important to pin down** (largest effect on the Eastern Shore surplus in draft v1):
1. `P_rate_multiplier`: P applied on soils below the high-P threshold vs crop removal (DLLC 2019's contested "medium vs optimum" category).
2. `birds_per_ft2`: stocking density at placement for Delmarva broilers.
3. `P_lb_per_ton`: P in today's Maryland litter (per wet ton).
4. `litter_lb_per_bird`: litter per bird marketed (UD 2.3-3.0; a 2026 Delmarva study ~25% below the Bay model).
5. `high_P_offset`: correction to the DLLC fit of the share of cropland too high in P.

Also wanted: Maryland Nutrient Management Manual first-year litter N availability (`N_available`), corn
and small-grain N rates by yield goal, county active-house counts.
