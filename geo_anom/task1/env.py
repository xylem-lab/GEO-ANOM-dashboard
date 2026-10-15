"""
Where things live, so the same notebook runs in Google Colab and locally.

    code        GitHub (xylem-lab/GEO-ANOM-dashboard), cloned at a pinned commit
    imagery     never stored: read from Planetary Computer tile by tile
    model       downloaded from Microsoft's public release, checked by SHA-256
    labels      USGS ScienceBase (Soroka & Duren 2020), checked by SHA-256
    results     the project's shared Google Drive folder "Task1_results"
                (found by its marker file), else data/processed/task1/ locally

results_root() is the only place notebooks should take an output folder from.
"""

from __future__ import annotations

import glob
import hashlib
import os
import platform
import sys
import zipfile
from pathlib import Path

import requests

from geo_anom.task1.tiles import ROOT

IN_COLAB = "google.colab" in sys.modules

RESULTS_MARKER = "GEO-ANOM_RESULTS_ROOT.md"
RESULTS_FOLDER = "Task1_results"
# Google Drive folder id of Task1_results on the GEO-ANOM shared drive (for humans; code uses the marker)
RESULTS_DRIVE_URL = "https://drive.google.com/drive/folders/1orNlxe7O9g8ZHwYDdsvkbb_TvZkYoCRx"

CHECKPOINT = {
    "path": ROOT / "data/models/train-all_unet_0.5_0.01_rotation_best-checkpoint.pt",
    "url": "https://opendata.aiforgood.ai/poultry-cafo/train-all_unet_0.5_0.01_rotation_best-checkpoint.pt",
    "sha256": "b4e68fd86c50cc31178ebe2d0543867ad74d40a61139df732efa529411d0b56f",
    "source": "Robinson et al. (2022), github.com/microsoft/poultry-cafos",
}
GROUND_TRUTH = {
    "zip": ROOT / "data/raw/external/soroka_duren/Delmarva_PL_House_Final.zip",
    "dir": ROOT / "data/raw/external/soroka_duren/Delmarva_PL_House_Final",
    "url": "https://www.sciencebase.gov/catalog/file/get/5e0a3fcde4b0b207aa0d794e"
           "?f=__disk__12%2F87%2Fdd%2F1287dd80c47c49f14474b66fd3d3173398bb94bc",
    "sha256": "6c9140445c7f23eefc9979abec1e4fd67b4e9452b15217136cc694de66153f53",
    "source": "Soroka & Duren (2020), USGS, doi:10.5066/P9MO25Z7",
}


def _drive_candidates() -> list[str]:
    pats = [
        # Colab after drive.mount("/content/drive")
        f"/content/drive/Shareddrives/*/{RESULTS_FOLDER}/{RESULTS_MARKER}",
        f"/content/drive/Shared drives/*/{RESULTS_FOLDER}/{RESULTS_MARKER}",
        f"/content/drive/MyDrive/**/{RESULTS_FOLDER}/{RESULTS_MARKER}",
        # Google Drive for Desktop on a Mac
        os.path.expanduser(f"~/Library/CloudStorage/GoogleDrive-*/Shared drives/*/{RESULTS_FOLDER}/{RESULTS_MARKER}"),
        os.path.expanduser(f"~/Library/CloudStorage/GoogleDrive-*/My Drive/**/{RESULTS_FOLDER}/{RESULTS_MARKER}"),
    ]
    hits = []
    for p in pats:
        hits += glob.glob(p, recursive=True)
    return hits


def results_root(local_fallback: bool = True) -> Path:
    """The shared results folder, or data/processed/task1 when Drive isn't available.

    Override with the environment variable GEO_ANOM_RESULTS=/some/path.
    """
    if os.environ.get("GEO_ANOM_RESULTS"):
        return Path(os.environ["GEO_ANOM_RESULTS"])
    hits = _drive_candidates()
    if hits:
        return Path(hits[0]).parent
    if IN_COLAB:
        raise RuntimeError(f"Shared drive folder '{RESULTS_FOLDER}' not found. Run drive.mount('/content/drive') "
                           f"and check you have access to {RESULTS_DRIVE_URL}")
    if not local_fallback:
        raise RuntimeError("No shared drive found and local_fallback=False")
    return ROOT / "data/processed/task1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(url: str, dest: Path, expected_sha: str):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    got = sha256(tmp)
    if got != expected_sha:
        tmp.unlink()
        raise RuntimeError(f"{url} downloaded but SHA-256 {got[:16]}… != expected {expected_sha[:16]}…")
    tmp.rename(dest)


def ensure_checkpoint() -> Path:
    """The U-Net weights, downloaded once and verified."""
    p = CHECKPOINT["path"]
    if not p.exists():
        print(f"Downloading model weights ({CHECKPOINT['source']}) ...")
        _fetch(CHECKPOINT["url"], p, CHECKPOINT["sha256"])
    elif sha256(p) != CHECKPOINT["sha256"]:
        raise RuntimeError(f"{p} exists but isn't the published checkpoint (SHA-256 mismatch)")
    return p


def ensure_ground_truth() -> Path:
    """USGS hand-traced poultry houses, downloaded once, verified and unzipped."""
    z, d = GROUND_TRUTH["zip"], GROUND_TRUTH["dir"]
    if not z.exists():
        print(f"Downloading hand-traced houses ({GROUND_TRUTH['source']}) ...")
        _fetch(GROUND_TRUTH["url"], z, GROUND_TRUTH["sha256"])
    if not any(d.glob("*.shp")):
        d.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            for member in zf.namelist():
                name = Path(member).name
                if name:
                    (d / name).write_bytes(zf.read(member))
    return next(d.glob("*.shp"))


def environment() -> dict:
    """Software versions, recorded in every run_meta.json."""
    import geopandas
    import numpy
    import rasterio
    import segmentation_models_pytorch
    import shapely
    import torch
    return {
        "where": "colab" if IN_COLAB else platform.node() or "local",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "segmentation_models_pytorch": segmentation_models_pytorch.__version__,
        "rasterio": rasterio.__version__,
        "gdal": rasterio.__gdal_version__,
        "geopandas": geopandas.__version__,
        "shapely": shapely.__version__,
        "numpy": numpy.__version__,
    }
