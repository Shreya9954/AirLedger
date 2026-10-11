"""Contrails.org observations: contrail line segments detected in GOES-East satellite imagery.

Endpoint: GET {base}/v1/observations/contrails-org/goes/L2/segments?time=YYYY-MM-DDTHH:MM:00
(10-minute steps). Each item is {"timestamp": ISO time, "geometry": "LINESTRING (lon lat, ...)"}.
Requests need an API key in the x-api-key header (ask api@contrails.org).
Docs: https://apidocs.contrails.org/observations.html. The provider marks these endpoints
experimental and not a complete dataset, so a missing time step is treated as "no detections".

Segments carry no id or flight; matching them to aircraft is done here, in pipeline/observed.py.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

DEFAULT_URL = "https://api.contrails.org"
SEGMENTS_PATH = "/v1/observations/contrails-org/goes/L2/segments"
_POINT = re.compile(r"(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s+(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")


@dataclass
class ObservedContrail:
    id: str
    observed_at: datetime
    line: list[tuple[float, float]]  # (lon, lat) vertices


def parse_linestring(wkt: str) -> list[tuple[float, float]]:
    """(lon, lat) vertices of a WKT LINESTRING. Extra Z/M values are ignored."""
    if not wkt.strip().upper().startswith("LINESTRING"):
        raise ValueError(f"expected a WKT LINESTRING, got {wkt[:40]!r}")
    body = wkt[wkt.index("(") + 1 : wkt.rindex(")")]
    points = []
    for vertex in body.split(","):
        m = _POINT.search(vertex)
        if m:
            points.append((float(m.group(1)), float(m.group(2))))
    return points


def floor_10min(t: datetime) -> datetime:
    return t.replace(minute=t.minute - t.minute % 10, second=0, microsecond=0)


def _in_bbox(line: list[tuple[float, float]], bbox: tuple[float, float, float, float]) -> bool:
    lon_min, lat_min, lon_max, lat_max = bbox
    return any(lon_min <= lon <= lon_max and lat_min <= lat <= lat_max for lon, lat in line)


class ContrailsOrgClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_URL, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise ValueError("CONTRAILS_ORG_KEY is not set")
        self._http = httpx.Client(base_url=(base_url or DEFAULT_URL).rstrip("/"), headers={"x-api-key": api_key},
                                  timeout=timeout, transport=transport)

    def segments(self, at: datetime) -> list[ObservedContrail]:
        """Detected contrail segments in the GOES image nearest below `at` (10-minute steps)."""
        t = floor_10min(at.astimezone(timezone.utc).replace(tzinfo=None) if at.tzinfo else at)
        r = self._http.get(SEGMENTS_PATH, params={"time": t.strftime("%Y-%m-%dT%H:%M:%S")})
        if r.status_code == 404:
            return []
        r.raise_for_status()
        out = []
        for k, item in enumerate(r.json()):
            line = parse_linestring(item["geometry"])
            if len(line) < 2:
                continue
            observed = datetime.fromisoformat(item.get("timestamp") or t.isoformat()).replace(tzinfo=timezone.utc)
            out.append(ObservedContrail(id=f"GOES-{t:%Y%m%dT%H%M}-{k}", observed_at=observed, line=line))
        return out

    def segments_between(self, start: datetime, end: datetime, bbox: tuple[float, float, float, float],
                         step_min: int = 30) -> list[ObservedContrail]:
        """Segments inside bbox from every `step_min` minutes of the window. A failed time step is
        logged and skipped so one bad request does not lose the whole night."""
        out: list[ObservedContrail] = []
        t = floor_10min(start)
        while t <= end:
            try:
                out += [c for c in self.segments(t) if _in_bbox(c.line, bbox)]
            except httpx.HTTPError as exc:
                log.warning("Contrails.org segments at %s failed: %s", t, exc)
            t += timedelta(minutes=step_min)
        return out
