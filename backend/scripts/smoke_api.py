"""Endpoint smoke test - hits every route and asserts the contract holds."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def main() -> int:
    failures = 0
    with TestClient(app) as client:
        checks = [
            ("GET", "/api/v1/health", None),
            ("GET", "/api/v1/meta", None),
            ("GET", "/api/v1/delivery-days", None),
            ("GET", "/api/v1/decision/2026-01-14", None),
            ("GET", "/api/v1/decision/2026-01-14?cutoff_hour=9&cutoff_minute=30", None),
            ("GET", "/api/v1/decision/2026-01-14/vintages", None),
            ("GET", "/api/v1/accuracy/report", None),
            ("GET", "/api/v1/accuracy/report?start=2026-01-10&end=2026-01-20", None),
            ("GET", "/api/v1/procurement/profiles", None),
            ("POST", "/api/v1/procurement/plan", {"delivery_date": "2026-01-14"}),
            ("POST", "/api/v1/procurement/plan", {"delivery_date": "2026-01-14", "demand_profile": "flat"}),
            ("GET", "/api/v1/decision/2026-06-01", None),  # out of window -> 422
        ]
        for method, url, body in checks:
            response = client.request(method, url, json=body)
            expected = 422 if "2026-06-01" in url else 200
            ok = response.status_code == expected
            failures += 0 if ok else 1
            size = len(response.content)
            print(f"{'OK ' if ok else 'FAIL'} {method:4s} {url:60s} {response.status_code} {size:>8d}B")
            if not ok:
                print(response.text[:800])

        decision = client.get("/api/v1/decision/2026-01-14").json()
        s = decision["summary"]
        print("\n--- decision 2026-01-14 ---")
        print(json.dumps({k: s[k] for k in list(s)[:18]}, indent=1, default=str)[:1800])
        print("vintage:", decision["vintage"])

        plan = client.post("/api/v1/procurement/plan", json={"delivery_date": "2026-01-14"}).json()
        print("\n--- procurement totals ---")
        print(json.dumps(plan["totals"], indent=1))
        print("policy:", plan["policy"])

        report = client.get("/api/v1/accuracy/report").json()
        print("\n--- accuracy headline ---")
        print(json.dumps(report["headline"], indent=1))
        print("benchmarks:", [(b["name"][:34], b["mae_mw"]) for b in report["benchmarks"]])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
