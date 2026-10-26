"""Application configuration.

All runtime knobs are environment driven so the same image can run locally,
in docker-compose, and in a container host without code changes.
"""

from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locally this file lives at <repo>/backend/app/config.py; inside the Docker
# image and the Vercel Python service the backend directory is the root.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
_ON_VERCEL = bool(os.environ.get("VERCEL"))
_DEFAULT_DATA_DIR = Path("/tmp") if _ON_VERCEL else _BACKEND_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GRIDBRICK_",
        env_file=(_REPO_ROOT / ".env", Path(".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "GridBrick Forecast Desk"
    version: str = "1.0.0"
    environment: str = "production" if _ON_VERCEL else "development"

    # --- storage -------------------------------------------------------
    # Default lives next to the backend package so `uvicorn` from any cwd works.
    # Serverless platforms only allow writes under /tmp.
    database_url: str = f"sqlite:///{(_DEFAULT_DATA_DIR / 'gridbrick.db').as_posix()}"

    # --- external data -------------------------------------------------
    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    elexon_timeout_seconds: float = 30.0
    elexon_max_retries: int = 3
    # The BMRS range endpoints reject windows wider than 7 days.
    elexon_max_window_days: int = 7

    # --- pilot scope ---------------------------------------------------
    pilot_start: date = date(2026, 1, 1)
    pilot_end: date = date(2026, 1, 31)
    # Ingest a buffer either side so that (a) the first delivery day already
    # has a residual history for its uncertainty bands and (b) late-January
    # delivery days have realised actuals before the pilot window closes.
    ingest_lookback_days: int = 12
    ingest_lookahead_days: int = 2

    # --- market assumptions --------------------------------------------
    # Default decision cutoff: 09:30 Europe/London on D-1, i.e. immediately
    # after the GB day-ahead auction gate closure.
    default_cutoff_hour: int = 9
    default_cutoff_minute: int = 30
    # Rolling window (days) of realised decision-relevant errors used to
    # estimate predictive quantiles. Every band is walk-forward: only data
    # publishable before the cutoff is ever used.
    band_lookback_days: int = 14
    band_min_days: int = 5
    # Conformal widening factor for predictive bands. Empirically derived from
    # walk-forward under-coverage on the pilot window (see README "Calibration"):
    # forecast error is clustered in weather regimes, so a trailing window of
    # quantiles is systematically slightly too narrow out of sample.
    band_inflation: float = 1.15
    # Treat a vintage stamped exactly at the cutoff as not yet available.
    strict_cutoff: bool = True

    # --- seeding / boot ------------------------------------------------
    seed_dir: Path = _BACKEND_ROOT / "seeds"
    auto_ingest_on_empty: bool = True
    allow_live_ingest: bool = True
    admin_token: str | None = None

    cors_origins: str = (
        "http://localhost:5173,http://localhost:4173,http://localhost:8080,"
        "http://localhost:3000"
    )

    @field_validator("seed_dir", mode="after")
    @classmethod
    def _resolve_seed_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (_REPO_ROOT / value).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def ingest_start(self) -> date:
        from datetime import timedelta

        return self.pilot_start - timedelta(days=self.ingest_lookback_days)

    @property
    def ingest_end(self) -> date:
        from datetime import timedelta

        return self.pilot_end + timedelta(days=self.ingest_lookahead_days)


@lru_cache
def get_settings() -> Settings:
    return Settings()
