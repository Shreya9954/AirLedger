"""OpenSky Network: aircraft positions, tracks and departure/arrival estimates.

Uses the REST API with OAuth2 client credentials. Historical tracks are limited to recent days
on the REST API; for older nights use the OpenSky Trino/Impala history database instead.
Docs: https://openskynetwork.github.io/opensky-api/rest.html
"""
from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

API = "https://opensky-network.org/api"
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"


@dataclass
class TrackPoint:
    time: int          # unix seconds
    lat: float
    lon: float
    baro_alt_m: float | None
    on_ground: bool


@dataclass
class Aircraft:
    icao24: str
    callsign: str
    type_code: str
    operator_icao: str
    origin: str
    destination: str
    track: list[TrackPoint]


class OpenSkyClient:
    def __init__(self, client_id: str, client_secret: str, timeout: float = 30.0):
        self._id, self._secret = client_id, client_secret
        self._token: str | None = None
        self._token_exp = 0.0
        self._http = httpx.Client(timeout=timeout)

    def _auth(self) -> dict[str, str]:
        if not self._id:
            return {}  # anonymous: lower rate limits, no history
        if not self._token or time.time() > self._token_exp - 60:
            r = self._http.post(TOKEN_URL, data={
                "grant_type": "client_credentials", "client_id": self._id, "client_secret": self._secret,
            })
            r.raise_for_status()
            body = r.json()
            self._token, self._token_exp = body["access_token"], time.time() + body.get("expires_in", 1800)
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path: str, **params) -> dict | list | None:
        r = self._http.get(API + path, params=params, headers=self._auth())
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def states(self, bbox: tuple[float, float, float, float], at: int | None = None) -> list[list]:
        """State vectors inside bbox (lon_min, lat_min, lon_max, lat_max) at unix time `at`."""
        lon_min, lat_min, lon_max, lat_max = bbox
        params = {"lamin": lat_min, "lomin": lon_min, "lamax": lat_max, "lomax": lon_max}
        if at:
            params["time"] = at
        body = self._get("/states/all", **params) or {}
        return body.get("states") or []

    def track(self, icao24: str, at: int) -> list[TrackPoint]:
        """Waypoints of the flight that icao24 was flying at unix time `at`."""
        body = self._get("/tracks/all", icao24=icao24, time=at) or {}
        return [TrackPoint(int(p[0]), p[1], p[2], p[3], bool(p[5])) for p in body.get("path") or []]

    def flight_info(self, icao24: str, begin: int, end: int) -> dict | None:
        """Estimated departure and arrival airports (ICAO codes) for an aircraft in a time window."""
        rows = self._get("/flights/aircraft", icao24=icao24, begin=begin, end=end) or []
        return rows[-1] if rows else None


class AircraftDatabase:
    """icao24 -> (type code, operator ICAO) from OpenSky's aircraft metadata CSV."""

    def __init__(self, path: Path):
        self._rows: dict[str, tuple[str, str]] = {}
        if path.exists():
            with path.open(newline="", encoding="utf-8", errors="replace") as fh:
                for row in csv.DictReader(fh):
                    self._rows[row.get("icao24", "").lower()] = (row.get("typecode", ""), row.get("operatoricao", ""))

    def lookup(self, icao24: str) -> tuple[str, str]:
        return self._rows.get(icao24.lower(), ("", ""))


def cruising_aircraft(client: OpenSkyClient, db: AircraftDatabase, bbox, at: int, limit: int,
                      min_alt_m: float = 8500) -> list[Aircraft]:
    """Aircraft above ~FL280 inside bbox at time `at`, with full tracks and metadata."""
    out: list[Aircraft] = []
    for s in client.states(bbox, at):
        icao24, callsign, baro_alt, on_ground = s[0], (s[1] or "").strip(), s[7], s[8]
        if on_ground or baro_alt is None or baro_alt < min_alt_m:
            continue
        track = client.track(icao24, at)
        if len(track) < 10:
            continue
        type_code, operator = db.lookup(icao24)
        info = client.flight_info(icao24, track[0].time, track[-1].time) or {}
        out.append(Aircraft(
            icao24=icao24, callsign=callsign, type_code=type_code or "UNKN",
            operator_icao=operator or callsign[:3],
            origin=info.get("estDepartureAirport") or "—", destination=info.get("estArrivalAirport") or "—",
            track=track,
        ))
        if len(out) >= limit:
            break
    return out
