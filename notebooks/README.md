# Task 1 notebooks

Step-by-step checks of the Task 1 pipeline. They call the same code as the
scripts (`geo_anom/task1/`), so a problem you see here is a problem in the
full run.

| Notebook | What you check |
|---|---|
| `01_map_buildings.ipynb` | One farm at a time: tile → U-Net probability → mask → shapes → filter (with the reason for every rejection) → boxes on the image → your own TP/FP/FN count → KMZ by animal type |
| `03_full_dataset.ipynb` | Run all 417 farms (or load the latest run) and look at everything: statewide map, distributions, rejection reasons, a gallery of every farm, zero-detection farms |
| `02_supply_check.ipynb` | N/P₂O₅ from a full run: coefficients against the AWTF report, one farm recomputed by hand, totals by species |

## Run

```bash
python3 -m jupyter lab notebooks/
```

Or in **VS Code** (Python + Jupyter extensions): open the repo folder, open a
notebook, and pick the kernel *Python 3.9* at
`/Library/Developer/CommandLineTools/usr/bin/python3`, which is the
interpreter with torch/rasterio/geopandas installed. Any other interpreter
will fail on the imports.

`00_workshop_walkthrough.ipynb` is the audience version used at the
2026-10-07 knowledge-sharing workshop (code collapsed, ~15 s end to end).

The full pipeline, outside the notebooks:

```bash
python3 scripts/map_buildings.py                                  # all 417 farms -> data/processed/task1/run_<date>/
python3 scripts/compute_supply.py data/processed/task1/run_<date>
python3 scripts/map_buildings.py --farm "Sheng Lin" --out-dir notebooks/output/one_farm   # a quick subset
```

`map_buildings.py` writes `buildings.geojson` (one row per physical
building, de-duplicated across overlapping tiles), `candidates.geojson`
(everything the U-Net proposed, kept or not, with reasons), `farms.csv`,
`buildings.kmz`, and `run_meta.json` (git commit, checkpoint and manifest
hashes, thresholds) so any number can be traced to the exact run.

Clear outputs before committing a notebook (Kernel → Restart & Clear
Outputs); `notebooks/output/` is git-ignored.
