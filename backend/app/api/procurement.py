"""Procurement planner endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..domain.demand import available_profiles, build_profile, profile_meta
from ..domain.procurement import RiskPolicy, build_plan
from ..domain.settlement import decision_cutoff, iso_utc, to_naive_utc
from ..schemas import ProcurementOut, ProcurementRequest
from ..services.analytics import PilotDataset, resolve_as_of
from ..services.decision import build_decision, sample_for, serialise
from .deps import SessionDep, resolve_day

router = APIRouter(tags=["procurement"])


@router.get("/procurement/profiles", summary="Available (synthetic) demand shapes")
def profiles() -> dict[str, Any]:
    return {
        "profiles": available_profiles(),
        "note": "Demand is an input to this product, not a modelled quantity. These shapes are illustrative.",
    }


@router.post(
    "/procurement/plan",
    response_model=ProcurementOut,
    summary="Risk-adjusted thermal procurement for a delivery day",
)
def plan(request: ProcurementRequest, session: SessionDep) -> dict[str, Any]:
    day = resolve_day(request.delivery_date)
    as_of = resolve_as_of(session, to_naive_utc(request.as_of) if request.as_of else None)
    dataset = PilotDataset.load(session, as_of)
    cutoff = decision_cutoff(day, request.cutoff_hour, request.cutoff_minute)
    context = build_decision(dataset, day, cutoff, as_of)

    demand = build_profile(
        request.demand_profile,
        peak_mw=request.peak_mw,
        trough_mw=request.trough_mw,
        flat_mw=request.flat_mw,
    )
    policy = RiskPolicy(
        c_short=request.c_short,
        c_long=request.c_long,
        confidence=request.confidence,
    )

    plan_payload = build_plan(
        context.rows,
        demand,
        policy=policy,
        quantile_for=context.band.quantile,
        sample_for_lead=lambda lead: sample_for(context.band, lead),
    )

    forecast = serialise(context, policy)
    return {
        "delivery_date": day.isoformat(),
        "cutoff_utc": iso_utc(cutoff),
        "as_of_utc": iso_utc(as_of),
        "profile": {
            **profile_meta(request.demand_profile),
            "peak_mw": request.peak_mw,
            "trough_mw": request.trough_mw,
            "flat_mw": request.flat_mw,
        },
        "policy": plan_payload["policy"],
        "totals": plan_payload["totals"],
        "hours": plan_payload["hours"],
        "forecast": {
            "vintage": forecast["vintage"],
            "summary": forecast["summary"],
        },
    }
