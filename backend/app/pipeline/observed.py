"""Attribute observed (satellite-detected) contrails to the flights in a scenario.

For each detection, only waypoints flown in the MAX_AGE_H hours before it are candidates (older
contrails have usually spread or dissipated), and flights whose recent track is nowhere near the
detection are skipped before the per-point matching in attribution.py.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from .attribution import Wind, advect, attribute

MAX_AGE_H = 3.0
NEAR_DEG = 8.0  # recent track must come this close (degrees) to the detection to be considered


def _near(track: Sequence[tuple[float, float, float]], line: Sequence[tuple[float, float]]) -> bool:
    lons, lats = [p[0] for p in line], [p[1] for p in line]
    lo0, lo1, la0, la1 = min(lons) - NEAR_DEG, max(lons) + NEAR_DEG, min(lats) - NEAR_DEG / 2, max(lats) + NEAR_DEG / 2
    return any(lo0 <= lon <= lo1 and la0 <= lat <= la1 for lon, lat, _ in track)


def _matched_age_h(track, line, obs_h: float, wind: Wind) -> float:
    """Age of the contrail at the detection's midpoint: when the waypoint that drifted there was flown."""
    mid = line[len(line) // 2]
    moved = advect(track, obs_h, wind)  # same order and length as track: every point is in the past
    i = min(range(len(moved)), key=lambda k: (moved[k][0] - mid[0]) ** 2 + (moved[k][1] - mid[1]) ** 2)
    return obs_h - track[i][2]


def attribute_observations(observations: Iterable[tuple[str, float, Sequence[tuple[float, float]]]],
                           tracks: dict, wind: Wind, max_age_h: float = MAX_AGE_H) -> dict:
    """observations: (id, observed hours after start, line). tracks: flight id -> [(lon, lat, t_hours)].
    Returns flight id -> best match {id, offset_km, confidence, age_min, observed_h, n_matched}."""
    best: dict = {}
    for obs_id, obs_h, line in observations:
        recent = {}
        for fid, track in tracks.items():
            pts = [p for p in track if 0.0 <= obs_h - p[2] <= max_age_h]
            if len(pts) >= 2 and _near(pts, line):
                recent[fid] = pts
        if not recent:
            continue
        m = attribute(obs_id, line, obs_h, recent, wind)
        if m is None:
            continue
        age_min = 60.0 * _matched_age_h(recent[m.flight_id], line, obs_h, wind)
        prev = best.get(m.flight_id)
        n = (prev["n_matched"] if prev else 0) + 1
        if prev is None or m.confidence > prev["confidence"]:
            best[m.flight_id] = {"id": obs_id, "offset_km": round(m.offset_km, 2), "confidence": round(m.confidence, 3),
                                 "age_min": round(age_min), "observed_h": round(obs_h, 3), "n_matched": n}
        else:
            prev["n_matched"] = n
    return best
