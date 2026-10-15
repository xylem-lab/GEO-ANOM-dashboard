"""
Compatibility wrapper. The U-Net inference code now lives in
geo_anom/task1/detect.py; this file keeps older scripts that do
`from unet_inference import ...` working unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo_anom.task1.detect import (  # noqa: E402,F401
    CHECKPOINT_PATH,
    CHIP_SIZE,
    CHIP_STRIDE,
    PADDING,
    chip_transform,
    get_device,
    load_model,
    mask_to_polygons,
    predict_class_scores,
    scores_to_mask,
)
from geo_anom.task1.tiles import read_tile  # noqa: E402


def run_inference_on_tile(model, device, tile_path: Path):
    """(hard_mask [H,W] uint8, rasterio transform) for one 4-band GeoTIFF."""
    img, meta = read_tile(tile_path)
    return scores_to_mask(predict_class_scores(model, device, img)), meta["transform"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--tile", type=Path, required=True)
    args = parser.parse_args()

    model, device = load_model()
    print(f"Loaded model on device={device}")
    mask, transform = run_inference_on_tile(model, device, args.tile)
    polys = mask_to_polygons(mask, transform)
    print(f"{args.tile.name}: {mask.sum()} building px, {len(polys)} raw polygons")
