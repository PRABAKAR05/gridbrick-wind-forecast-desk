"""Shared FastAPI dependencies."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_session
from ..domain.settlement import decision_cutoff, to_naive_utc, utcnow
from ..services.analytics import PilotDataset, data_bounds, resolve_as_of

SessionDep = Annotated[Session, Depends(get_session)]


def pilot_days() -> list[date]:
    """Every delivery day in the pilot window, in calendar order."""
    settings = get_settings()
    from datetime import timedelta

    days: list[date] = []
    cursor = settings.pilot_start
    while cursor <= settings.pilot_end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def resolve_day(value: date) -> date:
    if value < get_settings().pilot_start or value > get_settings().pilot_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"delivery_date must fall inside the pilot window "
                f"({get_settings().pilot_start} to {get_settings().pilot_end})"
            ),
        )
    return value


def dataset_dependency(
    session: SessionDep,
    as_of: Annotated[datetime | None, Query(description="Point-in-time clock, ISO-8601")] = None,
) -> PilotDataset:
    effective = resolve_as_of(session, to_naive_utc(as_of) if as_of else None)
    return PilotDataset.load(session, effective)


def cutoff_from_query(
    cutoff_hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    cutoff_minute: Annotated[int | None, Query(ge=0, le=59)] = None,
) -> tuple[int | None, int | None]:
    return cutoff_hour, cutoff_minute


def make_cutoff(day: date, hour: int | None, minute: int | None) -> datetime:
    return decision_cutoff(day, hour, minute)


def ensure_not_future(as_of: datetime) -> None:
    if as_of > utcnow():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="as_of cannot be in the future",
        )


__all__ = [
    "SessionDep",
    "data_bounds",
    "dataset_dependency",
    "make_cutoff",
    "pilot_days",
    "resolve_day",
]
