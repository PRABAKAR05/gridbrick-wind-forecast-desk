"""API contract and the point-in-time invariant.

The most important test here: the forecast numbers visible at gate closure must
be identical to the numbers a later observer sees for the same decision. Only
the outturn fields may change. That is the product's core correctness claim.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

GATE = "2026-01-13T09:30:00Z"
FORECAST_FIELDS = (
    "wind_forecast_mwh",
    "wind_calibrated_mwh",
    "wind_nominated_mwh",
    "wind_p10_mwh",
    "wind_p90_mwh",
    "expected_shortfall_mwh",
)


def test_health_and_meta(client: TestClient) -> None:
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["warehouse"]["actuals"] > 0

    meta = client.get("/api/v1/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert body["pilot"]["start"] == "2026-01-01"
    assert body["data"]["vintages"] > 0
    assert body["defaults"]["cutoff_hour"] == 9
    assert len(body["demand_profiles"]) == 2


def test_point_in_time_forecast_is_invariant(client: TestClient) -> None:
    at_gate = client.get(f"/api/v1/decision/2026-01-14?as_of={GATE}")
    later = client.get("/api/v1/decision/2026-01-14")
    assert at_gate.status_code == 200
    assert later.status_code == 200

    gate_body, later_body = at_gate.json(), later.json()
    gate_summary, later_summary = gate_body["summary"], later_body["summary"]

    # Same decision inputs, so every forecast-side number must match exactly.
    for field in FORECAST_FIELDS:
        assert gate_summary[field] == later_summary[field], field

    # At the gate no delivery-hour outturn exists yet.
    assert gate_summary["realised"] is False
    assert gate_summary["hours_with_actual"] == 0
    assert "mae_mw" not in gate_summary
    assert all(hour["actual_mw"] is None for hour in gate_body["hours"])

    # After the fact the same forecast can be scored.
    assert later_summary["realised"] is True
    assert later_summary["hours_with_actual"] == 24
    assert later_summary["mae_mw"] > 0
    assert all(hour["actual_mw"] is not None for hour in later_body["hours"])

    # The selected vintage is the latest one published strictly before the gate.
    assert gate_body["vintage"]["publish_time_utc"] == later_body["vintage"]["publish_time_utc"]
    assert gate_body["vintage"]["publish_time_utc"] < gate_body["cutoff_utc"]


def test_vintage_endpoint_respects_the_cutoff(client: TestClient) -> None:
    response = client.get(f"/api/v1/decision/2026-01-14/vintages?as_of={GATE}&limit=18")
    assert response.status_code == 200
    body = response.json()
    assert body["selected_vintage_utc"] is not None
    assert body["selected_vintage_utc"] < body["cutoff_utc"]
    assert body["vintages"]
    assert all(vintage["publish_time_utc"] < body["cutoff_utc"] for vintage in body["vintages"])


def test_accuracy_report_includes_both_bases_and_the_heatmap(client: TestClient) -> None:
    response = client.get("/api/v1/accuracy/report")
    assert response.status_code == 200
    body = response.json()

    assert body["headline"]["n"] == 744
    assert body["raw"]["mae_mw"] > body["calibrated"]["mae_mw"]
    assert body["calibrated"]["bias_mw"] < body["raw"]["bias_mw"]
    assert len(body["matrix"]) == 31
    assert all(len(row["residuals"]) == 24 for row in body["matrix"])
    assert len(body["benchmarks"]) == 4
    assert body["calibration"]["current"]["slope"] > 0


def test_procurement_plan_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/procurement/plan",
        json={
            "delivery_date": "2026-01-14",
            "as_of": GATE,
            "demand_profile": "synthetic_gb_winter",
            "c_short": 1.5,
            "c_long": 1.0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["policy"]["critical_fractile"] == 0.4
    assert len(body["hours"]) == 24
    assert body["totals"]["wind_nominated_mwh"] is not None
    assert body["totals"]["thermal_procured_mwh"] is not None
    assert body["totals"]["thermal_procured_mwh"] > body["totals"]["thermal_baseline_mwh"]

    # A more expensive shortfall pushes the nomination down and thermal cover up.
    cautious = client.post(
        "/api/v1/procurement/plan",
        json={"delivery_date": "2026-01-14", "as_of": GATE, "c_short": 4.0, "c_long": 1.0},
    ).json()
    assert cautious["policy"]["critical_fractile"] < body["policy"]["critical_fractile"]
    assert cautious["totals"]["wind_nominated_mwh"] < body["totals"]["wind_nominated_mwh"]


def test_bad_inputs_are_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/decision/2026-06-01").status_code == 422
    assert client.post("/api/v1/procurement/plan", json={"delivery_date": "2026-06-01"}).status_code == 422
    assert (
        client.post(
            "/api/v1/procurement/plan",
            json={
                "delivery_date": "2026-01-14",
                "demand_profile": "synthetic_gb_winter",
                "peak_mw": 30_000,
                "trough_mw": 46_000,
            },
        ).status_code
        == 422
    )
