"""Turning a probabilistic wind forecast into a quantity to procure.

The question the desk actually asks is not "what will wind be?" but "how much
thermal do I buy, given that I will be wrong?". That is a newsvendor problem.

Let ``F`` be the wind volume nominated. If wind outturn ``W`` comes in below
``F`` we are short and buy the gap at a penalty; if it comes in above ``F`` we
are long and sell the surplus back, usually at a worse price. Treating the two
underlying settlement prices as ``c_short`` and ``c_long`` per MWh, expected
imbalance cost is

    C(F) = c_short * E[(F - W)+] + c_long * E[(W - F)+]

and the first-order condition gives the classic critical fractile

    dC/dF = 0  =>  P(W < F*) = c_long / (c_short + c_long)

So the nomination is a *quantile of the predictive distribution*, not its mean.
When shortfall is expensive, the fractile collapses towards zero and we
deliberately under-nominate wind - buying more thermal as insurance. This is
the whole point of quantifying the error: it changes the number we submit.

Because the predictive distribution is expressed as the point forecast plus an
empirical residual distribution, the same machinery corrects for bias for free.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """Relative settlement economics plus a manual confidence override."""

    c_short: float = 1.5
    c_long: float = 1.0
    confidence: float | None = None  # None => derive from cost ratio

    @property
    def alpha(self) -> float:
        if self.confidence is not None:
            return float(min(max(self.confidence, 0.01), 0.99))
        total = self.c_short + self.c_long
        if total <= 0:
            return 0.5
        return float(min(max(self.c_long / total, 0.01), 0.99))

    @property
    def short_long_ratio(self) -> float:
        return round(self.c_short / self.c_long, 3) if self.c_long else 0.0


def critical_fractile(c_short: float, c_long: float) -> float:
    """P(W < F*): the optimal service level for the wind nomination."""
    total = c_short + c_long
    if total <= 0:
        return 0.5
    return float(min(max(c_long / total, 0.01), 0.99))


def hedge_offset(
    quantile_fn: Callable[[float, float], float | None],
    lead: float,
    alpha: float,
) -> float | None:
    """Offset to add to the point forecast to hit service level ``alpha``.

    Residuals are ``eps = forecast - actual``. With nomination ``F = f + o``,
    shortfall occurs when ``eps > -o``. Setting ``P(short) = 1 - alpha`` gives

        o = -q_{1-alpha}(eps)

    Note the sign and the ``1 - alpha``: a desk that is worried about being
    short (alpha < 0.5) needs a *negative* offset, i.e. nominate less wind and
    buy more thermal. Getting this backwards flatters the hedge and leaves the
    desk short - which is exactly the failure this product exists to avoid.
    """
    quantile = quantile_fn(lead, 1.0 - alpha)
    return None if quantile is None else -quantile


def exposure(sample: Sequence[float] | np.ndarray, offset: float) -> dict[str, float | None]:
    """Expected shortfall/surplus for a nomination offset ``o``.

    ``sample`` is the empirical distribution of ``forecast - actual``. The gap
    between the nominated volume and outturn is ``o + eps``: positive means we
    under-nominated wind and are short energy.
    """
    array = np.asarray(sample, dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return {
            "expected_shortfall_mw": None,
            "expected_surplus_mw": None,
            "prob_short": None,
            "offset_mw": None,
        }
    gap = offset + array
    shortfall = np.clip(gap, 0.0, None)
    surplus = np.clip(-gap, 0.0, None)
    return {
        "expected_shortfall_mw": round(float(np.mean(shortfall)), 2),
        "expected_surplus_mw": round(float(np.mean(surplus)), 2),
        "prob_short": round(float(np.mean(gap > 0)), 4),
        "offset_mw": round(float(offset), 2),
    }


@dataclass(frozen=True, slots=True)
class HourDecision:
    hour: int
    start_utc: str
    demand_mw: float | None
    wind_forecast_mw: float | None
    wind_raw_mw: float | None
    wind_nominated_mw: float | None
    wind_p10_mw: float | None
    wind_p90_mw: float | None
    thermal_baseline_mw: float | None
    thermal_procured_mw: float | None
    uplift_mw: float | None
    exposure: dict[str, float | None] | None

    def as_dict(self) -> dict[str, object]:
        return {
            "hour": self.hour,
            "start_utc": self.start_utc,
            "demand_mw": self.demand_mw,
            "wind_forecast_mw": self.wind_forecast_mw,
            "wind_raw_mw": self.wind_raw_mw,
            "wind_nominated_mw": self.wind_nominated_mw,
            "wind_p10_mw": self.wind_p10_mw,
            "wind_p90_mw": self.wind_p90_mw,
            "thermal_baseline_mw": self.thermal_baseline_mw,
            "thermal_procured_mw": self.thermal_procured_mw,
            "uplift_mw": self.uplift_mw,
            "exposure": self.exposure,
        }


def build_plan(
    rows: Sequence[dict[str, object]],
    demand_by_hour: dict[int, float | None],
    *,
    policy: RiskPolicy,
    quantile_for: Callable[[float, float], float | None],
    sample_for_lead: Callable[[float], Sequence[float] | None] | None = None,
) -> dict[str, object]:
    """Produce a risk-adjusted procurement plan from forecast rows.

    ``rows`` are the serialised hourly rows from the analytics layer; they carry
    the point forecast, the empirical band and the lead time needed to look up
    the right residual population.
    """
    decisions: list[HourDecision] = []
    baseline_energy = 0.0
    procured_energy = 0.0
    expected_shortfall_energy = 0.0
    covered_hours = 0

    for row in rows:
        hour = int(row["hour"])  # type: ignore[arg-type]
        raw = row.get("forecast_mw")
        # Band offsets live in the *calibrated* residual space, so the
        # nomination must be built on the calibrated forecast.
        basis = row.get("calibrated_mw")
        if basis is None:
            basis = raw
        lead = row.get("lead_hours")
        band = row.get("band") or {}
        demand = demand_by_hour.get(hour)

        alpha = policy.alpha
        offset = hedge_offset(quantile_for, float(lead), alpha) if lead is not None else None
        nominated = None if (basis is None or offset is None) else float(basis) + offset
        p10 = band.get("p10") if isinstance(band, dict) else None
        p90 = band.get("p90") if isinstance(band, dict) else None

        thermal_baseline = None
        thermal_procured = None
        uplift = None
        if demand is not None and basis is not None:
            thermal_baseline = demand - float(basis)
            if nominated is not None:
                thermal_procured = demand - nominated
                uplift = thermal_procured - thermal_baseline

        hour_exposure = None
        if nominated is not None and lead is not None and sample_for_lead is not None:
            sample = sample_for_lead(float(lead))
            if sample is not None and len(sample):
                hour_exposure = exposure(sample, offset or 0.0)
                if hour_exposure["expected_shortfall_mw"] is not None:
                    expected_shortfall_energy += float(hour_exposure["expected_shortfall_mw"])
                    covered_hours += 1

        if thermal_baseline is not None:
            baseline_energy += thermal_baseline
        if thermal_procured is not None:
            procured_energy += thermal_procured

        decisions.append(
            HourDecision(
                hour=hour,
                start_utc=str(row["start_utc"]),
                demand_mw=None if demand is None else round(demand, 1),
                wind_forecast_mw=None if basis is None else round(float(basis), 1),
                wind_raw_mw=None if raw is None else round(float(raw), 1),
                wind_nominated_mw=None if nominated is None else round(nominated, 1),
                wind_p10_mw=None if p10 is None else round(float(p10), 1),
                wind_p90_mw=None if p90 is None else round(float(p90), 1),
                thermal_baseline_mw=None if thermal_baseline is None else round(thermal_baseline, 1),
                thermal_procured_mw=None if thermal_procured is None else round(thermal_procured, 1),
                uplift_mw=None if uplift is None else round(uplift, 1),
                exposure=hour_exposure,
            )
        )

    has_demand = any(decision.demand_mw is not None for decision in decisions)
    uplift_total = procured_energy - baseline_energy if has_demand else None

    return {
        "policy": {
            "critical_fractile": round(policy.alpha, 4),
            "confidence_pct": round(policy.alpha * 100, 1),
            "c_short": policy.c_short,
            "c_long": policy.c_long,
            "short_long_ratio": policy.short_long_ratio,
            "rule": (
                "Nominate wind at the alpha-quantile of its predictive distribution, "
                "where alpha = c_long / (c_short + c_long)."
            ),
        },
        "hours": [decision.as_dict() for decision in decisions],
        "totals": {
            "demand_mwh": round(sum(d.demand_mw or 0.0 for d in decisions), 0) if has_demand else None,
            "wind_forecast_mwh": round(sum(d.wind_forecast_mw or 0.0 for d in decisions), 0),
            "wind_nominated_mwh": round(sum(d.wind_nominated_mw or 0.0 for d in decisions), 0),
            "thermal_baseline_mwh": round(baseline_energy, 0) if has_demand else None,
            "thermal_procured_mwh": round(procured_energy, 0) if has_demand else None,
            "risk_uplift_mwh": round(uplift_total, 0) if uplift_total is not None else None,
            "expected_shortfall_mwh": round(expected_shortfall_energy, 0) if covered_hours else None,
            "hours_covered": covered_hours,
        },
    }
