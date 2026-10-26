"""Europe/London settlement arithmetic, including DST days."""

from __future__ import annotations

from datetime import date, datetime

from app.domain.settlement import (
    decision_cutoff,
    delivery_hours,
    delivery_periods,
    lead_hours,
    parse_utc,
    period_start_utc,
    settlement_period,
    to_naive_utc,
)


def test_parse_utc_normalises_offsets() -> None:
    assert parse_utc("2026-01-14T10:00:00+01:00") == datetime(2026, 1, 14, 9, 0)
    assert parse_utc("2026-01-14T09:00:00Z") == datetime(2026, 1, 14, 9, 0)
    aware = datetime(2026, 1, 14, 9, 0, tzinfo=None)
    assert to_naive_utc(aware) == aware


def test_gate_closure_is_local_0930_the_day_before() -> None:
    # January: GMT, so local 09:30 is UTC 09:30.
    assert decision_cutoff(date(2026, 1, 14)) == datetime(2026, 1, 13, 9, 30)
    # June: BST, so local 09:30 is UTC 08:30.
    assert decision_cutoff(date(2026, 6, 1)) == datetime(2026, 5, 31, 8, 30)
    # An explicit cutoff is honoured.
    assert decision_cutoff(date(2026, 1, 14), 7, 15) == datetime(2026, 1, 13, 7, 15)


def test_delivery_days_have_23_24_or_25_hours() -> None:
    assert len(delivery_hours(date(2026, 1, 14))) == 24
    assert len(delivery_hours(date(2026, 3, 29))) == 23  # clocks go forward
    assert len(delivery_hours(date(2026, 10, 25))) == 25  # clocks go back
    assert len(delivery_periods(date(2026, 1, 14))) == 48
    assert len(delivery_periods(date(2026, 3, 29))) == 46
    assert len(delivery_periods(date(2026, 10, 25))) == 50


def test_settlement_period_round_trip() -> None:
    day, period = settlement_period(parse_utc("2026-01-01T00:00:00Z"))
    assert (day, period) == (date(2026, 1, 1), 1)
    assert settlement_period(parse_utc("2026-01-01T00:30:00Z"))[1] == 2
    assert settlement_period(parse_utc("2026-01-01T23:30:00Z"))[1] == 48
    assert period_start_utc(day, 1) == datetime(2026, 1, 1, 0, 0)
    assert period_start_utc(day, 2) == datetime(2026, 1, 1, 0, 30)


def test_lead_hours() -> None:
    assert lead_hours(datetime(2026, 1, 14, 12, 0), datetime(2026, 1, 13, 9, 0)) == 27.0
    assert lead_hours(datetime(2026, 1, 14, 12, 0), datetime(2026, 1, 14, 12, 0)) == 0.0
