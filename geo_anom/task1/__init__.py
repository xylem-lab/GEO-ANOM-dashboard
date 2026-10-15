"""
Task 1 (Nutrient Supply Mapping) pipeline.

One importable module shared by the command-line scripts and the notebooks
in `notebooks/`, so what you inspect step by step in a notebook is exactly
the code the full run uses -- no copy-pasted variants.

    tiles   -- load a manifest, download/read 4-band NAIP tiles
    detect  -- Robinson et al. U-Net inference + Tulbure et al. shape filter
    merge   -- de-duplicate across overlapping tiles, attribute to permits
    species -- registry animal_type -> species group
    kmz     -- Google Earth export, one marker style per animal type
    supply  -- N / P2O5 per farm and per building

Scripts:
    scripts/map_buildings.py   tiles -> buildings.geojson + buildings.kmz
    scripts/compute_supply.py  buildings.geojson -> N/P tables
"""
