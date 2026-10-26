"""Ad-hoc data quality probe (kept in the repo: shows how the feed behaves)."""

from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import SessionLocal  # noqa: E402
from app.domain.settlement import decision_cutoff, delivery_hours, iso_utc, utcnow  # noqa: E402
from app.services.analytics import PilotDataset, accuracy_report  # noqa: E402


def main() -> None:
    with SessionLocal() as session:
        dataset = PilotDataset.load(session, utcnow())

        print("vintages:", len(dataset.vintages))
        per_day = Counter(publish.date() for publish in dataset.vintages)
        counts = sorted(per_day.values())
        print("vintages/day min/median/max:", counts[0], statistics.median(counts), counts[-1])

        # What is actually available at a 09:30 gate?
        gaps: list[float] = []
        for day in (date(2026, 1, 1) + timedelta(days=i) for i in range(31)):
            cutoff = decision_cutoff(day)
            vintage = dataset.vintage_for(day, cutoff)
            if vintage is None:
                print("NO VINTAGE", day)
                continue
            gaps.append((cutoff - vintage).total_seconds() / 3600)
        print(
            "gate vintage age (h): min %.2f median %.2f max %.2f"
            % (min(gaps), statistics.median(gaps), max(gaps))
        )

        # Coverage of actual hours per delivery day
        missing = defaultdict(int)
        for day in (date(2026, 1, 1) + timedelta(days=i) for i in range(31)):
            for slot in delivery_hours(day):
                if slot.start_utc not in dataset.actuals:
                    missing[day] += 1
        print("days with missing actual hours:", dict(missing) or "none")

        # Vintage size / horizon
        sizes = Counter(len(series) for series in dataset.vintages.values())
        print("forecast points per vintage:", dict(sizes))
        sample_publish = sorted(dataset.vintages)[100]
        targets = sorted(dataset.vintages[sample_publish])
        print(
            f"sample vintage {iso_utc(sample_publish)}: {len(targets)} targets "
            f"{iso_utc(targets[0])} -> {iso_utc(targets[-1])}"
        )

        days = [date(2026, 1, 1) + timedelta(days=i) for i in range(31)]
        report = accuracy_report(dataset, days)
        print("\nHEADLINE", report["headline"])
        print("CALIBRATION", report["calibration"])
        print("BENCHMARKS")
        for row in report["benchmarks"]:
            print("  ", row)
        print("HORIZON")
        for row in report["by_horizon"]:
            print("  ", row)


if __name__ == "__main__":
    main()
