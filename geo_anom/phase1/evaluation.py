"""
Formal accuracy metrics for Task 1 detection outputs.

Replaces informal count-ratio and ad-hoc-correlation language ("ratio 0.83",
"Spearman rho=0.435" computed once in a scratchpad script and never rerun
identically) with standard, reusable, testable metrics: R^2/RMSE/MAE/
correlation for count-regression comparisons, and precision/recall/F1 for
object-level detection audits. Built to a publication standard -- every
number these functions produce should be traceable and reproducible, not
re-derived by hand each time.
"""

from __future__ import annotations

import math

from scipy import stats as scipy_stats
from sklearn.metrics import r2_score


def regression_metrics(y_true: list[float], y_pred: list[float]) -> dict:
    """
    Standard regression-agreement metrics between two paired count/quantity
    series (e.g. detected houses per farm vs. ground-truth houses per farm,
    or vs. registry headcount per farm).

    Parameters
    ----------
    y_true, y_pred : sequences of equal length, one value per unit
        (e.g. per farm). Order must correspond between the two.

    Returns
    -------
    dict with r2, rmse, mae, pearson_r, pearson_p, spearman_rho, spearman_p, n
    """
    if len(y_true) != len(y_pred):
        raise ValueError(
            f"y_true and y_pred must be the same length, got {len(y_true)} and {len(y_pred)}"
        )
    n = len(y_true)
    if n < 2:
        raise ValueError("regression_metrics needs at least 2 paired observations")

    r2 = r2_score(y_true, y_pred)
    rmse = math.sqrt(sum((a - b) ** 2 for a, b in zip(y_true, y_pred)) / n)
    mae = sum(abs(a - b) for a, b in zip(y_true, y_pred)) / n

    pearson_r, pearson_p = scipy_stats.pearsonr(y_true, y_pred)
    spearman_rho, spearman_p = scipy_stats.spearmanr(y_true, y_pred)

    return {
        "n": n,
        "r2": r2,
        "rmse": rmse,
        "mae": mae,
        "pearson_r": pearson_r,
        "pearson_p": pearson_p,
        "spearman_rho": spearman_rho,
        "spearman_p": spearman_p,
    }


def detection_metrics(tp: int, fp: int, fn: int) -> dict:
    """
    Standard object-detection metrics from a manual TP/FP/FN audit count.

    Parameters
    ----------
    tp : true positives -- detections that correspond to a real object
    fp : false positives -- detections with no real object underneath
    fn : false negatives -- real, visible objects the detector missed

    Returns
    -------
    dict with precision, recall, f1, tp, fp, fn
    """
    if tp < 0 or fp < 0 or fn < 0:
        raise ValueError("tp, fp, fn must all be non-negative")

    precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
    recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    if (precision + recall) > 0 and not (math.isnan(precision) or math.isnan(recall)):
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = float("nan")

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def format_metrics_table(metrics: dict, title: str = "") -> str:
    """Render a metrics dict as a compact markdown-ready line, for dropping
    straight into a results table without re-typing numbers by hand."""
    lines = []
    if title:
        lines.append(f"**{title}**")
    if "r2" in metrics:
        lines.append(
            f"n={metrics['n']}, R²={metrics['r2']:.3f}, RMSE={metrics['rmse']:.2f}, "
            f"MAE={metrics['mae']:.2f}, Pearson r={metrics['pearson_r']:.3f} "
            f"(p={metrics['pearson_p']:.2g}), Spearman ρ={metrics['spearman_rho']:.3f} "
            f"(p={metrics['spearman_p']:.2g})"
        )
    elif "precision" in metrics:
        lines.append(
            f"TP={metrics['tp']}, FP={metrics['fp']}, FN={metrics['fn']}, "
            f"Precision={metrics['precision']:.3f}, Recall={metrics['recall']:.3f}, "
            f"F1={metrics['f1']:.3f}"
        )
    return "\n".join(lines)
