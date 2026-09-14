"""
Poultry-barn inference using Robinson et al.'s (Microsoft Research) trained
U-Net checkpoint.

Not a copy of microsoft/poultry-cafos -- that repo hard-requires CUDA and
exits otherwise. This is our own thin wrapper around their published model
architecture (cafo/models.get_unet(), MIT-licensed) and checkpoint (Open Use
of Data Agreement v1.0), patched to run on CPU/MPS, since this machine has
neither CUDA nor a copy of their repo installed.

Citation: Robinson, Chugg, Anderson & Ho (2022), "Mapping industrial poultry
operations at scale with deep learning and aerial imagery," IEEE JSTARS.
Training labels: Soroka & Duren (2020), USGS data release,
doi:10.5066/P9MO25Z7.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import rasterio
import segmentation_models_pytorch as smp
import torch
import torch.nn.functional as F
from rasterio.features import shapes as rio_shapes
from shapely.geometry import shape as shapely_shape

ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_PATH = ROOT / "data/models/train-all_unet_0.5_0.01_rotation_best-checkpoint.pt"

CHIP_SIZE = 256
PADDING = 32
HALF_PADDING = PADDING // 2
CHIP_STRIDE = CHIP_SIZE - PADDING


def get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_model(checkpoint_path: Path = CHECKPOINT_PATH, device: torch.device | None = None):
    device = device or get_device()
    model = smp.Unet(
        encoder_name="resnet18",
        encoder_depth=3,
        encoder_weights=None,
        decoder_channels=(128, 64, 64),
        in_channels=4,
        classes=2,
    )
    ckpt = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(ckpt["model_checkpoint"])
    model = model.to(device)
    model.eval()
    return model, device


def chip_transform(chip: np.ndarray) -> torch.Tensor:
    """Matches cafo/utils.py's chip_transformer: HWC uint8 -> CHW float32 [0,1]."""
    chip = chip / 255.0
    chip = np.rollaxis(chip, 2, 0).astype(np.float32)
    return torch.from_numpy(chip)


def run_inference_on_tile(model, device: torch.device, tile_path: Path) -> tuple[np.ndarray, object]:
    """
    Runs chip-based inference over a 4-band GeoTIFF, matching Microsoft's
    inference.py tiling scheme (256px chips, 32px overlap, edge-weighted
    blending). Returns (hard_mask [H,W] uint8, rasterio transform).
    """
    with rasterio.open(tile_path) as src:
        img = np.moveaxis(src.read(), 0, -1)  # HWC, 4 bands
        transform = src.transform
        height, width = img.shape[0], img.shape[1]

    if img.shape[2] != 4:
        raise ValueError(f"{tile_path} has {img.shape[2]} bands, expected 4 (RGB+NIR)")

    output = np.zeros((2, height, width), dtype=np.float32)
    counts = np.zeros((height, width), dtype=np.float32)
    kernel = np.ones((CHIP_SIZE, CHIP_SIZE), dtype=np.float32)
    kernel[HALF_PADDING:-HALF_PADDING, HALF_PADDING:-HALF_PADDING] = 5

    ys = list(range(0, max(height - CHIP_SIZE, 0) + 1, CHIP_STRIDE))
    xs = list(range(0, max(width - CHIP_SIZE, 0) + 1, CHIP_STRIDE))
    if not ys or ys[-1] + CHIP_SIZE < height:
        ys.append(max(height - CHIP_SIZE, 0))
    if not xs or xs[-1] + CHIP_SIZE < width:
        xs.append(max(width - CHIP_SIZE, 0))

    with torch.no_grad():
        for y in ys:
            for x in xs:
                chip = img[y : y + CHIP_SIZE, x : x + CHIP_SIZE]
                ch, cw = chip.shape[0], chip.shape[1]
                if ch < CHIP_SIZE or cw < CHIP_SIZE:
                    padded = np.zeros((CHIP_SIZE, CHIP_SIZE, 4), dtype=chip.dtype)
                    padded[:ch, :cw] = chip
                    chip = padded

                tensor = chip_transform(chip).unsqueeze(0).to(device)
                pred = model(tensor)
                pred = F.softmax(pred, dim=1).cpu().numpy()[0]

                out_h, out_w = min(CHIP_SIZE, height - y), min(CHIP_SIZE, width - x)
                output[:, y : y + out_h, x : x + out_w] += (
                    pred[:, :out_h, :out_w] * kernel[:out_h, :out_w]
                )
                counts[y : y + out_h, x : x + out_w] += kernel[:out_h, :out_w]

    output = output / np.maximum(counts, 1e-6)
    hard_mask = output.argmax(axis=0).astype(np.uint8)
    return hard_mask, transform


def mask_to_polygons(mask: np.ndarray, transform, close_kernel: int = 11) -> list[dict]:
    """Polygonize the binary building mask into geographic-CRS polygons.

    Applies a morphological close first: found during full-scale QA that a
    single real house's mask is sometimes patchy along its length (confidence
    dips at roof ridge lines/equipment), so plain connected-components
    polygonize splits it into several short fragments, each too short to
    pass the length filter individually even though the real house would
    pass as one piece (confirmed visually: site_0082/Sheng Lin Farm, 6 clear
    houses, split into 18 fragments, 0 passing the filter). Tested kernel
    sizes against that farm and against Alan C. Eck Farm (a site with 9
    correctly-separated real houses, used as a regression check): kernel=11
    recovers some of Sheng Lin's fragments with zero change at Eck (still
    9/9); kernel=15+ starts merging Eck's separate houses together (9->3->1->0
    passing as kernel grows) while barely helping Sheng Lin further. 11 is
    the largest kernel that helps without any observed regression.
    """
    if close_kernel > 1:
        mask = cv2.morphologyEx(
            mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((close_kernel, close_kernel), np.uint8)
        )
    polys = []
    for geom, value in rio_shapes(mask, mask=mask.astype(bool), transform=transform):
        if value == 1:
            polys.append(shapely_shape(geom))
    return polys


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
