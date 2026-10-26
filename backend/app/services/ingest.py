"""Data ingestion: Elexon -> local warehouse, plus a committed seed snapshot.

Two load paths share one idempotent upsert:

1. **Live pull** from the BMRS API (used at boot or via the admin endpoint).
2. **Seed snapshot** (``backend/seeds/*.jsonl.gz``) so a fresh container, an
   offline reviewer, or a CI job gets an identical warehouse without touching
   the network.

Both are safe to run repeatedly: ``ON CONFLICT`` upserts make ingestion
idempotent, which also means a partial failure can simply be retried.
"""

from __future__ import annotations

import gzip
import json
import logging
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..domain.settlement import iso_utc, parse_utc, utcnow
from ..models import IngestionRun, WindActual, WindForecast
from .elexon import ActualRow, ElexonClient, ForecastRow

logger = logging.getLogger(__name__)

_BATCH = 400


def _upsert(session: Session, model, rows: Sequence[dict], conflict_cols: list[str]) -> int:
    if not rows:
        return 0
    dialect = session.get_bind().dialect.name
    written = 0
    update_cols = [c for c in rows[0] if c not in conflict_cols]

    for start in range(0, len(rows), _BATCH):
        batch = rows[start : start + _BATCH]
        if dialect == "sqlite":
            stmt = sqlite_insert(model).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_cols,
                set_={col: getattr(stmt.excluded, col) for col in update_cols},
            )
        elif dialect == "postgresql":
            stmt = pg_insert(model).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_cols,
                set_={col: getattr(stmt.excluded, col) for col in update_cols},
            )
        else:  # pragma: no cover - fallback for exotic backends
            session.bulk_insert_mappings(model, batch)
            written += len(batch)
            continue
        session.execute(stmt)
        written += len(batch)
    return written


def upsert_actuals(session: Session, rows: Iterable[ActualRow]) -> int:
    now = utcnow()
    payload = [
        {
            "start_time": row.start_time,
            "publish_time": row.publish_time,
            "settlement_date": row.settlement_date,
            "settlement_period": row.settlement_period,
            "generation_mw": row.generation_mw,
            "source": "FUELHH",
            "ingested_at": now,
        }
        for row in rows
    ]
    return _upsert(session, WindActual, payload, ["start_time"])


def upsert_forecasts(session: Session, rows: Iterable[ForecastRow]) -> int:
    now = utcnow()
    payload = [
        {
            "publish_time": row.publish_time,
            "target_time": row.target_time,
            "generation_mw": row.generation_mw,
            "ingested_at": now,
        }
        for row in rows
    ]
    return _upsert(session, WindForecast, payload, ["publish_time", "target_time"])


async def ingest_window(
    session: Session,
    start: datetime,
    end: datetime,
    *,
    trigger: str,
    settings: Settings | None = None,
    client: ElexonClient | None = None,
) -> IngestionRun:
    """Pull [start, end) from Elexon and persist it. Returns the audit record."""
    settings = settings or get_settings()
    run = IngestionRun(started_at=utcnow(), status="running", trigger=trigger)
    session.add(run)
    session.commit()
    session.refresh(run)

    actuals_total = 0
    forecasts_total = 0
    try:
        async with ElexonClient(settings, client) as feed:
            # Chunk on the same seven-day grid the API requires.
            from .elexon import _chunk_windows  # local import keeps the public surface tidy

            for window_start, window_end in _chunk_windows(start, end, settings.elexon_max_window_days):
                actuals = await feed.fetch_actuals(window_start, window_end)
                forecasts = await feed.fetch_forecasts(window_start, window_end)
                actuals_total += upsert_actuals(session, actuals)
                forecasts_total += upsert_forecasts(session, forecasts)
                session.commit()
                logger.info(
                    "ingested window %s -> %s (%d actuals, %d forecasts)",
                    iso_utc(window_start),
                    iso_utc(window_end),
                    len(actuals),
                    len(forecasts),
                )

        run.status = "success"
        run.actuals_upserted = actuals_total
        run.forecasts_upserted = forecasts_total
        run.message = "live BMRS pull"
    except Exception as exc:
        session.rollback()
        run = session.get(IngestionRun, run.id) or run
        run.status = "failed"
        run.message = str(exc)[:1000]
        logger.exception("ingestion failed")
    finally:
        run.finished_at = utcnow()
        session.add(run)
        session.commit()
        session.refresh(run)
    return run


# --------------------------------------------------------------------- seeds
def seed_paths(seed_dir: Path) -> tuple[Path, Path]:
    return seed_dir / "wind_actuals.jsonl.gz", seed_dir / "wind_forecasts.jsonl.gz"


def export_seed(session: Session, seed_dir: Path) -> dict[str, int]:
    """Write the warehouse to compact gzipped JSON lines for the repo."""
    seed_dir.mkdir(parents=True, exist_ok=True)
    actuals_path, forecasts_path = seed_paths(seed_dir)

    actual_rows = session.execute(select(WindActual).order_by(WindActual.start_time)).scalars()
    count_a = 0
    with gzip.open(actuals_path, "wt", encoding="utf-8", compresslevel=9) as handle:
        for row in actual_rows:
            handle.write(
                json.dumps(
                    {
                        "s": iso_utc(row.start_time),
                        "p": iso_utc(row.publish_time),
                        "g": round(row.generation_mw, 3),
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
            count_a += 1

    forecast_rows = session.execute(
        select(WindForecast).order_by(WindForecast.publish_time, WindForecast.target_time)
    ).scalars()
    count_f = 0
    with gzip.open(forecasts_path, "wt", encoding="utf-8", compresslevel=9) as handle:
        for row in forecast_rows:
            handle.write(
                json.dumps(
                    {
                        "p": iso_utc(row.publish_time),
                        "t": iso_utc(row.target_time),
                        "g": round(row.generation_mw, 3),
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
            count_f += 1

    logger.info("exported seed: %d actuals, %d forecasts -> %s", count_a, count_f, seed_dir)
    return {"actuals": count_a, "forecasts": count_f}


def load_seed(session: Session, seed_dir: Path | None = None) -> dict[str, int]:
    """Populate an empty warehouse from the committed snapshot."""
    settings = get_settings()
    seed_dir = seed_dir or settings.seed_dir
    actuals_path, forecasts_path = seed_paths(seed_dir)
    if not actuals_path.exists() or not forecasts_path.exists():
        return {"actuals": 0, "forecasts": 0}

    from ..domain.settlement import settlement_period

    actual_payload: list[dict] = []
    now = utcnow()
    with gzip.open(actuals_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            start = parse_utc(record["s"])
            day, period = settlement_period(start)
            actual_payload.append(
                {
                    "start_time": start,
                    "publish_time": parse_utc(record["p"]),
                    "settlement_date": day,
                    "settlement_period": period,
                    "generation_mw": float(record["g"]),
                    "source": "FUELHH-seed",
                    "ingested_at": now,
                }
            )

    forecast_payload: list[dict] = []
    with gzip.open(forecasts_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            forecast_payload.append(
                {
                    "publish_time": parse_utc(record["p"]),
                    "target_time": parse_utc(record["t"]),
                    "generation_mw": float(record["g"]),
                    "ingested_at": now,
                }
            )

    written_a = _upsert(session, WindActual, actual_payload, ["start_time"])
    written_f = _upsert(session, WindForecast, forecast_payload, ["publish_time", "target_time"])
    session.commit()
    logger.info("loaded seed: %d actuals, %d forecasts", written_a, written_f)
    return {"actuals": written_a, "forecasts": written_f}


def warehouse_is_empty(session: Session) -> bool:
    count = session.execute(select(func.count()).select_from(WindActual)).scalar_one()
    forecasts = session.execute(select(func.count()).select_from(WindForecast)).scalar_one()
    return count == 0 or forecasts == 0
