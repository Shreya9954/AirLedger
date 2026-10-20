"""Upper-air forecasts from Open-Meteo (https://open-meteo.com): no API key, two models.

We fetch ECMWF IFS (0.25°) and NOAA GFS on a regular lon/lat grid at the three cruise pressure
levels both models share: 300 hPa (about FL300), 250 hPa (FL340) and 200 hPa (FL390), hourly.

Humidity: at these temperatures (below about -23 °C) the models' relative humidity is reported
with respect to ICE (mixed-phase convention), capped at 100 %. We checked this on the data itself:
at T < -45 °C a third of values exceed 70 % and many reach 100 %, which is impossible for humidity
over water (ice saturation is only ~60 % over water at -50 °C). So reported RH is used as RHi.
Open-Meteo data is CC BY 4.0.
"""
from __future__ import annotations

import json
import math
import time as _time
from dataclasses import dataclass

import httpx
import numpy as np

URL = "https://api.open-meteo.com/v1/forecast"
LEVELS_HPA = (300, 250, 200)
MODELS = {"ecmwf": "ecmwf_ifs025", "gfs": "gfs_seamless"}
CHUNK = 40  # locations per request (bigger batches time out)


@dataclass
class ModelGrid:
    """One model on a lon/lat/level/time grid. Arrays are (time, level, lat, lon)."""
    name: str
    lons: np.ndarray
    lats: np.ndarray
    levels_hpa: tuple
    times: np.ndarray        # unix seconds, hourly
    temp_c: np.ndarray
    rhi: np.ndarray          # 0..1, relative humidity over ice as reported (capped at 1)
    u250: np.ndarray         # (time, lat, lon) m/s
    v250: np.ndarray


def _wind_uv(speed, direction_deg):
    """Meteorological direction (where the wind comes FROM) -> eastward u, northward v."""
    d = np.radians(direction_deg)
    return -speed * np.sin(d), -speed * np.cos(d)


def _get(http: httpx.Client, params: dict) -> list:
    for attempt in range(3):
        try:
            r = http.get(URL, params=params)
            r.raise_for_status()
            body = r.json()
            return body if isinstance(body, list) else [body]
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError, ValueError) as exc:  # ValueError: cut-off JSON
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 0
            if attempt == 2 or (status and status < 500 and status != 429):
                raise
            _time.sleep(65 if status == 429 else 5 * (attempt + 1))  # 429: the per-minute quota resets in a minute
    raise RuntimeError("unreachable")


def fetch_grid(bbox, step_deg: float, past_days: int = 1, forecast_days: int = 1,
               client: httpx.Client | None = None, cache_dir=None) -> dict[str, ModelGrid]:
    lon_min, lat_min, lon_max, lat_max = bbox
    lons = np.arange(lon_min, lon_max + 1e-9, step_deg)
    lats = np.arange(lat_min, lat_max + 1e-9, step_deg)
    pts = [(la, lo) for la in lats for lo in lons]
    hourly = [f"{v}_{p}hPa" for p in LEVELS_HPA for v in ("temperature", "relative_humidity")]
    hourly += ["wind_speed_250hPa", "wind_direction_250hPa"]
    http = client or httpx.Client(timeout=180)
    rows: list[dict] = []
    for k in range(0, len(pts), CHUNK):
        part = pts[k:k + CHUNK]
        cached = cache_dir / f"openmeteo_{step_deg}_{k}.json" if cache_dir else None
        if cached and cached.exists():
            rows += json.loads(cached.read_text())
            continue
        params = {
            "latitude": ",".join(f"{la:.2f}" for la, _ in part), "longitude": ",".join(f"{lo:.2f}" for _, lo in part),
            "hourly": ",".join(hourly), "models": ",".join(MODELS.values()), "wind_speed_unit": "ms",
            "past_days": past_days, "forecast_days": forecast_days, "timeformat": "unixtime", "timezone": "GMT",
        }
        got = _get(http, params)
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(got))
        rows += got
        _time.sleep(13)  # free tier: ~600 weighted calls a minute; a 40-location request weighs ~100+
    times = np.asarray(rows[0]["hourly"]["time"], float)
    nt, nl, ny, nx = len(times), len(LEVELS_HPA), len(lats), len(lons)
    out = {}
    for short, model in MODELS.items():
        T = np.full((nt, nl, ny, nx), np.nan)
        H = np.full((nt, nl, ny, nx), np.nan)
        U = np.full((nt, ny, nx), np.nan)
        V = np.full((nt, ny, nx), np.nan)
        for idx, row in enumerate(rows):
            j, i = divmod(idx, nx)
            h = row["hourly"]
            for li, p in enumerate(LEVELS_HPA):
                T[:, li, j, i] = np.asarray(h[f"temperature_{p}hPa_{model}"], float)
                H[:, li, j, i] = np.asarray(h[f"relative_humidity_{p}hPa_{model}"], float) / 100.0
            u, v = _wind_uv(np.asarray(h[f"wind_speed_250hPa_{model}"], float), np.asarray(h[f"wind_direction_250hPa_{model}"], float))
            U[:, j, i], V[:, j, i] = u, v
        out[short] = ModelGrid(short, lons, lats, LEVELS_HPA, times, T, np.clip(H, 0, 1), U, V)
    return out


# ISA: pressure (hPa) <-> flight level (hundreds of ft), troposphere and lower stratosphere
def fl_to_hpa(fl: float) -> float:
    h = fl * 100 * 0.3048
    if h <= 11000:
        return 1013.25 * (1 - 2.25577e-5 * h) ** 5.25588
    return 226.32 * math.exp(-(h - 11000) / 6341.62)


def hpa_to_fl(p: float) -> float:
    if p >= 226.32:
        h = (1 - (p / 1013.25) ** (1 / 5.25588)) / 2.25577e-5
    else:
        h = 11000 - 6341.62 * math.log(p / 226.32)
    return h / 0.3048 / 100
