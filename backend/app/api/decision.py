"""Decision Desk endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ..domain.procurement import RiskPolicy
from ..schemas import DecisionOut, VintageEvolutionOut
from ..services.analytics import PilotDataset
from ..services.decision import build_decision, build_vintage_evolution, serialise
from .deps import dataset_dependency, make_cutoff, resolve_day

router = APIRouter(tags=["decision"])


@router.get(
    "/decision/{delivery_date}",
    response_model=DecisionOut,
    summary="Latest forecast visible at gate closure, with uncertainty band",
)
def decision(
    delivery_date: date,
    dataset: Annotated[PilotDataset, Depends(dataset_dependency)],
    cutoff_hour: Annotated[int | None, Query(ge=0, le=23, description="Local hour of gate closure on D-1")] = None,
    cutoff_minute: Annotated[int | None, Query(ge=0, le=59)] = None,
    c_short: Annotated[float, Query(gt=0, description="Relative cost of being short")] = 1.5,
    c_long: Annotated[float, Query(gt=0, description="Relative cost of being long")] = 1.0,
) -> dict[str, Any]:
    day = resolve_day(delivery_date)
    cutoff = make_cutoff(day, cutoff_hour, cutoff_minute)
    context = build_decision(dataset, day, cutoff, dataset.as_of)
    return serialise(context, RiskPolicy(c_short=c_short, c_long=c_long))


@router.get(
    "/decision/{delivery_date}/vintages",
    response_model=VintageEvolutionOut,
    summary="How the forecast for this day was revised before gate closure",
)
def vintages(
    delivery_date: date,
    dataset: Annotated[PilotDataset, Depends(dataset_dependency)],
    cutoff_hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    cutoff_minute: Annotated[int | None, Query(ge=0, le=59)] = None,
    limit: Annotated[int, Query(ge=2, le=48)] = 16,
) -> dict[str, Any]:
    day = resolve_day(delivery_date)
    cutoff = make_cutoff(day, cutoff_hour, cutoff_minute)
    return build_vintage_evolution(dataset, day, cutoff, limit=limit)
