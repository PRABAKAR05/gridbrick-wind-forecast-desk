"""CLI: pull the pilot window from Elexon and refresh the committed seed.

Usage (from the backend directory):

    python scripts/ingest.py                # fetch + export seed
    python scripts/ingest.py --no-seed      # fetch only
    python scripts/ingest.py --from 2026-01-01 --to 2026-02-01
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.services.ingest import export_seed, ingest_window  # noqa: E402


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Elexon wind data")
    parser.add_argument("--from", dest="start", type=_parse_date, default=None)
    parser.add_argument("--to", dest="end", type=_parse_date, default=None)
    parser.add_argument("--no-seed", action="store_true", help="skip seed export")
    args = parser.parse_args()

    settings = get_settings()
    init_db()

    start = datetime.combine(args.start or settings.ingest_start, time.min)
    end = datetime.combine(args.end or settings.ingest_end, time.min)
    print(f"pulling publish window {start:%Y-%m-%d} -> {end:%Y-%m-%d} from {settings.elexon_base_url}")

    with SessionLocal() as session:
        run = await ingest_window(session, start, end, trigger="cli", settings=settings)
        print(f"status={run.status} actuals={run.actuals_upserted} forecasts={run.forecasts_upserted}")
        if run.message:
            print(f"message={run.message}")
        if run.status != "success":
            return 1
        if not args.no_seed:
            counts = export_seed(session, settings.seed_dir)
            print(f"seed exported: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
