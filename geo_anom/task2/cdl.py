"""
USDA NASS Cropland Data Layer (CDL) for Maryland: where each crop is, at 30 m.

    ensure_cdl(2023)                 Maryland GeoTIFF for one year (~90 MB), from
                                     the shared drive copy if there is one, else
                                     from NASS CropScape; SHA-256 recorded
    crop_acres_on_grid(path, codes)  acres of the given CDL classes in each grid
                                     cell (cells as in balance.cell_index)

Why NASS and not Planetary Computer: Planetary Computer's `usda-cdl` stops at
2021; our NAIP imagery is 2023. The CropScape state file is the official
product, clipped to Maryland (FIPS 24).

Sanity check (2023): 523,640 acres of class 1 corn in the Maryland file,
against ~510,000 acres planted in the NASS 2023 survey.

Limits that belong next to any number from here:
- Maryland only. Delmarva houses near Delaware / Virginia lines have cropland
  across the line that this file doesn't see.
- One year is a snapshot: fields rotate (corn / soybeans / wheat, corn / hay),
  so use several years (`years=`) to get the average corn area of a place.
- CDL accuracy for corn in Maryland is high but not perfect (NASS publishes
  per-state accuracy tables); small or mixed fields are the weakest.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

import numpy as np
import requests

from geo_anom.task1.tiles import ROOT

MD_FIPS = "24"
CACHE = ROOT / "data/raw/external/cdl"
SERVICE = "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile?year={year}&fips={fips}"
SOURCE = "USDA NASS Cropland Data Layer, CropScape (nassgeodata.gmu.edu)"
PIXEL_ACRES = 30 * 30 / 4046.8564224
# Files as first downloaded for this project (NASS can re-issue a year; a
# different hash is reported, not refused, and every run records the hash it used)
KNOWN_SHA256 = {
    2023: "703c9a8bb1cfef86d317a4911317544218b5cf2a2938dc16cebc250edefc6ee7",
}

# CDL class codes (NASS legend). Double crops that include corn count as corn.
CROP_GROUPS = {
    "corn": [1, 225, 226, 237, 241],                 # corn; dbl crop wheat/corn, oats/corn, barley/corn, corn/soy
    "soybeans_small_grains": [5, 21, 23, 24, 26, 27, 28, 254],  # soy, barley, spring/winter wheat, wheat/soy, rye, oats, barley/soy
    "hay_pasture": [36, 37, 176],                    # alfalfa, other hay, grassland/pasture
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_cdl(year: int = 2023, drive_dir: Path | None = None, log=print) -> dict:
    """Local path + provenance of the Maryland CDL for `year`.

    Looks in the local cache, then `drive_dir` (e.g. Task1_results/reference),
    then downloads from NASS. A fresh download is also copied to `drive_dir`
    so the next Colab session doesn't depend on the NASS server.
    """
    name = f"CDL_{year}_{MD_FIPS}.tif"
    p = CACHE / name
    if not p.exists() and drive_dir is not None and (Path(drive_dir) / name).exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(drive_dir) / name, p)
    if not p.exists():
        log(f"Downloading the {year} Cropland Data Layer for Maryland from NASS (~90 MB) ...")
        r = requests.get(SERVICE.format(year=year, fips=MD_FIPS), timeout=120)
        r.raise_for_status()
        m = re.search(r"<returnURL>(.*?)</returnURL>", r.text)
        if not m:
            raise RuntimeError(f"CropScape gave no file for {year}: {r.text[:200]}")
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".part")
        with requests.get(m.group(1), stream=True, timeout=300) as d:
            d.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in d.iter_content(1 << 20):
                    f.write(chunk)
        tmp.rename(p)
        if drive_dir is not None:
            Path(drive_dir).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, Path(drive_dir) / name)
    sha = _sha256(p)
    if year in KNOWN_SHA256 and sha != KNOWN_SHA256[year]:
        log(f"Note: CDL {year} differs from the file first used ({sha[:12]}... vs "
            f"{KNOWN_SHA256[year][:12]}...); NASS may have re-issued it. The hash is recorded.")
    return {"year": year, "path": str(p), "sha256": sha, "source": SOURCE}


def class_acres(path: str | Path) -> dict:
    """Acres of every CDL class in the file (for sanity checks)."""
    import rasterio
    with rasterio.open(path) as src:
        a = src.read(1)
    v, c = np.unique(a, return_counts=True)
    return {int(k): float(n * PIXEL_ACRES) for k, n in zip(v, c) if k != 0}


def crop_acres_on_grid(path: str | Path, codes: list[int], cell_m: float, utm: str = "EPSG:32618"):
    """{(ix, iy): acres} of the given CDL classes, binned into cell_m squares
    of the UTM grid (cell = floor(x / cell_m), floor(y / cell_m)).

    Each 30 m pixel goes to the cell holding its centre.
    """
    import rasterio
    from pyproj import Transformer

    with rasterio.open(path) as src:
        a = src.read(1)
        t, crs = src.transform, src.crs
    rows, cols = np.nonzero(np.isin(a, codes))
    del a
    xs = t.c + (cols + 0.5) * t.a        # pixel centres (north-up file, no rotation terms)
    ys = t.f + (rows + 0.5) * t.e
    x, y = Transformer.from_crs(crs, utm, always_xy=True).transform(xs, ys)
    ix, iy = np.floor(x / cell_m).astype(int), np.floor(y / cell_m).astype(int)
    keys, counts = np.unique(np.stack([ix, iy], axis=1), axis=0, return_counts=True)
    return {(int(i), int(j)): float(n * PIXEL_ACRES) for (i, j), n in zip(keys, counts)}
