"""Accuracy scorecard and quantile helpers."""

from __future__ import annotations

import pytest

from app.domain.metrics import coverage, quantile, reliability_table, skill_score, summarise


def test_summarise_known_values() -> None:
    result = summarise([2.0, 4.0, 6.0], [1.0, 2.0, 3.0], capacity_mw=10_000.0)
    assert result.n == 3
    assert result.mae_mw == pytest.approx(2.0)
    assert result.rmse_mw == pytest.approx(2.2)
    assert result.bias_mw == pytest.approx(2.0)
    assert result.mape_pct == pytest.approx(100.0)
    assert result.r2 == pytest.approx(0.0)
    assert result.correlation == pytest.approx(1.0)
    assert result.nrmse_pct_of_capacity == pytest.approx(0.02)


def test_summarise_empty_is_safe() -> None:
    result = summarise([], [])
    assert result.n == 0
    assert result.mae_mw == 0.0
    assert result.mape_pct is None


def test_coverage_and_skill() -> None:
    assert coverage([-2, -1, 0, 1, 2], -1, 1) == pytest.approx(0.6)
    assert coverage([], -1, 1) is None
    assert skill_score(1_000.0, 4_000.0) == pytest.approx(0.75)
    assert skill_score(1_000.0, 0.0) is None


def test_quantile_interpolates() -> None:
    assert quantile([0, 10], 0.5) == pytest.approx(5.0)
    assert quantile([], 0.5) == 0.0


def test_reliability_table_is_self_consistent_on_a_uniform_sample() -> None:
    sample = [float(value) for value in range(-100, 101)]
    rows = reliability_table(sample, [0.5, 0.8, 0.9])
    assert [row["nominal"] for row in rows] == [0.5, 0.8, 0.9]
    for row in rows:
        assert row["observed"] is not None
        # A central interval of the sample it was built from covers close to nominal.
        assert abs(row["observed"] - row["nominal"]) < 0.05
