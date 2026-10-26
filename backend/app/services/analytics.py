"""Point-in-time analytics engine.

Every number this module produces obeys one invariant:

    A response may only depend on data that was *published* on or before the
    cut-off it is answering for.

That is what makes the pilot honest. The naive alternative - "take the latest
WINDFOR value for each hour and compare it to the actual" - silently scores the
forecast against information nobody had at gate closure and flatters the model
by a wide margin. Here the vintage is selected by ``publish_time < cutoff``,
actuals are filtered by their own ``publish_time``, and uncertainty bands are
estimated only from days whose settlement completed before the cut-off.

Two forecasts are exposed throughout:

``forecast_mw``
    The raw Elexon WINDFOR value. This is what "forecast accuracy" means in
    the brief, and it is what the accuracy screen scores.

``calibrated_mw``
    The same value after a walk-forward affine recalibration against
    transmission-metered outturn (see ``domain.calibration``). This is the
    decision-grade number the procurement maths uses.

The dataset is small (one month of national wind), so a request loads what it
needs in two indexed queries and computes in memory.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..domain import metrics
from ..domain.calibration import IDENTITY, AffineCalibration
from ..domain.calibration import fit as fit_calibration
from ..domain.settlement import decision_cutoff, delivery_hours, lead_hours, utcnow
from ..models import WindActual, WindForecast

#: Installed GB wind capacity, used only to normalise error (MW).
GB_WIND_CAPACITY_MW = 30_000.0

DEFAULT_LEVELS: tuple[float, ...] = (0.10, 0.25, 0.50, 0.75, 0.90)
CALIBRATION_LEVELS: tuple[float, ...] = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)
LEAD_BUCKET_HOURS = 6


# --------------------------------------------------------------------- types
@dataclass(frozen=True, slots=True)
class DataBounds:
    actual_start: datetime | None
    actual_end: datetime | None
    forecast_publish_start: datetime | None
    forecast_publish_end: datetime | None
    latest_observable: datetime | None


@dataclass(frozen=True, slots=True)
class ActualHour:
    start_utc: datetime
    mw: float
    publish_time: datetime
    periods: int


@dataclass(frozen=True, slots=True)
class HourObservation:
    """One delivery hour of an as-of forecast paired with its outturn."""

    delivery_date: date
    hour: int
    start_utc: datetime
    forecast_mw: float | None
    calibrated_mw: float | None
    actual_mw: float | None
    publish_time: datetime | None
    lead_hours: float | None

    @property
    def raw_residual_mw(self) -> float | None:
        """Raw forecast minus actual; positive means the forecast ran high."""
        if self.forecast_mw is None or self.actual_mw is None:
            return None
        return self.forecast_mw - self.actual_mw

    @property
    def residual_mw(self) -> float | None:
        """Decision-grade (calibrated) forecast minus actual."""
        if self.calibrated_mw is None or self.actual_mw is None:
            return None
        return self.calibrated_mw - self.actual_mw

    @property
    def abs_error_mw(self) -> float | None:
        residual = self.residual_mw
        return None if residual is None else abs(residual)


@dataclass(frozen=True, slots=True)
class VintageInfo:
    publish_time: datetime
    hours_covered: int
    first_target: datetime
    last_target: datetime


# ------------------------------------------------------------------- clocking
def data_bounds(session: Session) -> DataBounds:
    actual_row = session.execute(
        select(
            func.min(WindActual.start_time),
            func.max(WindActual.start_time),
            func.max(WindActual.publish_time),
        )
    ).one()
    forecast_row = session.execute(
        select(
            func.min(WindForecast.publish_time),
            func.max(WindForecast.publish_time),
            func.max(WindForecast.target_time),
        )
    ).one()

    candidates = [value for value in (actual_row[2], forecast_row[1], utcnow()) if value is not None]
    return DataBounds(
        actual_start=actual_row[0],
        actual_end=actual_row[1],
        forecast_publish_start=forecast_row[0],
        forecast_publish_end=forecast_row[1],
        latest_observable=min(candidates) if candidates else None,
    )


def resolve_as_of(session: Session, requested: datetime | None) -> datetime:
    """Clamp a requested 'as of' instant to what the warehouse can support.

    Requesting an instant beyond the data is legitimate (a trader looking
    forward), so we clamp down to the newest piece of data we hold rather than
    erroring.
    """
    bounds = data_bounds(session)
    latest = bounds.latest_observable or utcnow()
    if requested is None:
        return min(utcnow(), latest)
    return min(requested, latest)


class PilotDataset:
    """In-memory view of the warehouse at a given instant."""

    def __init__(
        self,
        actuals: dict[datetime, ActualHour],
        vintages: dict[datetime, dict[datetime, float]],
        as_of: datetime,
    ) -> None:
        self.actuals = actuals
        self.vintages = vintages
        self.as_of = as_of
        self._observation_cache: dict[tuple, list[HourObservation]] = {}
        self._vintage_cache: dict[tuple[date, datetime], datetime | None] = {}
        self._calibration_cache: dict[tuple[date, datetime], AffineCalibration] = {}
        self._settings = get_settings()

    # -- loading -----------------------------------------------------------
    @classmethod
    def load(cls, session: Session, as_of: datetime) -> PilotDataset:
        # Column-level selects keep the hot path light: no ORM identity map.
        #
        # Actuals are loaded in full here, then filtered by their own
        # ``publish_time`` at every point of use. Loading the complete actual
        # table is deliberate: the warehouse stores one finalised row per
        # settlement period (FUELHH revisions overwrite in place), so filtering
        # at load time would make a historical fit depend on whether a revision
        # happened to land before or after the viewer's clock. Deferring the
        # check keeps the decision-time fit bit-for-bit reproducible.
        actual_rows = session.execute(
            select(WindActual.start_time, WindActual.generation_mw, WindActual.publish_time)
        ).all()

        buckets: dict[datetime, list[tuple[float, datetime]]] = {}
        for start_time, mw, publish_time in actual_rows:
            hour_start = start_time.replace(minute=0, second=0, microsecond=0)
            buckets.setdefault(hour_start, []).append((float(mw), publish_time))

        actuals = {
            hour_start: ActualHour(
                start_utc=hour_start,
                mw=round(statistics.fmean(v[0] for v in values), 3),
                publish_time=max(v[1] for v in values),
                periods=len(values),
            )
            for hour_start, values in buckets.items()
        }

        forecast_rows = session.execute(
            select(
                WindForecast.publish_time,
                WindForecast.target_time,
                WindForecast.generation_mw,
            ).where(WindForecast.publish_time <= as_of)
        ).all()

        vintages: dict[datetime, dict[datetime, float]] = {}
        for publish_time, target_time, mw in forecast_rows:
            vintages.setdefault(publish_time, {})[target_time] = float(mw)

        return cls(actuals=actuals, vintages=vintages, as_of=as_of)

    # -- vintage selection -------------------------------------------------
    def _before_cutoff(self, publish: datetime, cutoff: datetime) -> bool:
        """Strict inequality by default.

        A vintage stamped at exactly 09:30 is treated as *not yet available* at
        a 09:30 gate. It is the conservative reading, and it keeps a 2-4 hour
        staleness signal in the data rather than a suspiciously perfect 0.
        """
        if self._settings.strict_cutoff:
            return publish < cutoff
        return publish <= cutoff

    def vintage_for(self, delivery_date: date, cutoff: datetime) -> datetime | None:
        """Newest vintage published before the cutoff that covers the day."""
        key = (delivery_date, cutoff)
        if key in self._vintage_cache:
            return self._vintage_cache[key]

        hours = delivery_hours(delivery_date)
        required = max(1, int(round(0.8 * len(hours)))) if hours else 1
        chosen: datetime | None = None
        for publish_time in sorted(self.vintages):
            if not self._before_cutoff(publish_time, cutoff):
                break
            targets = self.vintages[publish_time]
            if sum(1 for slot in hours if slot.start_utc in targets) >= required:
                chosen = publish_time
        self._vintage_cache[key] = chosen
        return chosen

    def vintage_series(self, publish_time: datetime | None) -> dict[datetime, float]:
        return self.vintages.get(publish_time, {}) if publish_time else {}

    def vintages_for(self, delivery_date: date, cutoff: datetime | None = None) -> list[VintageInfo]:
        hours = delivery_hours(delivery_date)
        required = max(1, int(round(0.8 * len(hours))))
        infos: list[VintageInfo] = []
        for publish_time in sorted(self.vintages):
            if cutoff is not None and not self._before_cutoff(publish_time, cutoff):
                break
            targets = self.vintages[publish_time]
            hits = [slot.start_utc for slot in hours if slot.start_utc in targets]
            if len(hits) >= required:
                infos.append(
                    VintageInfo(
                        publish_time=publish_time,
                        hours_covered=len(hits),
                        first_target=min(hits),
                        last_target=max(hits),
                    )
                )
        return infos

    # -- raw pairs (used for calibration, never for calibration itself) ----
    def raw_pairs(self, delivery_date: date, cutoff: datetime, as_of: datetime) -> list[tuple[float, float]]:
        """(raw forecast, actual) pairs visible before ``cutoff``."""
        series = self.vintage_series(self.vintage_for(delivery_date, cutoff))
        pairs: list[tuple[float, float]] = []
        for slot in delivery_hours(delivery_date):
            forecast = series.get(slot.start_utc)
            actual = self.actuals.get(slot.start_utc)
            if forecast is None or actual is None or actual.publish_time > as_of:
                continue
            pairs.append((forecast, actual.mw))
        return pairs

    # -- calibration -------------------------------------------------------
    def _history_days(self, delivery_date: date, lookback: int) -> list[date]:
        return [delivery_date - timedelta(days=k) for k in range(1, lookback + 1)]

    def calibration_for(self, delivery_date: date, cutoff: datetime) -> AffineCalibration:
        """Walk-forward recalibration fitted strictly on earlier settlements."""
        key = (delivery_date, cutoff)
        if key in self._calibration_cache:
            return self._calibration_cache[key]

        pairs: list[tuple[float, float]] = []
        for day in self._history_days(delivery_date, self._settings.band_lookback_days):
            pairs.extend(self.raw_pairs(day, decision_cutoff(day), cutoff))

        model = fit_calibration(pairs)
        self._calibration_cache[key] = model
        return model

    # -- observations ------------------------------------------------------
    def observation(
        self,
        delivery_date: date,
        cutoff: datetime,
        as_of: datetime | None = None,
        *,
        calibrated: bool = True,
    ) -> list[HourObservation]:
        """As-of forecast vs outturn for one delivery day."""
        effective_as_of = as_of or self.as_of
        key = (delivery_date, cutoff, effective_as_of, calibrated)
        if key in self._observation_cache:
            return self._observation_cache[key]

        vintage = self.vintage_for(delivery_date, cutoff)
        series = self.vintage_series(vintage)
        model = self.calibration_for(delivery_date, cutoff) if calibrated else IDENTITY

        rows: list[HourObservation] = []
        for slot in delivery_hours(delivery_date):
            actual = self.actuals.get(slot.start_utc)
            visible = actual if (actual is not None and actual.publish_time <= effective_as_of) else None
            forecast = series.get(slot.start_utc)
            calibrated_value = model.apply(forecast) if forecast is not None else None
            rows.append(
                HourObservation(
                    delivery_date=delivery_date,
                    hour=slot.hour,
                    start_utc=slot.start_utc,
                    forecast_mw=forecast,
                    calibrated_mw=calibrated_value,
                    actual_mw=visible.mw if visible else None,
                    publish_time=vintage,
                    lead_hours=lead_hours(slot.start_utc, vintage) if vintage else None,
                )
            )
        self._observation_cache[key] = rows
        return rows

    def realised_observations(
        self,
        days: Sequence[date],
        cutoff_fn=decision_cutoff,
        *,
        as_of: datetime | None = None,
        calibrated: bool = True,
    ) -> list[HourObservation]:
        out: list[HourObservation] = []
        for day in days:
            for row in self.observation(day, cutoff_fn(day), as_of, calibrated=calibrated):
                if row.actual_mw is not None and (
                    row.calibrated_mw if calibrated else row.forecast_mw
                ) is not None:
                    out.append(row)
        return out

    def all_forecast_points(self) -> list[tuple[datetime, datetime, float]]:
        return [
            (target, publish, mw)
            for publish, series in self.vintages.items()
            for target, mw in series.items()
        ]

    # -- bands -------------------------------------------------------------
    @property
    def band_inflation(self) -> float:
        return self._settings.band_inflation

    def band_model(
        self,
        delivery_date: date,
        cutoff: datetime,
        *,
        lookback_days: int | None = None,
        cutoff_fn=decision_cutoff,
    ) -> BandModel:
        """Walk-forward decision-grade residual pool from earlier settlements."""
        lookback = lookback_days or self._settings.band_lookback_days
        by_bucket: dict[int, list[float]] = {}
        pooled: list[float] = []
        usable_days = 0

        for day in self._history_days(delivery_date, lookback):
            used_any = False
            for row in self.observation(day, cutoff_fn(day), as_of=cutoff):
                residual = row.residual_mw
                if residual is None or row.lead_hours is None:
                    continue
                by_bucket.setdefault(lead_bucket(row.lead_hours), []).append(residual)
                pooled.append(residual)
                used_any = True
            if used_any:
                usable_days += 1

        return BandModel(
            by_bucket=by_bucket,
            pooled=pooled,
            usable_days=usable_days,
            lookback_days=lookback,
            inflation=self._settings.band_inflation,
        )


def lead_bucket(hours: float) -> int:
    return int(max(0.0, hours) // LEAD_BUCKET_HOURS)


@dataclass(slots=True)
class BandModel:
    """Predictive error quantiles estimated from realised, decision-time errors.

    ``inflation`` is a split-conformal style widening factor applied around the
    median, chosen because walk-forward testing showed the trailing-window
    quantiles under-cover by a few points out of sample. Scaling around the
    median keeps the point forecast unbiased while widening the tails.
    """

    by_bucket: dict[int, list[float]]
    pooled: list[float]
    usable_days: int
    lookback_days: int
    min_samples: int = 48
    inflation: float = 1.0

    def _sample(self, lead: float) -> tuple[list[float], str]:
        sample = self.by_bucket.get(lead_bucket(lead), [])
        if len(sample) >= self.min_samples:
            return sample, "walk_forward_lead_bucket"
        return self.pooled, "walk_forward_pooled"

    def offsets(self, lead: float, levels: Iterable[float] = DEFAULT_LEVELS) -> dict[str, float | str] | None:
        sample, source = self._sample(lead)
        if len(sample) < self.min_samples:
            return None
        result: dict[str, float | str] = {
            f"p{int(round(level * 100)):02d}": round(self._scaled(sample, level), 1)
            for level in levels
        }
        result["source"] = source
        return result

    def _scaled(self, sample: list[float], level: float) -> float:
        median = float(np.quantile(sample, 0.5))
        raw = float(np.quantile(sample, level))
        return median + self.inflation * (raw - median)

    @property
    def ready(self) -> bool:
        return len(self.pooled) >= self.min_samples

    def quantile(self, lead: float, level: float) -> float | None:
        """Inflated predictive quantile of `calibrated forecast - actual`."""
        sample, _ = self._sample(lead)
        if len(sample) < self.min_samples:
            return None
        return self._scaled(sample, level)

    def raw_quantile(self, lead: float, level: float) -> float | None:
        sample, _ = self._sample(lead)
        if len(sample) < self.min_samples:
            return None
        return float(np.quantile(sample, level))


# -------------------------------------------------------------------- reports
def hour_series(observations: Sequence[HourObservation], band: BandModel | None) -> list[dict[str, object]]:
    """Serialise one delivery day's forecast/actual/band rows."""
    rows: list[dict[str, object]] = []
    for row in observations:
        payload: dict[str, object] = {
            "hour": row.hour,
            "start_utc": row.start_utc.isoformat() + "Z",
            "forecast_mw": None if row.forecast_mw is None else round(row.forecast_mw, 1),
            "calibrated_mw": None if row.calibrated_mw is None else round(row.calibrated_mw, 1),
            "actual_mw": None if row.actual_mw is None else round(row.actual_mw, 1),
            "residual_mw": None if row.residual_mw is None else round(row.residual_mw, 1),
            "raw_residual_mw": None if row.raw_residual_mw is None else round(row.raw_residual_mw, 1),
            "lead_hours": row.lead_hours,
            "band": None,
        }
        basis = row.calibrated_mw if row.calibrated_mw is not None else row.forecast_mw
        if band is not None and row.lead_hours is not None and basis is not None:
            offsets = band.offsets(row.lead_hours)
            if offsets:
                payload["band"] = {
                    "p10": round(basis + float(offsets["p10"]), 1),
                    "p25": round(basis + float(offsets["p25"]), 1),
                    "p50": round(basis + float(offsets["p50"]), 1),
                    "p75": round(basis + float(offsets["p75"]), 1),
                    "p90": round(basis + float(offsets["p90"]), 1),
                    "source": offsets["source"],
                }
        rows.append(payload)
    return rows


def band_summary(band: BandModel | None, observations: Sequence[HourObservation]) -> dict[str, object]:
    if band is None or not band.ready:
        return {
            "available": False,
            "reason": "Not enough realised decision-time history to estimate a band.",
            "usable_days": band.usable_days if band else 0,
            "lookback_days": band.lookback_days if band else 0,
        }
    leads = [row.lead_hours for row in observations if row.lead_hours is not None]
    median_lead = statistics.fmean(leads) if leads else 24.0
    p10 = band.quantile(median_lead, 0.10)
    p90 = band.quantile(median_lead, 0.90)
    width = (p90 - p10) if (p10 is not None and p90 is not None) else None
    return {
        "available": True,
        "usable_days": band.usable_days,
        "lookback_days": band.lookback_days,
        "samples": len(band.pooled),
        "median_lead_hours": round(median_lead, 1),
        "p10_offset_mw": None if p10 is None else round(p10, 1),
        "p90_offset_mw": None if p90 is None else round(p90, 1),
        "p80_width_mw": None if width is None else round(width, 1),
        "capacity_note": f"Band estimated from {band.usable_days} settled delivery days.",
    }


def accuracy_report(
    dataset: PilotDataset,
    days: Sequence[date],
    *,
    cutoff_fn=decision_cutoff,
) -> dict[str, object]:
    """Full accuracy document backing the Forecast Accuracy screen."""
    raw_obs = dataset.realised_observations(days, cutoff_fn, as_of=dataset.as_of, calibrated=False)
    cal_obs = dataset.realised_observations(days, cutoff_fn, as_of=dataset.as_of, calibrated=True)

    raw_headline = metrics.summarise(
        [row.forecast_mw for row in raw_obs if row.forecast_mw is not None],
        [row.actual_mw for row in raw_obs if row.actual_mw is not None],
        capacity_mw=GB_WIND_CAPACITY_MW,
    )
    cal_headline = metrics.summarise(
        [row.calibrated_mw for row in cal_obs if row.calibrated_mw is not None],
        [row.actual_mw for row in cal_obs if row.actual_mw is not None],
        capacity_mw=GB_WIND_CAPACITY_MW,
    )

    # --- horizon curve: every vintage, not just the decision-time one -----
    horizon_buckets: dict[int, list[tuple[float, float]]] = {}
    for target, publish, mw in dataset.all_forecast_points():
        lead = lead_hours(target, publish)
        if lead < 0 or lead > 60:
            continue
        actual = dataset.actuals.get(target)
        if actual is None or actual.publish_time > dataset.as_of:
            continue
        horizon_buckets.setdefault(int(lead // 3) * 3, []).append((mw, actual.mw))

    by_horizon = []
    for bucket in sorted(horizon_buckets):
        pairs = horizon_buckets[bucket]
        summary = metrics.summarise([p[0] for p in pairs], [p[1] for p in pairs])
        by_horizon.append(
            {
                "lead_hours": bucket,
                "lead_label": f"{bucket}-{bucket + 3}h",
                "n": summary.n,
                "mae_mw": summary.mae_mw,
                "rmse_mw": summary.rmse_mw,
                "bias_mw": summary.bias_mw,
                "mape_pct": summary.mape_pct,
            }
        )

    # --- by hour of day (raw, decision-time vintage) ----------------------
    by_hour = []
    for hour in range(24):
        subset = [row for row in raw_obs if row.hour == hour]
        if not subset:
            continue
        summary = metrics.summarise(
            [row.forecast_mw for row in subset], [row.actual_mw for row in subset]
        )
        cal_subset = [row for row in cal_obs if row.hour == hour]
        cal_summary = metrics.summarise(
            [row.calibrated_mw for row in cal_subset], [row.actual_mw for row in cal_subset]
        )
        by_hour.append(
            {
                "hour": hour,
                "label": f"{hour:02d}:00",
                "n": summary.n,
                "mae_mw": summary.mae_mw,
                "bias_mw": summary.bias_mw,
                "calibrated_mae_mw": cal_summary.mae_mw,
                "mean_actual_mw": summary.mean_actual_mw,
                "mean_forecast_mw": summary.mean_forecast_mw,
            }
        )

    # --- by delivery day --------------------------------------------------
    by_day = []
    for day in days:
        subset = [row for row in cal_obs if row.delivery_date == day]
        raw_subset = [row for row in raw_obs if row.delivery_date == day]
        if not subset:
            by_day.append(
                {
                    "delivery_date": day.isoformat(),
                    "n": 0,
                    "mae_mw": None,
                    "bias_mw": None,
                    "rmse_mw": None,
                    "raw_mae_mw": None,
                    "raw_bias_mw": None,
                    "abs_energy_mwh": None,
                    "bias_energy_mwh": None,
                    "coverage_p80": None,
                }
            )
            continue
        summary = metrics.summarise(
            [row.calibrated_mw for row in subset], [row.actual_mw for row in subset]
        )
        raw_summary = metrics.summarise(
            [row.forecast_mw for row in raw_subset], [row.actual_mw for row in raw_subset]
        )
        residuals = [row.residual_mw for row in subset if row.residual_mw is not None]
        band = dataset.band_model(day, cutoff_fn(day), cutoff_fn=cutoff_fn)
        coverage_80 = None
        if band.ready:
            inside = []
            for row in subset:
                if row.residual_mw is None or row.lead_hours is None:
                    continue
                lo = band.quantile(row.lead_hours, 0.10)
                hi = band.quantile(row.lead_hours, 0.90)
                if lo is None or hi is None:
                    continue
                inside.append(lo <= row.residual_mw <= hi)
            coverage_80 = round(sum(inside) / len(inside), 4) if inside else None

        by_day.append(
            {
                "delivery_date": day.isoformat(),
                "n": summary.n,
                "mae_mw": summary.mae_mw,
                "bias_mw": summary.bias_mw,
                "rmse_mw": summary.rmse_mw,
                "raw_mae_mw": raw_summary.mae_mw,
                "raw_bias_mw": raw_summary.bias_mw,
                "abs_energy_mwh": round(sum(abs(r) for r in residuals), 0),
                "bias_energy_mwh": round(sum(residuals), 0),
                "coverage_p80": coverage_80,
            }
        )

    calibration_history = []
    for day in days:
        model = dataset.calibration_for(day, cutoff_fn(day))
        calibration_history.append({"delivery_date": day.isoformat(), **model.as_dict()})

    # Dense day x hour residual grid, for the heatmap. Decision-grade residuals.
    by_day_hour: dict[date, dict[int, float]] = {}
    for row in cal_obs:
        if row.residual_mw is not None:
            by_day_hour.setdefault(row.delivery_date, {})[row.hour] = row.residual_mw
    matrix = [
        {
            "delivery_date": day.isoformat(),
            "residuals": [
                None if by_day_hour.get(day, {}).get(hour) is None
                else round(by_day_hour[day][hour], 1)
                for hour in range(24)
            ],
        }
        for day in days
    ]

    residuals_all = [row.residual_mw for row in cal_obs if row.residual_mw is not None]
    raw_residuals = [row.raw_residual_mw for row in raw_obs if row.raw_residual_mw is not None]
    distribution = metrics.histogram(residuals_all, bins=30)
    distribution["quantiles"] = metrics.quantiles(residuals_all, DEFAULT_LEVELS)
    distribution["raw_quantiles"] = metrics.quantiles(raw_residuals, DEFAULT_LEVELS)

    return {
        "as_of": dataset.as_of.isoformat() + "Z",
        "window": {
            "start": min(days).isoformat() if days else None,
            "end": max(days).isoformat() if days else None,
            "days": len(days),
            "hours_evaluated": raw_headline.n,
        },
        "headline": raw_headline.as_dict(),
        "raw": raw_headline.as_dict(),
        "calibrated": cal_headline.as_dict(),
        "calibration": {
            "walk_forward": walk_forward_calibration(dataset, days, cutoff_fn),
            "fit_history": calibration_history,
            "current": dataset.calibration_for(
                max(days) + timedelta(days=1), cutoff_fn(max(days) + timedelta(days=1))
            ).as_dict()
            if days
            else IDENTITY.as_dict(),
            "method": (
                "Affine recalibration outturn ~ a*forecast + b, fitted on a trailing "
                "14-day window of decision-time vintages and applied out-of-sample."
            ),
        },
        "by_horizon": by_horizon,
        "by_hour": by_hour,
        "by_day": by_day,
        "benchmarks": benchmark_comparison(dataset, raw_obs, cal_obs, cutoff_fn),
        "distribution": distribution,
        "matrix": matrix,
        "scatter": [
            {
                "forecast": round(row.forecast_mw, 1),
                "calibrated": round(row.calibrated_mw, 1) if row.calibrated_mw is not None else None,
                "actual": round(row.actual_mw, 1),
            }
            for row in raw_obs
            if row.forecast_mw is not None and row.actual_mw is not None
        ],
    }


def walk_forward_calibration(dataset: PilotDataset, days: Sequence[date], cutoff_fn) -> dict[str, object]:
    """Does an 80% band actually contain 80% of outcomes?

    For each delivery day the band is rebuilt from earlier days only, then
    tested against that day's outturn. This is the only honest way to score a
    probabilistic forecast, and it is the number that lets a desk size a buffer
    with confidence.
    """
    hits_by_level: dict[float, list[bool]] = {level: [] for level in CALIBRATION_LEVELS}
    raw_hits: dict[float, list[bool]] = {level: [] for level in CALIBRATION_LEVELS}
    pinball: dict[str, list[float]] = {"p10": [], "p90": []}
    scored_days = 0

    for day in days:
        band = dataset.band_model(day, cutoff_fn(day), cutoff_fn=cutoff_fn)
        if not band.ready:
            continue
        day_scored = False
        for row in dataset.observation(day, cutoff_fn(day), as_of=dataset.as_of):
            if row.residual_mw is None or row.lead_hours is None:
                continue
            day_scored = True
            for level in CALIBRATION_LEVELS:
                alpha = (1.0 - level) / 2.0
                lo = band.quantile(row.lead_hours, alpha)
                hi = band.quantile(row.lead_hours, 1.0 - alpha)
                if lo is not None and hi is not None:
                    hits_by_level[level].append(bool(lo <= row.residual_mw <= hi))
                raw_lo = band.raw_quantile(row.lead_hours, alpha)
                raw_hi = band.raw_quantile(row.lead_hours, 1.0 - alpha)
                if raw_lo is not None and raw_hi is not None:
                    raw_hits[level].append(bool(raw_lo <= row.residual_mw <= raw_hi))
            for name, q in (("p10", 0.10), ("p90", 0.90)):
                value = band.quantile(row.lead_hours, q)
                if value is not None:
                    pinball[name].append(metrics.pinball_loss([row.residual_mw], value, q))
        if day_scored:
            scored_days += 1

    table = []
    for level in CALIBRATION_LEVELS:
        hits = hits_by_level[level]
        raw = raw_hits[level]
        observed = round(sum(hits) / len(hits), 4) if hits else None
        raw_observed = round(sum(raw) / len(raw), 4) if raw else None
        table.append(
            {
                "nominal": level,
                "observed": observed,
                "raw_observed": raw_observed,
                "gap": None if observed is None else round(observed - level, 4),
                "samples": len(hits),
            }
        )

    gaps = [abs(row["gap"]) for row in table if row["gap"] is not None]
    return {
        "scored_days": scored_days,
        "inflation": dataset.band_inflation,
        "table": table,
        "pinball_loss": {
            name: round(statistics.fmean(values), 2) if values else None
            for name, values in pinball.items()
        },
        "mean_abs_gap": round(statistics.fmean(gaps), 4) if gaps else None,
    }


def benchmark_comparison(
    dataset: PilotDataset,
    raw_obs: Sequence[HourObservation],
    cal_obs: Sequence[HourObservation],
    cutoff_fn,
) -> list[dict[str, object]]:
    """Model skill against persistence and expanding-window climatology."""
    days = sorted({row.delivery_date for row in raw_obs})
    if not days:
        return []

    persistence_f: list[float] = []
    persistence_a: list[float] = []
    climatology_f: list[float] = []
    climatology_a: list[float] = []
    hourly_history: dict[int, list[float]] = {}

    for day in days:
        cutoff = cutoff_fn(day)
        climatology_by_hour = {h: statistics.fmean(v) for h, v in hourly_history.items() if v}
        for row in dataset.observation(day, cutoff, as_of=dataset.as_of, calibrated=False):
            if row.actual_mw is None:
                continue
            # Persistence at gate closure must use the most recent same-hour
            # observation that had actually been published: for evening hours
            # that is D-2, not D-1.
            for lag in (1, 2, 3):
                candidate = dataset.actuals.get(row.start_utc - timedelta(days=lag))
                if candidate is not None and candidate.publish_time <= cutoff:
                    persistence_f.append(candidate.mw)
                    persistence_a.append(row.actual_mw)
                    break
            if row.hour in climatology_by_hour:
                climatology_f.append(climatology_by_hour[row.hour])
                climatology_a.append(row.actual_mw)
            hourly_history.setdefault(row.hour, []).append(row.actual_mw)

    model = metrics.summarise(
        [row.forecast_mw for row in raw_obs], [row.actual_mw for row in raw_obs]
    )
    calibrated = metrics.summarise(
        [row.calibrated_mw for row in cal_obs], [row.actual_mw for row in cal_obs]
    )

    rows: list[dict[str, object]] = [
        {
            "name": "Elexon WINDFOR (raw, decision-time vintage)",
            "mae_mw": model.mae_mw,
            "rmse_mw": model.rmse_mw,
            "bias_mw": model.bias_mw,
            "n": model.n,
            "skill": None,
            "note": "The feed as published. Level bias is expected: see note on scope.",
            "kind": "model",
        },
        {
            "name": "WINDFOR + walk-forward recalibration",
            "mae_mw": calibrated.mae_mw,
            "rmse_mw": calibrated.rmse_mw,
            "bias_mw": calibrated.bias_mw,
            "n": calibrated.n,
            "skill": None,
            "note": "Decision-grade input used by the procurement planner.",
            "kind": "calibrated",
        },
    ]

    baseline_mae = None
    if persistence_f:
        persist = metrics.summarise(persistence_f, persistence_a)
        baseline_mae = persist.mae_mw
        rows.append(
            {
                "name": "Naive persistence (last same-hour observation before gate)",
                "mae_mw": persist.mae_mw,
                "rmse_mw": persist.rmse_mw,
                "bias_mw": persist.bias_mw,
                "n": persist.n,
                "skill": None,
                "note": "Zero-cost benchmark any forecast must beat.",
                "kind": "baseline",
            }
        )
    if climatology_f:
        climate = metrics.summarise(climatology_f, climatology_a)
        rows.append(
            {
                "name": "Expanding climatology (hour-of-day mean)",
                "mae_mw": climate.mae_mw,
                "rmse_mw": climate.rmse_mw,
                "bias_mw": climate.bias_mw,
                "n": climate.n,
                "skill": None,
                "note": "Captures the diurnal shape but no weather signal.",
                "kind": "baseline",
            }
        )

    if baseline_mae:
        for row in rows:
            if row["kind"] in {"model", "calibrated"}:
                row["skill"] = metrics.skill_score(float(row["mae_mw"]), baseline_mae)  # type: ignore[arg-type]
    return rows
