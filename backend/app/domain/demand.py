"""Illustrative demand profiles.

**Scope note.** The pilot's evidence base is wind only - that was the brief.
The desk already owns a demand forecast, so demand enters this product as an
*input*, not as something we model. To make the procurement screen usable
without plugging into the client's systems, we ship two clearly-labelled
synthetic shapes. They are for demonstration of the mechanics only and are
never presented as a forecast.
"""

from __future__ import annotations

import math

SYNTHETIC_LABEL = "synthetic-illustrative"


def _bell(hour: float, centre: float, width: float) -> float:
    return math.exp(-0.5 * ((hour - centre) / width) ** 2)


def gb_winter_shape(hour: int) -> float:
    """Normalised 0-1 shape of a GB winter weekday demand curve.

    Two peaks (morning ~08:00, evening ~18:00) with an overnight trough - the
    familiar 'bathtub' that drives the residual load the desk has to cover.
    """
    base = 0.55
    morning = 0.18 * _bell(hour, 8.0, 2.1)
    evening = 0.30 * _bell(hour, 18.0, 2.6)
    midday = 0.07 * _bell(hour, 13.0, 3.0)
    raw = base + morning + evening + midday
    # Shape is normalised so that hour 18 is 1.0 and the trough is ~0.55.
    return raw / (base + evening)


def build_profile(
    kind: str,
    *,
    peak_mw: float = 46_000.0,
    trough_mw: float = 30_000.0,
    flat_mw: float = 38_000.0,
    hours: range | None = None,
) -> dict[int, float]:
    """Return demand MW by local hour for a named profile."""
    hours = hours or range(24)
    if kind == "flat":
        return {hour: round(flat_mw, 1) for hour in hours}
    if kind == "synthetic_gb_winter":
        result = {}
        for hour in hours:
            shape = gb_winter_shape(hour)
            result[hour] = round(trough_mw + (peak_mw - trough_mw) * shape, 1)
        return result
    raise ValueError(f"unknown demand profile: {kind}")


def profile_meta(kind: str) -> dict[str, object]:
    descriptions = {
        "synthetic_gb_winter": {
            "id": "synthetic_gb_winter",
            "label": "Synthetic GB winter weekday",
            "synthetic": True,
            "description": (
                "Illustrative two-peak national demand shape (peak 46 GW, trough 30 GW). "
                "Not a forecast - replace with the client's own demand signal."
            ),
        },
        "flat": {
            "id": "flat",
            "label": "Flat block",
            "synthetic": True,
            "description": "Constant demand across all 24 hours, for sensitivity testing.",
        },
    }
    return descriptions.get(kind, {"id": kind, "label": kind, "synthetic": True, "description": ""})


def available_profiles() -> list[dict[str, object]]:
    return [profile_meta("synthetic_gb_winter"), profile_meta("flat")]
