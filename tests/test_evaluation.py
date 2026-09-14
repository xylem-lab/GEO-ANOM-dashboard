"""Tests for geo_anom.phase1.evaluation -- verified against synthetic,
hand-computed values before trusting these functions on real numbers
headed into a paper."""

from __future__ import annotations

import math

import pytest

from geo_anom.phase1.evaluation import (
    regression_metrics,
    detection_metrics,
    format_metrics_table,
)


class TestRegressionMetrics:
    def test_identical_series_gives_perfect_agreement(self):
        y = [1, 2, 3, 4, 5]
        m = regression_metrics(y, y)
        assert m["r2"] == pytest.approx(1.0)
        assert m["rmse"] == pytest.approx(0.0)
        assert m["mae"] == pytest.approx(0.0)
        assert m["pearson_r"] == pytest.approx(1.0)
        assert m["spearman_rho"] == pytest.approx(1.0)
        assert m["n"] == 5

    def test_hand_computed_rmse_mae(self):
        # errors: 1, -1, 1 -> squared errors 1,1,1 -> mean 1 -> rmse 1
        y_true = [10, 10, 10]
        y_pred = [11, 9, 11]
        m = regression_metrics(y_true, y_pred)
        assert m["rmse"] == pytest.approx(1.0)
        assert m["mae"] == pytest.approx(1.0)

    def test_constant_offset_perfect_correlation_imperfect_r2(self):
        # y_pred = y_true + 2 everywhere: perfect correlation, but R^2 can
        # still be less than 1 since R^2 penalizes systematic bias, not just
        # scatter -- a real, useful distinction to have available.
        y_true = [1, 2, 3, 4, 5]
        y_pred = [3, 4, 5, 6, 7]
        m = regression_metrics(y_true, y_pred)
        assert m["pearson_r"] == pytest.approx(1.0)
        assert m["r2"] < 1.0

    def test_anticorrelated_series(self):
        y_true = [1, 2, 3, 4, 5]
        y_pred = [5, 4, 3, 2, 1]
        m = regression_metrics(y_true, y_pred)
        assert m["pearson_r"] == pytest.approx(-1.0)
        assert m["spearman_rho"] == pytest.approx(-1.0)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            regression_metrics([1, 2, 3], [1, 2])

    def test_too_few_points_raises(self):
        with pytest.raises(ValueError):
            regression_metrics([1], [1])


class TestDetectionMetrics:
    def test_perfect_detection(self):
        m = detection_metrics(tp=10, fp=0, fn=0)
        assert m["precision"] == pytest.approx(1.0)
        assert m["recall"] == pytest.approx(1.0)
        assert m["f1"] == pytest.approx(1.0)

    def test_hand_computed_precision_recall(self):
        # precision = 8/(8+2) = 0.8, recall = 8/(8+4) = 0.667
        m = detection_metrics(tp=8, fp=2, fn=4)
        assert m["precision"] == pytest.approx(0.8)
        assert m["recall"] == pytest.approx(8 / 12)
        expected_f1 = 2 * 0.8 * (8 / 12) / (0.8 + 8 / 12)
        assert m["f1"] == pytest.approx(expected_f1)

    def test_no_predictions_precision_is_nan(self):
        m = detection_metrics(tp=0, fp=0, fn=5)
        assert math.isnan(m["precision"])
        assert m["recall"] == pytest.approx(0.0)

    def test_no_real_objects_recall_is_nan(self):
        m = detection_metrics(tp=0, fp=3, fn=0)
        assert math.isnan(m["recall"])
        assert m["precision"] == pytest.approx(0.0)

    def test_negative_counts_raise(self):
        with pytest.raises(ValueError):
            detection_metrics(tp=-1, fp=0, fn=0)


class TestFormatMetricsTable:
    def test_formats_regression_metrics(self):
        m = regression_metrics([1, 2, 3], [1, 2, 3])
        out = format_metrics_table(m, title="Test")
        assert "R²=1.000" in out
        assert "Test" in out

    def test_formats_detection_metrics(self):
        m = detection_metrics(tp=5, fp=1, fn=1)
        out = format_metrics_table(m)
        assert "Precision=" in out
        assert "TP=5" in out
