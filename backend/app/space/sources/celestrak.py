"""CelesTrak: the satellite catalogue (SATCAT, with decay dates) and orbital elements (GP data, as OMM JSON).

Catalogue numbers passed 99999 in July 2026 and new objects have no TLE, so orbits are read as OMM.
"""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass
from datetime import date

from ..cache import Cache

SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
TTL_SATCAT = 12 * 3600  # updated by hand once or twice a day
TTL_GP = 2 * 3600       # GP data updates every 2 hours

MU_KM3_S2 = 398600.4418
R_EARTH_KM = 6378.137


@dataclass(frozen=True)
class SatcatRow:
    norad: int
    cospar: str
    name: str
    type: str                  # PAY | R/B | DEB | UNK
    owner: str                 # CelesTrak owner code (country or organisation)
    launch_date: date | None
    decay_date: date | None
    inclination_deg: float | None
    apogee_km: float | None
    perigee_km: float | None
    orbit_type: str = "ORB"    # ORB in orbit | IMP re-entered/impacted | LAN landed | DOC docked | R/T round trip


def parse_satcat(text: str) -> list[SatcatRow]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        rows.append(SatcatRow(
            norad=int(r["NORAD_CAT_ID"]),
            cospar=r["OBJECT_ID"].strip(),
            name=r["OBJECT_NAME"].strip(),
            type=r["OBJECT_TYPE"].strip(),
            owner=r["OWNER"].strip(),
            launch_date=_date(r["LAUNCH_DATE"]),
            decay_date=_date(r["DECAY_DATE"]),
            inclination_deg=_float(r["INCLINATION"]),
            apogee_km=_float(r["APOGEE"]),
            perigee_km=_float(r["PERIGEE"]),
            orbit_type=r.get("ORBIT_TYPE", "").strip() or "ORB",
        ))
    return rows


def parse_gp(data: bytes) -> list[dict]:
    """OMM records as published. CelesTrak answers an unknown query with plain text, not JSON."""
    try:
        records = json.loads(data)
    except ValueError as exc:
        raise ValueError(f"GP response is not JSON: {data[:120]!r}") from exc
    if not isinstance(records, list):
        raise ValueError("GP response is not a list of OMM records")
    return records


def omm_perigee_apogee(omm: dict) -> tuple[float, float]:
    """Perigee and apogee altitude (km) from the mean motion (rev/day) and eccentricity."""
    n = float(omm["MEAN_MOTION"]) * 2 * math.pi / 86400
    a = (MU_KM3_S2 / n ** 2) ** (1 / 3)
    e = float(omm["ECCENTRICITY"])
    return a * (1 - e) - R_EARTH_KM, a * (1 + e) - R_EARTH_KM


class CelestrakClient:
    def __init__(self, cache: Cache):
        self.cache = cache

    def satcat(self) -> list[SatcatRow]:
        return parse_satcat(self.cache.get("celestrak_satcat", SATCAT_URL, TTL_SATCAT).decode("utf-8"))

    def gp(self, *, group: str | None = None, special: str | None = None) -> list[dict]:
        if (group is None) == (special is None):
            raise ValueError("pass exactly one of group or special")
        params = {"GROUP": group} if group else {"SPECIAL": special}
        params["FORMAT"] = "json"
        key = f"celestrak_gp_{(group or special).lower()}"
        return parse_gp(self.cache.get(key, GP_URL, TTL_GP, params=params))


def _date(s: str) -> date | None:
    s = s.strip()
    return date.fromisoformat(s[:10]) if s else None


def _float(s: str) -> float | None:
    s = s.strip()
    return float(s) if s else None
