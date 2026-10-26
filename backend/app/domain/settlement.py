"""UK electricity settlement clock.

The GB market runs on *settlement periods*: 30-minute blocks that start at
local midnight. Delivery days are local days, so a day normally has 48 periods,
46 on the spring DST transition and 50 on the autumn one.

Everything inside the application is stored in naive UTC. This module is the
single place that knows about ``Europe/London``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
UTC = UTC

PERIOD = timedelta(minutes=30)
HOUR = timedelta(hours=1)


def utcnow() -> datetime:
    """Current time as naive UTC (the app-wide convention)."""
    return datetime.now(tz=UTC).replace(tzinfo=None, microsecond=0)


def to_naive_utc(value: datetime) -> datetime:
    """Normalise any datetime to naive UTC."""
    if value.tzinfo is None:
        return value.replace(microsecond=0)
    return value.astimezone(UTC).replace(tzinfo=None, microsecond=0)


def parse_utc(value: str | datetime) -> datetime:
    """Parse an ISO-8601 string (``Z`` suffix tolerated) into naive UTC."""
    if isinstance(value, datetime):
        return to_naive_utc(value)
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return to_naive_utc(parsed)


def to_london(value: datetime) -> datetime:
    """Attach Europe/London to a naive-UTC instant."""
    return to_naive_utc(value).replace(tzinfo=UTC).astimezone(LONDON)


def local_midnight_utc(day: date) -> datetime:
    """UTC instant of local midnight starting ``day``."""
    local = datetime.combine(day, time(0, 0), tzinfo=LONDON)
    return local.astimezone(UTC).replace(tzinfo=None)


def local_midnight_next_utc(day: date) -> datetime:
    return local_midnight_utc(day + timedelta(days=1))


def settlement_period(instant: datetime) -> tuple[date, int]:
    """Map a UTC instant to (settlement date, settlement period).

    Implemented by elapsed half-hours from local midnight rather than by
    wall-clock arithmetic, so DST days are numbered the way Elexon numbers
    them (46/48/50 periods, no gaps or repeats).
    """
    local = to_london(instant)
    day = local.date()
    elapsed = to_naive_utc(instant) - local_midnight_utc(day)
    period = int(elapsed // PERIOD) + 1
    # Guard against an instant that lands in the repeated autumn hour but is
    # still before local midnight: clamp into the valid range.
    return day, max(1, min(period, 50))


def period_start_utc(day: date, period: int) -> datetime:
    """UTC start instant of a given settlement period."""
    return local_midnight_utc(day) + (period - 1) * PERIOD


@dataclass(frozen=True, slots=True)
class HourSlot:
    """One hourly delivery block, as used for forecast/actual comparison."""

    delivery_date: date
    hour: int  # local hour label 0-23
    start_utc: datetime  # naive UTC
    end_utc: datetime

    @property
    def label(self) -> str:
        return f"{self.hour:02d}:00"


@dataclass(frozen=True, slots=True)
class PeriodSlot:
    settlement_date: date
    period: int
    start_utc: datetime
    end_utc: datetime


def delivery_hours(day: date) -> list[HourSlot]:
    """All hourly blocks of a local delivery day, in absolute-time order."""
    start = local_midnight_utc(day)
    end = local_midnight_next_utc(day)
    slots: list[HourSlot] = []
    cursor = start
    while cursor < end:
        slots.append(
            HourSlot(
                delivery_date=day,
                hour=to_london(cursor).hour,
                start_utc=cursor,
                end_utc=cursor + HOUR,
            )
        )
        cursor += HOUR
    return slots


def delivery_periods(day: date) -> list[PeriodSlot]:
    """All 30-minute settlement periods of a local delivery day."""
    start = local_midnight_utc(day)
    end = local_midnight_next_utc(day)
    slots: list[PeriodSlot] = []
    cursor = start
    index = 1
    while cursor < end:
        slots.append(
            PeriodSlot(
                settlement_date=day,
                period=index,
                start_utc=cursor,
                end_utc=cursor + PERIOD,
            )
        )
        cursor += PERIOD
        index += 1
    return slots


def decision_cutoff(
    delivery_date: date,
    hour: int | None = None,
    minute: int | None = None,
) -> datetime:
    """Gate-closure instant for a delivery day, as naive UTC.

    Defaults to 09:30 Europe/London on D-1 - just after the GB day-ahead
    auction gate closure, which is when the trading desk has to have its
    bids in. The cutoff is a first-class parameter everywhere in the API,
    because *which* forecast is available depends entirely on it.
    """
    if hour is None or minute is None:
        from ..config import get_settings

        settings = get_settings()
        hour = settings.default_cutoff_hour if hour is None else hour
        minute = settings.default_cutoff_minute if minute is None else minute

    previous_day = delivery_date - timedelta(days=1)
    local = datetime.combine(previous_day, time(hour % 24, minute % 60), tzinfo=LONDON)
    return local.astimezone(UTC).replace(tzinfo=None)


def cutoff_for(
    delivery_date: date,
    hour: int | None = None,
    minute: int | None = None,
) -> datetime:
    """Alias kept for readability in services."""
    return decision_cutoff(delivery_date, hour, minute)


def lead_hours(target: datetime, publish: datetime) -> float:
    """How far ahead of its target a forecast was issued, in hours."""
    return round((to_naive_utc(target) - to_naive_utc(publish)).total_seconds() / 3600.0, 2)


def format_london(value: datetime) -> str:
    """Human-readable local timestamp, e.g. ``31 Jan 09:30``."""
    return to_london(value).strftime("%d %b %H:%M")


def iso_utc(value: datetime) -> str:
    """Serialise a naive-UTC datetime with an explicit ``Z`` suffix."""
    return to_naive_utc(value).isoformat(timespec="seconds") + "Z"
