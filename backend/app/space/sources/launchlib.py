"""Launch Library 2 (The Space Devs): past and upcoming orbital launches.

Anonymous use is limited to 15 requests an hour, so pages are cached for 6 hours. Detailed mode is
needed because only it carries the rocket configuration's liftoff mass. For development, set
LL2_BASE_URL=https://lldev.thespacedevs.com/2.3.0 (current data, looser limits).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from ..cache import Cache
from ..records import LaunchRecord

log = logging.getLogger(__name__)

DEFAULT_BASE = "https://ll.thespacedevs.com/2.3.0"
TTL = 6 * 3600
PAGE = 100
STATUS = {"Success": "success", "Failure": "failure", "Partial Failure": "partial"}
FINAL = set(STATUS)


def parse_launch(r: dict) -> LaunchRecord | None:
    """One LL2 launch; None for a launch that has flown but has no final outcome yet (in flight)."""
    abbrev = (r.get("status") or {}).get("abbrev", "")
    net = _dt(r["net"])
    if abbrev in FINAL:
        status = STATUS[abbrev]
    elif abbrev == "In Flight":
        return None
    else:
        status = "upcoming"
    provider = r.get("launch_service_provider") or {}
    countries = provider.get("country") or []
    config = (r.get("rocket") or {}).get("configuration") or {}
    pad = r.get("pad") or {}
    mass_t = config.get("launch_mass")
    return LaunchRecord(
        id=f"ll2:{r['id']}",
        name=r.get("name", ""),
        net=net,
        status=status,
        provider=provider.get("name") or "Unknown",
        country=countries[0].get("alpha_3_code") if countries and isinstance(countries[0], dict) else None,
        vehicle=config.get("full_name") or config.get("name") or "Unknown",
        vehicle_families=tuple(f["name"] for f in config.get("families") or [] if f.get("name")),
        orbit=((r.get("mission") or {}).get("orbit") or {}).get("abbrev"),
        pad_name=pad.get("name"),
        pad_location=(pad.get("location") or {}).get("name"),
        pad_lat=_float(pad.get("latitude")),
        pad_lon=_float(pad.get("longitude")),
        liftoff_mass_kg=float(mass_t) * 1000 if mass_t else None,
    )


class LaunchLibClient:
    def __init__(self, cache: Cache, base: str | None = None):
        self.cache = cache
        self.base = (base or os.environ.get("LL2_BASE_URL") or DEFAULT_BASE).rstrip("/")

    def previous(self, since: datetime, max_pages: int = 5) -> list[LaunchRecord]:
        """Launches with NET on or after `since`, newest first."""
        params = {"net__gte": _iso(since), "limit": PAGE, "mode": "detailed", "ordering": "-net"}
        return self._pages(f"ll2_previous_{since:%Y%m%d}", "launches/previous/", params, max_pages)

    def upcoming(self, until: datetime, max_pages: int = 1) -> list[LaunchRecord]:
        """Launches with NET up to `until`, soonest first."""
        params = {"net__lte": _iso(until), "limit": PAGE, "mode": "detailed", "ordering": "net"}
        return self._pages(f"ll2_upcoming_{until:%Y%m%d}", "launches/upcoming/", params, max_pages)

    def _pages(self, key: str, path: str, params: dict, max_pages: int) -> list[LaunchRecord]:
        out: list[LaunchRecord] = []
        for page in range(max_pages):
            body = json.loads(self.cache.get(f"{key}_p{page}", f"{self.base}/{path}",
                                              TTL, params=dict(params, offset=page * PAGE)))
            for r in body.get("results", []):
                rec = parse_launch(r)
                if rec is not None:
                    out.append(rec)
            if not body.get("next"):
                break
        else:
            log.warning("LL2 %s: stopped after %d pages; older launches omitted", path, max_pages)
        return out


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _float(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
