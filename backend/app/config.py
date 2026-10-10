"""Settings read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    mode: str = field(default_factory=lambda: _env("UAL_MODE", "demo"))
    start: datetime = field(
        default_factory=lambda: datetime.fromisoformat(_env("UAL_START", "2026-10-10T21:00")).replace(tzinfo=timezone.utc)
    )
    hours: int = field(default_factory=lambda: int(_env("UAL_HOURS", "12")))
    bbox: tuple[float, float, float, float] = field(
        default_factory=lambda: tuple(float(x) for x in _env("UAL_BBOX", "-82,26,14,68").split(","))  # type: ignore[return-value]
    )
    max_flights: int = field(default_factory=lambda: int(_env("UAL_MAX_FLIGHTS", "80")))

    opensky_client_id: str = field(default_factory=lambda: _env("OPENSKY_CLIENT_ID"))
    opensky_client_secret: str = field(default_factory=lambda: _env("OPENSKY_CLIENT_SECRET"))
    opensky_aircraft_db: Path = field(default_factory=lambda: Path(_env("OPENSKY_AIRCRAFT_DB", "data/aircraftDatabase.csv")))

    contrails_org_url: str = field(default_factory=lambda: _env("CONTRAILS_ORG_URL"))
    contrails_org_key: str = field(default_factory=lambda: _env("CONTRAILS_ORG_KEY"))

    cache_dir: Path = field(default_factory=lambda: Path(_env("UAL_CACHE_DIR", ".cache")))

    @property
    def live(self) -> bool:
        return self.mode == "live"


settings = Settings()
