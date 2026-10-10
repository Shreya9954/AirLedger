"""Match observed contrails to the aircraft that made them ("waycasting").

Each candidate flight's track is advected with the wind for the contrail's age, then compared to
the observed contrail line. The flight whose advected track lies closest, on average, wins.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

from .geometry import point_segment_km, to_local_km

Wind = Callable[[float, float, float], tuple[float, float]]  # (lon, lat, t_hours) -> (u, v) in m/s


@dataclass
class Match:
    contrail_id: str
    flight_id: str | int
    offset_km: float
    confidence: float


def advect(track: Sequence[tuple[float, float, float]], at_hours: float, wind: Wind) -> list[tuple[float, float]]:
    """Move each waypoint (lon, lat, t) downwind from when it was flown to at_hours."""
    out = []
    for lon, lat, t in track:
        age_s = (at_hours - t) * 3600
        if age_s < 0:
            continue
        u, v = wind(lon, lat, t)
        dlat = v * age_s / 111_320
        dlon = u * age_s / (111_320 * math.cos(math.radians(lat)))
        out.append((lon + dlon, lat + dlat))
    return out


def mean_offset_km(line: Sequence[tuple[float, float]], track: Sequence[tuple[float, float]]) -> float:
    if len(track) < 2 or not line:
        return math.inf
    lat0 = line[0][1]
    L, T = to_local_km(line, lat0), to_local_km(track, lat0)
    return sum(min(point_segment_km(p, T[i], T[i + 1]) for i in range(len(T) - 1)) for p in L) / len(L)


def attribute(contrail_id: str, line: Sequence[tuple[float, float]], observed_h: float,
              flights: dict, wind: Wind, max_km: float = 20.0, scale_km: float = 10.0) -> Match | None:
    """flights: id -> list of (lon, lat, t_hours). Returns the best match within max_km, or None."""
    best_id, best_d = None, math.inf
    for fid, track in flights.items():
        d = mean_offset_km(line, advect(track, observed_h, wind))
        if d < best_d:
            best_id, best_d = fid, d
    if best_id is None or best_d > max_km:
        return None
    return Match(contrail_id, best_id, best_d, math.exp(-best_d / scale_km))
