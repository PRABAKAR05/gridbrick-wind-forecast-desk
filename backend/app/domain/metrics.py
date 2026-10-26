"""Error statistics for renewable generation forecasts.

Deliberately dependency-light and pure: every function takes arrays and
returns plain Python types, which makes the maths trivial to unit test and
reuse from both the API layer and the offline evaluation CLI.

A note on units
---------------
Generation is MW. Because our comparison granularity is one hour and each
observation is the mean MW over that hour, summing hourly MW values yields
MWh directly. That identity is used throughout the procurement maths.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

import numpy as np

ArrayLike = Sequence[float] | np.ndarray


def _as_array(values: ArrayLike) -> np.ndarray:
    array = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype=float)
    return array[np.isfinite(array)] if array.size else array


def _paired(forecast: ArrayLike, actual: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    f = np.asarray(forecast, dtype=float)
    a = np.asarray(actual, dtype=float)
    if f.shape != a.shape:
        raise ValueError(f"shape mismatch: forecast {f.shape} vs actual {a.shape}")
    mask = np.isfinite(f) & np.isfinite(a)
    return f[mask], a[mask]


@dataclass(frozen=True, slots=True)
class ErrorSummary:
    """Standard accuracy scorecard for a set of paired observations."""

    n: int
    mae_mw: float
    rmse_mw: float
    bias_mw: float
    mape_pct: float | None
    nrmse_pct_of_capacity: float | None
    nrmse_pct_of_mean_actual: float | None
    r2: float
    correlation: float
    mean_forecast_mw: float
    mean_actual_mw: float
    p90_abs_error_mw: float
    max_abs_error_mw: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def summarise(
    forecast: ArrayLike,
    actual: ArrayLike,
    *,
    capacity_mw: float | None = None,
) -> ErrorSummary:
    """Compute the headline scorecard.

    ``mape_pct`` excludes observations where the actual is below 1% of the
    mean actual, because percentage error on near-zero wind is numerically
    meaningless and would dominate the average.
    """
    f, a = _paired(forecast, actual)
    n = int(f.size)
    if n == 0:
        return ErrorSummary(0, 0.0, 0.0, 0.0, None, None, None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    errors = f - a
    abs_errors = np.abs(errors)
    mean_actual = float(np.mean(a))
    rmse = float(np.sqrt(np.mean(errors**2)))

    floor = max(0.01 * mean_actual, 1.0)
    pct_mask = np.abs(a) > floor
    mape = float(np.mean(abs_errors[pct_mask] / np.abs(a[pct_mask])) * 100.0) if pct_mask.any() else None

    var_a = float(np.var(a))
    r2 = float(1.0 - np.var(errors) / var_a) if var_a > 1e-9 else 0.0
    corr = float(np.corrcoef(f, a)[0, 1]) if f.size > 1 and np.std(f) > 1e-9 and np.std(a) > 1e-9 else 0.0

    return ErrorSummary(
        n=n,
        mae_mw=round(float(np.mean(abs_errors)), 1),
        rmse_mw=round(rmse, 1),
        bias_mw=round(float(np.mean(errors)), 1),
        mape_pct=None if mape is None else round(mape, 2),
        nrmse_pct_of_capacity=None if not capacity_mw else round(rmse / capacity_mw * 100, 2),
        nrmse_pct_of_mean_actual=round(rmse / mean_actual * 100, 2) if mean_actual > 1e-9 else None,
        r2=round(r2, 4),
        correlation=round(corr, 4),
        mean_forecast_mw=round(float(np.mean(f)), 1),
        mean_actual_mw=round(mean_actual, 1),
        p90_abs_error_mw=round(float(np.quantile(abs_errors, 0.9)), 1) if n else 0.0,
        max_abs_error_mw=round(float(np.max(abs_errors)), 1) if n else 0.0,
    )


def quantile(values: ArrayLike, level: float) -> float:
    """Empirical quantile; ``level`` in [0, 1]."""
    array = _as_array(values)
    if array.size == 0:
        return 0.0
    return float(np.quantile(array, level))


def quantiles(values: ArrayLike, levels: Iterable[float]) -> dict[str, float]:
    """Empirical quantiles keyed by ``p10``/``p90``-style labels."""
    array = _as_array(values)
    return {
        f"p{int(round(level * 100))}": round(quantile(array, level), 1)
        for level in levels
    }


def predictive_quantiles(
    residual_history: ArrayLike,
    levels: Iterable[float],
    *,
    min_samples: int = 30,
) -> dict[str, float] | None:
    """Quantiles of the forecast-error distribution, used as a band offset.

    Returns ``None`` when there is not enough history to say anything
    credible, so callers can render an explicit "no band" state instead of
    inventing a number.
    """
    array = _as_array(residual_history)
    if array.size < min_samples:
        return None
    return quantiles(array, levels)


def coverage(errors: ArrayLike, lower: float, upper: float) -> float | None:
    """Fraction of residuals that fall inside ``[lower, upper]``."""
    array = _as_array(errors)
    if array.size == 0:
        return None
    return round(float(np.mean((array >= lower) & (array <= upper))), 4)


def pinball_loss(
    residual_history: ArrayLike,
    predicted_quantile: float,
    level: float,
) -> float:
    """Pinball (quantile) loss of a predictive quantile forecast.

    Residual = forecast - actual, so the predictive distribution of the
    *error* is what we are issuing quantiles of. This is the proper scoring
    rule for quantile forecasts: it rewards sharp and calibrated bands, and a
    band cannot be gamed by simply widening it.
    """
    array = _as_array(residual_history)
    if array.size == 0:
        return 0.0
    diff = array - predicted_quantile
    loss = np.where(diff >= 0, level * diff, (level - 1.0) * diff)
    return round(float(np.mean(loss)), 2)


def skill_score(model_error: float, baseline_error: float) -> float | None:
    """1 - model/baseline. Positive means the model beats the baseline."""
    if baseline_error <= 1e-9:
        return None
    return round(1.0 - model_error / baseline_error, 4)


def histogram(values: ArrayLike, *, bins: int = 28) -> dict[str, list[float]]:
    """Density-friendly histogram payload for the UI."""
    array = _as_array(values)
    if array.size == 0:
        return {"bin_start": [], "bin_end": [], "count": []}
    counts, edges = np.histogram(array, bins=bins)
    return {
        "bin_start": [round(float(edge), 1) for edge in edges[:-1]],
        "bin_end": [round(float(edge), 1) for edge in edges[1:]],
        "count": [int(c) for c in counts],
    }


def reliability_table(
    residual_history: Sequence[float],
    levels: Sequence[float],
) -> list[dict[str, float | None]]:
    """Empirical coverage achieved at each nominal central interval level.

    For nominal level ``0.8`` we build the central 80% interval of the
    residual history and check what fraction of the *same* residuals it
    contains. Evaluated walk-forward this answers the client's real question:
    "when you tell me an 80% band, is it actually 80%?"
    """
    array = _as_array(residual_history)
    rows: list[dict[str, float | None]] = []
    for level in levels:
        if array.size == 0:
            rows.append({"nominal": level, "observed": None, "lower": None, "upper": None, "samples": 0})
            continue
        alpha = (1.0 - level) / 2.0
        lower = float(np.quantile(array, alpha))
        upper = float(np.quantile(array, 1.0 - alpha))
        observed = float(np.mean((array >= lower) & (array <= upper)))
        rows.append(
            {
                "nominal": level,
                "observed": round(observed, 4),
                "lower": round(lower, 1),
                "upper": round(upper, 1),
                "samples": int(array.size),
            }
        )
    return rows
