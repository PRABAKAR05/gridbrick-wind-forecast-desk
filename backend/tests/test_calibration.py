"""Affine recalibration: guard rails and out-of-sample behaviour."""

from __future__ import annotations

import random

import pytest

from app.domain.calibration import IDENTITY, MIN_SAMPLES, fit


def test_short_history_falls_back_to_identity() -> None:
    pairs = [(float(i), float(i) - 500.0) for i in range(MIN_SAMPLES - 1)]
    result = fit(pairs)
    assert result is IDENTITY
    assert result.is_identity


def test_recovers_a_known_affine_relationship() -> None:
    random.seed(7)
    pairs = []
    for _ in range(400):
        x = random.uniform(2_000.0, 14_000.0)
        noise = random.gauss(0.0, 60.0)
        pairs.append((x, 0.8 * x + 1_200.0 + noise))

    result = fit(pairs)
    assert result.method == "affine_ols"
    assert result.samples == 400
    assert result.slope == pytest.approx(0.8, abs=0.01)
    assert result.intercept == pytest.approx(1_200.0, abs=120.0)
    assert result.r2 > 0.99


def test_implausible_slope_becomes_bias_only_correction() -> None:
    pairs = [(float(i), 2.0 * float(i) + 10.0) for i in range(200)]
    result = fit(pairs)
    assert result.method == "bias_only"
    assert result.slope == 1.0
    # Bias-only keeps the raw shape and shifts it by the mean error (+109.5).
    assert result.intercept == pytest.approx(109.5, abs=0.5)


def test_apply_never_returns_negative_generation() -> None:
    pairs = [(float(i), 0.5 * float(i) - 500.0) for i in range(200)]
    result = fit(pairs)
    assert result.apply(0.0) == 0.0
    assert result.apply(10_000.0) >= 0.0
