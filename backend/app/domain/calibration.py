"""Forecast recalibration: raw weather-model output -> decision-grade input.

Why this exists
---------------
The day-ahead question is "how much wind will actually reach the transmission
system?", but Elexon's WINDFOR feed is a forecast of *total* wind generation.
The outturn we can verify against (FUELHH) measures transmission-metered wind
only. Comparing the two directly produces a large, systematic level bias -
roughly +1.8 GW across the pilot month - that has nothing to do with weather
skill and everything to do with scope.

A trading desk that ignores this believes there is 1.8 GW more wind than there
is, buys correspondingly less thermal cover, and is short every single day. So
the product does not compare like with like by hand-wave: it fits an affine
recalibration

    outturn ~= slope * forecast + intercept

on a trailing window of **decision-time** vintages only, and applies it
out-of-sample to the day being decided. Fitted coefficients are bounded, so a
bad window can degrade the forecast towards naive but can never invert it.

Every fit this module produces is walk-forward: the window ends the day before
the delivery day and only contains actuals published before the cutoff. The
accuracy screen reports the out-of-sample result, not the fit quality.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

MIN_SAMPLES = 120
SLOPE_BOUNDS = (0.4, 1.3)


@dataclass(frozen=True, slots=True)
class AffineCalibration:
    slope: float
    intercept: float
    samples: int
    r2: float
    method: str

    def apply(self, value: float) -> float:
        return max(0.0, self.slope * value + self.intercept)

    def apply_array(self, values: np.ndarray) -> np.ndarray:
        return np.clip(self.slope * values + self.intercept, 0.0, None)

    @property
    def is_identity(self) -> bool:
        return self.method == "identity"

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "slope": round(self.slope, 4),
            "intercept_mw": round(self.intercept, 1),
            "samples": self.samples,
            "r2": round(self.r2, 4),
            "method": self.method,
        }


IDENTITY = AffineCalibration(slope=1.0, intercept=0.0, samples=0, r2=0.0, method="identity")


def fit(pairs: Sequence[tuple[float, float]]) -> AffineCalibration:
    """Least-squares affine recalibration with guard rails.

    Falls back to a pure bias correction if the fitted slope leaves the
    plausible band, and to identity if there is simply not enough history.
    """
    if len(pairs) < MIN_SAMPLES:
        return IDENTITY

    x = np.array([p[0] for p in pairs], dtype=float)
    y = np.array([p[1] for p in pairs], dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if x.size < MIN_SAMPLES or np.var(x) < 1e-6:
        return IDENTITY

    slope, intercept = np.polyfit(x, y, 1)
    if not np.isfinite(slope) or not SLOPE_BOUNDS[0] <= slope <= SLOPE_BOUNDS[1]:
        # Bias-only fallback: subtract the mean error, keep the shape.
        offset = float(np.mean(y - x))
        return AffineCalibration(
            slope=1.0,
            intercept=offset,
            samples=int(x.size),
            r2=0.0,
            method="bias_only",
        )

    residual = slope * x + intercept - y
    var = float(np.var(y))
    r2 = 1.0 - float(np.var(residual)) / var if var > 1e-9 else 0.0
    return AffineCalibration(
        slope=float(slope),
        intercept=float(intercept),
        samples=int(x.size),
        r2=float(r2),
        method="affine_ols",
    )
