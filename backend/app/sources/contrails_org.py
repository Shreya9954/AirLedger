"""Contrails.org observations: detected contrails, their geometry and persistence.

NOTE: the endpoint path and response fields below are placeholders. Confirm them against the
Contrails.org API documentation and adjust `_parse` before relying on this client.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx


@dataclass
class ObservedContrail:
    id: str
    observed_at: datetime
    line: list[tuple[float, float]]   # (lon, lat) vertices
    persistent: bool
    flight_id: str | None = None      # attribution supplied by the API, when available


class ContrailsOrgClient:
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 30.0):
        if not base_url:
            raise ValueError("CONTRAILS_ORG_URL is not set")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)

    def contrails(self, bbox: tuple[float, float, float, float], start: datetime, end: datetime) -> list[ObservedContrail]:
        r = self._http.get("/contrails", params={  # placeholder path
            "bbox": ",".join(map(str, bbox)), "start": start.isoformat(), "end": end.isoformat(),
        })
        r.raise_for_status()
        return [self._parse(item) for item in r.json().get("features", [])]

    @staticmethod
    def _parse(feature: dict) -> ObservedContrail:
        props = feature.get("properties", {})
        return ObservedContrail(
            id=str(feature.get("id") or props.get("id")),
            observed_at=datetime.fromisoformat(props["time"].replace("Z", "+00:00")),
            line=[(float(x), float(y)) for x, y, *_ in feature["geometry"]["coordinates"]],
            persistent=bool(props.get("persistent", True)),
            flight_id=props.get("flight_id"),
        )
