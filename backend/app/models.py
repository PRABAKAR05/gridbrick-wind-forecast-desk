"""SQLAlchemy models.

Two facts tables carry the whole product:

* ``wind_actuals``    - half-hourly national wind outturn (FUELHH, fuelType=WIND)
* ``wind_forecasts``  - hourly national wind forecast *vintages* (WINDFOR)

``wind_forecasts`` is append-only and keyed by ``(publish_time, target_time)``.
Keeping every vintage - rather than only the latest forecast per target - is
what makes point-in-time evaluation possible: for any delivery day we can
reconstruct exactly which forecast a trader could have seen at the gate.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class WindActual(Base):
    """One settlement period of realised national wind generation."""

    __tablename__ = "wind_actuals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # naive UTC
    publish_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # naive UTC
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_period: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_mw: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="FUELHH")
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("start_time", name="uq_wind_actuals_start_time"),
        Index("ix_wind_actuals_settlement_date", "settlement_date"),
        Index("ix_wind_actuals_start_time", "start_time"),
    )


class WindForecast(Base):
    """One (vintage, target hour) pair of the Elexon WINDFOR feed."""

    __tablename__ = "wind_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publish_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # naive UTC
    target_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # naive UTC
    generation_mw: Mapped[float] = mapped_column(Float, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("publish_time", "target_time", name="uq_wind_forecast_vintage_target"),
        Index("ix_wind_forecasts_publish_time", "publish_time"),
        Index("ix_wind_forecasts_target_time", "target_time"),
    )


class IngestionRun(Base):
    """Audit trail for every data load - observability for the pipeline."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    actuals_upserted: Mapped[int] = mapped_column(Integer, default=0)
    forecasts_upserted: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditEvent(Base):
    """Lightweight append-only log of API-triggered actions."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
