"""Async client for the Elexon BMRS Insights API.

The two endpoints we need are the ``/stream`` variants referenced in the
product brief - they return a flat JSON array of rows for a time window.

The API rejects windows wider than seven days, so :meth:`fetch_*` transparently
splits any requested range into compliant chunks. Retries use capped
exponential backoff and are only attempted for transient failures.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from ..config import Settings, get_settings
from ..domain.settlement import parse_utc, settlement_period

logger = logging.getLogger(__name__)

_FUEL_TYPE = "WIND"


class ElexonError(RuntimeError):
    """Raised when the upstream feed cannot be read."""


@dataclass(frozen=True, slots=True)
class ActualRow:
    start_time: datetime
    publish_time: datetime
    settlement_date: date
    settlement_period: int
    generation_mw: float


@dataclass(frozen=True, slots=True)
class ForecastRow:
    publish_time: datetime
    target_time: datetime
    generation_mw: float


def _chunk_windows(start: datetime, end: datetime, max_days: int) -> list[tuple[datetime, datetime]]:
    """Split [start, end) into windows the BMRS API will accept."""
    if end <= start:
        return []
    step = timedelta(days=max(1, max_days))
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        boundary = min(cursor + step, end)
        windows.append((cursor, boundary))
        cursor = boundary
    return windows


class ElexonClient:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings or get_settings()
        self._external = client is not None
        self._client = client or httpx.AsyncClient(
            base_url=self._settings.elexon_base_url,
            timeout=self._settings.elexon_timeout_seconds,
            headers={
                "Accept": "application/json",
                "User-Agent": "GridBrick-ForecastDesk/1.0 (+pilot)",
            },
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )

    async def __aenter__(self) -> ElexonClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._external:
            await self._client.aclose()

    # ------------------------------------------------------------------ http
    async def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(self._settings.elexon_max_retries + 1):
            try:
                response = await self._client.get(path, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    raise ElexonError(f"upstream {response.status_code} for {path}")
                if response.status_code >= 400:
                    raise ElexonError(f"upstream {response.status_code} for {path}: {response.text[:200]}")
                payload = response.json()
                if isinstance(payload, dict):
                    payload = payload.get("data", [])
                if not isinstance(payload, list):
                    raise ElexonError(f"unexpected payload type for {path}: {type(payload).__name__}")
                return payload
            except (httpx.HTTPError, ElexonError, ValueError) as exc:
                last_error = exc
                if attempt >= self._settings.elexon_max_retries:
                    break
                delay = min(0.5 * (2**attempt), 4.0)
                logger.warning("elexon request failed (%s); retrying in %.1fs", exc, delay)
                await asyncio.sleep(delay)
        raise ElexonError(f"giving up on {path}: {last_error}") from last_error

    @staticmethod
    def _param(value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    # --------------------------------------------------------------- actuals
    async def fetch_actuals(self, start: datetime, end: datetime) -> list[ActualRow]:
        """FUELHH rows for wind over [start, end), keyed by publish time.

        Later publications for the same instant supersede earlier ones, so we
        de-duplicate on ``start_time`` keeping the newest ``publish_time``.
        """
        merged: dict[datetime, ActualRow] = {}
        for window_start, window_end in _chunk_windows(start, end, self._settings.elexon_max_window_days):
            rows = await self._get(
                "/datasets/FUELHH/stream",
                {
                    "publishDateTimeFrom": self._param(window_start),
                    "publishDateTimeTo": self._param(window_end),
                    "fuelType": _FUEL_TYPE,
                },
            )
            for raw in rows:
                parsed = self._parse_actual(raw)
                if parsed is None:
                    continue
                existing = merged.get(parsed.start_time)
                if existing is None or parsed.publish_time >= existing.publish_time:
                    merged[parsed.start_time] = parsed
        return sorted(merged.values(), key=lambda row: row.start_time)

    def _parse_actual(self, raw: dict[str, Any]) -> ActualRow | None:
        try:
            if (raw.get("fuelType") or _FUEL_TYPE).upper() != _FUEL_TYPE:
                return None
            generation = raw.get("generation")
            if generation is None:
                return None
            start = parse_utc(raw["startTime"])
            publish = parse_utc(raw.get("publishTime") or raw["startTime"])
            day, period = settlement_period(start)
            return ActualRow(
                start_time=start,
                publish_time=publish,
                settlement_date=day,
                settlement_period=period,
                generation_mw=float(generation),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("skipping malformed FUELHH row: %s (%s)", raw, exc)
            return None

    # ------------------------------------------------------------- forecasts
    async def fetch_forecasts(self, start: datetime, end: datetime) -> list[ForecastRow]:
        """All WINDFOR vintages published in [start, end)."""
        merged: dict[tuple[datetime, datetime], ForecastRow] = {}
        for window_start, window_end in _chunk_windows(start, end, self._settings.elexon_max_window_days):
            rows = await self._get(
                "/datasets/WINDFOR/stream",
                {
                    "publishDateTimeFrom": self._param(window_start),
                    "publishDateTimeTo": self._param(window_end),
                },
            )
            for raw in rows:
                parsed = self._parse_forecast(raw)
                if parsed is None:
                    continue
                merged[(parsed.publish_time, parsed.target_time)] = parsed
        return sorted(merged.values(), key=lambda row: (row.publish_time, row.target_time))

    def _parse_forecast(self, raw: dict[str, Any]) -> ForecastRow | None:
        try:
            generation = raw.get("generation")
            if generation is None:
                return None
            publish = parse_utc(raw["publishTime"])
            target = parse_utc(raw["startTime"])
            return ForecastRow(
                publish_time=publish,
                target_time=target,
                generation_mw=float(generation),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("skipping malformed WINDFOR row: %s (%s)", raw, exc)
            return None


async def stream_windows(
    client: ElexonClient,
    start: datetime,
    end: datetime,
) -> AsyncIterator[tuple[list[ActualRow], list[ForecastRow]]]:
    """Yield (actuals, forecasts) chunk by chunk so ingestion can checkpoint."""
    for window_start, window_end in _chunk_windows(start, end, client._settings.elexon_max_window_days):
        actuals = await client.fetch_actuals(window_start, window_end)
        forecasts = await client.fetch_forecasts(window_start, window_end)
        yield actuals, forecasts
