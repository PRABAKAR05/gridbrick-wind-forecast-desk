"""Newsvendor maths and the procurement plan contract."""

from __future__ import annotations

import pytest

from app.domain.procurement import (
    RiskPolicy,
    build_plan,
    critical_fractile,
    exposure,
    hedge_offset,
)


def test_critical_fractile_uses_the_cost_ratio() -> None:
    assert critical_fractile(1.5, 1.0) == pytest.approx(0.4)
    assert critical_fractile(1.0, 1.0) == pytest.approx(0.5)
    # The policy is clamped away from 0/1 so a quantile always exists.
    assert critical_fractile(1_000.0, 1.0) == pytest.approx(0.01)
    assert RiskPolicy(c_short=1.5, c_long=1.0).alpha == pytest.approx(0.4)
    assert RiskPolicy(confidence=0.72).alpha == pytest.approx(0.72)


def test_hedge_offset_has_the_right_sign() -> None:
    calls: list[tuple[float, float]] = []

    def quantile(lead: float, level: float) -> float:
        calls.append((lead, level))
        return 500.0

    # alpha=0.4 means q at 0.6; the offset must reduce the wind nomination.
    assert hedge_offset(quantile, 8.5, 0.4) == pytest.approx(-500.0)
    assert calls == [(8.5, pytest.approx(0.6))]


def test_exposure_splits_both_sides() -> None:
    result = exposure([-100.0, 100.0], -50.0)
    # gap = [-150, 50] => half the mass is a 50 MW shortfall, half a 75 MW surplus.
    assert result["expected_shortfall_mw"] == pytest.approx(25.0)
    assert result["expected_surplus_mw"] == pytest.approx(75.0)
    assert result["prob_short"] == pytest.approx(0.5)
    assert exposure([], 0.0)["expected_shortfall_mw"] is None


def test_build_plan_uses_the_calibrated_forecast_as_basis() -> None:
    rows = [
        {
            "hour": 0,
            "start_utc": "2026-01-14T00:00:00Z",
            "forecast_mw": 5_000.0,
            "calibrated_mw": 1_000.0,
            "lead_hours": 8.5,
            "band": {"p10": 800.0, "p90": 1_400.0},
        }
    ]
    plan = build_plan(
        rows,
        {0: 2_000.0},
        policy=RiskPolicy(c_short=1.5, c_long=1.0),
        quantile_for=lambda lead, level: 200.0,
        sample_for_lead=lambda lead: [-100.0, 100.0],
    )
    hour = plan["hours"][0]
    assert hour["wind_raw_mw"] == 5_000.0
    assert hour["wind_nominated_mw"] == pytest.approx(800.0)
    assert hour["thermal_baseline_mw"] == pytest.approx(1_000.0)
    assert hour["thermal_procured_mw"] == pytest.approx(1_200.0)
    assert hour["uplift_mw"] == pytest.approx(200.0)
    assert plan["policy"]["critical_fractile"] == pytest.approx(0.4)
    assert plan["totals"]["wind_nominated_mwh"] == pytest.approx(800.0)
    assert plan["totals"]["risk_uplift_mwh"] == pytest.approx(200.0)


def test_build_plan_without_demand_leaves_thermal_empty() -> None:
    rows = [
        {
            "hour": 0,
            "start_utc": "2026-01-14T00:00:00Z",
            "forecast_mw": 1_000.0,
            "calibrated_mw": 1_000.0,
            "lead_hours": 10.0,
            "band": None,
        }
    ]
    plan = build_plan(
        rows,
        {},
        policy=RiskPolicy(),
        quantile_for=lambda lead, level: None,
    )
    assert plan["hours"][0]["wind_nominated_mw"] is None
    assert plan["totals"]["thermal_baseline_mwh"] is None
    assert plan["totals"]["wind_nominated_mwh"] == 0
