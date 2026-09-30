"""
Vision-only headcount estimation for poultry-type detections.

Loads the model fit by scripts/train_capacity_model.py (log(area) ->
log(headcount), cross-validated R^2 ~= 0.23, n=357 poultry farms) and applies
it to a detected building cluster's total floor area, with no registry
lookup involved. See docs/species_capacity_model_metrics.md for why this is
poultry-only and what a non-poultry estimate would require instead.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = ROOT / "data/processed/models/poultry_capacity_model.json"

# Species this model was actually fit on -- see the shape-filter argument in
# species_capacity_model_metrics.md for why it can't be extended to
# dairy/beef/swine without retraining the upstream segmentation step.
POULTRY_TYPES = {"chickens_not_laying_hens", "laying_hens_dry_manure", "turkeys", "ducks_liquid_manure"}


@lru_cache(maxsize=1)
def _load_model() -> dict:
    return json.loads(MODEL_PATH.read_text())


def predict_poultry_headcount(total_area_m2: float, n_buildings: int) -> tuple[float, float]:
    """
    Predict headcount from detected floor area alone (no registry lookup).

    Returns (point_estimate, approx_multiplicative_uncertainty) -- e.g. a
    returned (48000, 1.7) means "about 48,000, but individual farms in the
    training data were typically off by a factor of ~1.7x in either
    direction," not a precise count. Callers should surface both numbers,
    not just the point estimate.
    """
    model = _load_model()
    if total_area_m2 <= 0:
        return 0.0, float("nan")
    log_area = math.log(total_area_m2)
    if model["features"] == ["log_total_area_m2", "log_n_buildings"]:
        x = [log_area, math.log(max(n_buildings, 1))]
    else:
        x = [log_area]
    log_headcount = model["intercept"] + sum(c * xi for c, xi in zip(model["coef"], x))
    point = math.exp(log_headcount)
    uncertainty_factor = math.exp(model["residual_log_std"])
    return point, uncertainty_factor


def is_poultry_type(animal_type: str | None) -> bool:
    return (animal_type or "").strip().lower() in POULTRY_TYPES


def model_metadata() -> dict:
    """Surface the model's own honesty metadata (n, R^2) for logging/QA."""
    model = _load_model()
    return {
        "cv_r2_mean": model["cv_r2_mean"],
        "cv_r2_std": model["cv_r2_std"],
        "n_training_farms": model["n_training_farms"],
    }
