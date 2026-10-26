"""The Decision Desk view: one delivery day, as seen at one gate closure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import numpy as np

from ..domain import metrics
from ..domain.calibration import AffineCalibration
from ..domain.procurement import RiskPolicy, hedge_offset
from ..domain.settlement import delivery_hours, iso_utc
from .analytics import (
    GB_WIND_CAPACITY_MW,
    BandModel,
    HourObservation,
    PilotDataset,
    band_summary,
    hour_series,
    lead_bucket,
)


@dataclass(slots=True)
class DecisionContext:
    delivery_date: date
    cutoff: datetime
    as_of: datetime
    vintage: datetime | None
    observations: list[HourObservation]
    rows: list[dict[str, object]]
    band: BandModel
    calibration: AffineCalibration
    dataset: PilotDataset

    @property
    def realised(self) -> bool:
        return any(row.actual_mw is not None for row in self.observations)


def build_decision(
    dataset: PilotDataset,
    delivery_date: date,
    cutoff: datetime,
    as_of: datetime,
) -> DecisionContext:
    observations = dataset.observation(delivery_date, cutoff, as_of)
    vintage = dataset.vintage_for(delivery_date, cutoff)
    band = dataset.band_model(delivery_date, cutoff)
    calibration = dataset.calibration_for(delivery_date, cutoff)
    rows = hour_series(observations, band)
    return DecisionContext(
        delivery_date=delivery_date,
        cutoff=cutoff,
        as_of=as_of,
        vintage=vintage,
        observations=observations,
        rows=rows,
        band=band,
        calibration=calibration,
        dataset=dataset,
    )


def sample_for(band: BandModel, lead: float) -> list[float] | None:
    """Residual population the band model would use at this lead time."""
    sample = band.by_bucket.get(lead_bucket(lead))
    if sample and len(sample) >= band.min_samples:
        return sample
    if len(band.pooled) >= band.min_samples:
        return band.pooled
    return None


def serialise(context: DecisionContext, policy: RiskPolicy | None = None) -> dict[str, object]:
    policy = policy or RiskPolicy()
    rows = context.rows
    observations = context.observations

    raw = [float(r["forecast_mw"]) for r in rows if r["forecast_mw"] is not None]
    calibrated = [float(r["calibrated_mw"]) for r in rows if r["calibrated_mw"] is not None]
    actuals = [float(r["actual_mw"]) for r in rows if r["actual_mw"] is not None]
    residuals = [float(r["residual_mw"]) for r in rows if r["residual_mw"] is not None]
    raw_residuals = [float(r["raw_residual_mw"]) for r in rows if r["raw_residual_mw"] is not None]

    band_info = band_summary(context.band, observations)
    p10_values = [r["band"]["p10"] for r in rows if isinstance(r["band"], dict)]  # type: ignore[index]
    p90_values = [r["band"]["p90"] for r in rows if isinstance(r["band"], dict)]  # type: ignore[index]

    basis = calibrated or raw
    downside_p90 = (
        round(sum(max(0.0, b - float(low)) for b, low in zip(basis, p10_values, strict=False)), 0)
        if p10_values and basis
        else None
    )
    upside_p90 = (
        round(sum(max(0.0, float(u) - b) for b, u in zip(basis, p90_values, strict=False)), 0)
        if p90_values and basis
        else None
    )

    alpha = policy.alpha
    expected_shortfall = 0.0
    expected_surplus = 0.0
    prob_short: list[float] = []
    nominated_total = 0.0
    covered = 0
    for observation in observations:
        if observation.lead_hours is None or not context.band.ready:
            continue
        sample = sample_for(context.band, observation.lead_hours)
        offset = hedge_offset(context.band.quantile, observation.lead_hours, alpha)
        if sample is None or offset is None:
            continue
        basis = observation.calibrated_mw
        if basis is not None:
            nominated_total += basis + offset
        gap = offset + np.asarray(sample, dtype=float)
        expected_shortfall += float(np.mean(np.clip(gap, 0, None)))
        expected_surplus += float(np.mean(np.clip(-gap, 0, None)))
        prob_short.append(float(np.mean(gap > 0)))
        covered += 1

    realised = context.realised and len(actuals) == len(rows) and bool(rows)

    summary: dict[str, object] = {
        "realised": context.realised,
        "hours_with_forecast": len(raw),
        "hours_with_actual": len(actuals),
        "calibration": context.calibration.as_dict(),
        # raw feed
        "wind_forecast_mwh": round(sum(raw), 0) if raw else None,
        "wind_forecast_mean_mw": round(float(np.mean(raw)), 1) if raw else None,
        "wind_forecast_min_mw": round(min(raw), 1) if raw else None,
        "wind_forecast_max_mw": round(max(raw), 1) if raw else None,
        # decision-grade
        "wind_calibrated_mwh": round(sum(calibrated), 0) if calibrated else None,
        "wind_calibrated_mean_mw": round(float(np.mean(calibrated)), 1) if calibrated else None,
        # uncertainty
        "wind_p10_mwh": round(float(sum(p10_values)), 0) if p10_values else None,
        "wind_p90_mwh": round(float(sum(p90_values)), 0) if p90_values else None,
        "downside_p90_mwh": downside_p90,
        "upside_p90_mwh": upside_p90,
        "band": band_info,
        "policy": {
            "critical_fractile": round(alpha, 4),
            "c_short": policy.c_short,
            "c_long": policy.c_long,
            "confidence_pct": round(alpha * 100, 1),
        },
        "expected_shortfall_mwh": round(expected_shortfall, 0) if covered else None,
        "expected_surplus_mwh": round(expected_surplus, 0) if covered else None,
        "wind_nominated_mwh": round(nominated_total, 0) if covered else None,
        "nomination_uplift_mwh": round(nominated_total - sum(calibrated), 0)
        if covered and calibrated
        else None,
        "prob_short": round(float(np.mean(prob_short)), 3) if prob_short else None,
        "hours_in_risk_calc": covered,
    }

    if realised:
        summary.update(
            {
                "wind_actual_mwh": round(sum(actuals), 0),
                "wind_actual_mean_mw": round(float(np.mean(actuals)), 1),
                "mae_mw": round(float(np.mean([abs(x) for x in residuals])), 1),
                "bias_mw": round(float(np.mean(residuals)), 1),
                "rmse_mw": metrics.summarise(
                    [r["calibrated_mw"] for r in rows], [r["actual_mw"] for r in rows]
                ).rmse_mw,
                "energy_error_mwh": round(float(sum(residuals)), 0),
                "raw_mae_mw": round(float(np.mean([abs(x) for x in raw_residuals])), 1)
                if raw_residuals
                else None,
                "raw_bias_mw": round(float(np.mean(raw_residuals)), 1) if raw_residuals else None,
                "within_p10_p90": sum(
                    1
                    for row in rows
                    if isinstance(row["band"], dict)
                    and row["actual_mw"] is not None
                    and row["band"]["p10"] <= row["actual_mw"] <= row["band"]["p90"]
                ),
                "utilisation_pct": round(float(np.mean(actuals)) / GB_WIND_CAPACITY_MW * 100, 1),
            }
        )

    vintage_age = None
    if context.vintage is not None:
        vintage_age = round((context.cutoff - context.vintage).total_seconds() / 3600.0, 2)

    return {
        "delivery_date": context.delivery_date.isoformat(),
        "cutoff_utc": iso_utc(context.cutoff),
        "as_of_utc": iso_utc(context.as_of),
        "vintage": {
            "available": context.vintage is not None,
            "publish_time_utc": iso_utc(context.vintage) if context.vintage else None,
            "age_hours": vintage_age,
            "horizon_hours": 24,
            "note": (
                "Newest WINDFOR vintage published before gate closure."
                if context.vintage
                else "No forecast covering this delivery day had been published by the cutoff."
            ),
        },
        "summary": summary,
        "hours": rows,
        "delivery_hours": [
            {"hour": slot.hour, "start_utc": iso_utc(slot.start_utc)}
            for slot in delivery_hours(context.delivery_date)
        ],
    }


def build_vintage_evolution(
    dataset: PilotDataset,
    delivery_date: date,
    cutoff: datetime,
    *,
    limit: int = 16,
) -> dict[str, object]:
    """How the forecast for this delivery day was revised, up to gate closure.

    Only vintages published before the cutoff are shown - a desk could not have
    seen the rest, and showing them would leak hindsight into a revision
    analysis.
    """
    hours = delivery_hours(delivery_date)
    infos = dataset.vintages_for(delivery_date, cutoff)
    total = len(infos)
    if len(infos) > limit:
        infos = infos[-limit:]

    series: list[dict[str, object]] = []
    for info in infos:
        targets = dataset.vintage_series(info.publish_time)
        values = [targets.get(slot.start_utc) for slot in hours]
        present = [v for v in values if v is not None]
        if not present:
            continue
        series.append(
            {
                "publish_time_utc": iso_utc(info.publish_time),
                "age_hours": round((cutoff - info.publish_time).total_seconds() / 3600.0, 2),
                "mean_mw": round(float(np.mean(present)), 1),
                "values": [None if value is None else round(value, 1) for value in values],
            }
        )

    selected = dataset.vintage_for(delivery_date, cutoff)
    actual_values = []
    for slot in hours:
        actual = dataset.actuals.get(slot.start_utc)
        visible = actual is not None and actual.publish_time <= dataset.as_of
        actual_values.append(round(actual.mw, 1) if (actual is not None and visible) else None)

    return {
        "delivery_date": delivery_date.isoformat(),
        "cutoff_utc": iso_utc(cutoff),
        "hours": [{"hour": slot.hour, "start_utc": iso_utc(slot.start_utc)} for slot in hours],
        "vintages": series,
        "selected_vintage_utc": iso_utc(selected) if selected else None,
        "actual_mw": actual_values if any(v is not None for v in actual_values) else None,
        "total_vintages_available": total,
    }
