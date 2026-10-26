"""Pydantic contracts for the public API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class BandOut(BaseModel):
    p10: float = Field(description="10th percentile of predictive wind generation, MW")
    p25: float
    p50: float | None = None
    p75: float
    p90: float
    source: str | None = Field(default=None, description="How the quantiles were estimated")


class HourOut(BaseModel):
    hour: int = Field(ge=0, le=23)
    start_utc: str
    forecast_mw: float | None = Field(default=None, description="Raw Elexon WINDFOR value")
    calibrated_mw: float | None = Field(
        default=None, description="Walk-forward recalibrated, decision-grade value"
    )
    actual_mw: float | None = Field(default=None, description="Null when outturn is not yet published")
    residual_mw: float | None = Field(default=None, description="calibrated - actual, MW")
    raw_residual_mw: float | None = Field(default=None, description="raw forecast - actual, MW")
    lead_hours: float | None = None
    band: BandOut | None = None


class VintageOut(BaseModel):
    available: bool
    publish_time_utc: str | None = None
    age_hours: float | None = Field(default=None, description="Cutoff minus publish time")
    horizon_hours: int | None = None
    note: str


class DecisionOut(BaseModel):
    delivery_date: str
    cutoff_utc: str
    as_of_utc: str
    vintage: VintageOut
    summary: dict[str, Any]
    hours: list[HourOut]
    delivery_hours: list[dict[str, Any]]


class VintageSeriesOut(BaseModel):
    publish_time_utc: str
    age_hours: float
    mean_mw: float
    values: list[float | None]


class VintageEvolutionOut(BaseModel):
    delivery_date: str
    cutoff_utc: str
    hours: list[dict[str, Any]]
    vintages: list[VintageSeriesOut]
    selected_vintage_utc: str | None
    actual_mw: list[float | None] | None
    total_vintages_available: int


class DayStatusOut(BaseModel):
    delivery_date: str
    cutoff_utc: str
    status: Literal["pending_gate", "awaiting_outturn", "partial", "realised"]
    vintage_publish_utc: str | None
    vintage_age_hours: float | None
    hours_realised: int
    mae_mw: float | None
    bias_mw: float | None
    forecast_mwh: float | None


class DeliveryDaysOut(BaseModel):
    as_of_utc: str
    days: list[DayStatusOut]


class AccuracyReportOut(BaseModel):
    as_of: str
    window: dict[str, Any]
    headline: dict[str, Any]
    raw: dict[str, Any]
    calibrated: dict[str, Any]
    by_horizon: list[dict[str, Any]]
    by_hour: list[dict[str, Any]]
    by_day: list[dict[str, Any]]
    calibration: dict[str, Any]
    benchmarks: list[dict[str, Any]]
    distribution: dict[str, Any]
    matrix: list[dict[str, Any]]
    scatter: list[dict[str, Any]]


class ProcurementRequest(BaseModel):
    delivery_date: date
    as_of: datetime | None = None
    cutoff_hour: int = Field(default=9, ge=0, le=23)
    cutoff_minute: int = Field(default=30, ge=0, le=59)
    demand_profile: Literal["synthetic_gb_winter", "flat"] = "synthetic_gb_winter"
    peak_mw: float = Field(default=46_000.0, gt=0)
    trough_mw: float = Field(default=30_000.0, gt=0)
    flat_mw: float = Field(default=38_000.0, gt=0)
    c_short: float = Field(default=1.5, gt=0, description="Relative cost of being short per MWh")
    c_long: float = Field(default=1.0, gt=0, description="Relative cost of being long per MWh")
    confidence: float | None = Field(
        default=None,
        gt=0,
        lt=1,
        description="Optional manual override of the critical fractile (0-1).",
    )

    @model_validator(mode="after")
    def _check_demand(self) -> ProcurementRequest:
        if self.demand_profile == "synthetic_gb_winter" and self.trough_mw >= self.peak_mw:
            raise ValueError("trough_mw must be below peak_mw for the synthetic profile")
        return self


class ProcurementOut(BaseModel):
    delivery_date: str
    cutoff_utc: str
    as_of_utc: str
    profile: dict[str, Any]
    policy: dict[str, Any]
    totals: dict[str, Any]
    hours: list[dict[str, Any]]
    forecast: dict[str, Any]


class MetaOut(BaseModel):
    app: str
    version: str
    environment: str
    pilot: dict[str, Any]
    data: dict[str, Any]
    defaults: dict[str, Any]
    demand_profiles: list[dict[str, Any]]
    ingestion_runs: list[dict[str, Any]]


class IngestResultOut(BaseModel):
    status: str
    trigger: str
    started_at: str
    finished_at: str | None
    actuals_upserted: int
    forecasts_upserted: int
    message: str | None = None
    warehouse: dict[str, Any]
