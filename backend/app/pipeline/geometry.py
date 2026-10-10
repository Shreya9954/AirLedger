"""Small geodesy helpers shared by the pipeline."""
from __future__ import annotations

import math

EARTH_R_KM = 6371.0


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance between (lon, lat) points in km."""
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(h))


def to_local_km(points, lat0: float) -> list[tuple[float, float]]:
    """Equirectangular projection to km around latitude lat0; fine over a few hundred km."""
    k = 111.32
    c = math.cos(math.radians(lat0))
    return [(lon * k * c, lat * k) for lon, lat in points]


def point_segment_km(p, a, b) -> float:
    """Distance from p to segment ab, all in local km coordinates."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def resample(values: list[float], times: list[float], n: int) -> list[float]:
    """Linear resample of values(times) onto n evenly spaced times."""
    t0, t1 = times[0], times[-1]
    out, j = [], 0
    for i in range(n):
        t = t0 + (t1 - t0) * i / (n - 1)
        while j < len(times) - 2 and times[j + 1] < t:
            j += 1
        span = times[j + 1] - times[j] or 1.0
        f = (t - times[j]) / span
        out.append(values[j] + (values[j + 1] - values[j]) * f)
    return out
