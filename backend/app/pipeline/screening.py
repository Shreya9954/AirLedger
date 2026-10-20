"""Contrail screening model on forecast grids: where would a persistent contrail form?

Two physical tests at each waypoint:
  1. Schmidt-Appleman: the exhaust plume reaches water saturation, i.e. the air is colder than the
     threshold T_crit(p). We use the dry-air threshold (Schumann 1996, Meteorol. Z. 5, 4-23):
       G = EI_H2O * cp * p / (eps * Q * (1 - eta))
       T_crit[°C] = -46.46 + 9.43 ln(G - 0.053) + 0.72 ln(G - 0.053)^2
  2. Persistence: the ambient air is at or above ice saturation. Forecast RHi is capped at 100 % and
     NWP models under-forecast supersaturation, so RHi >= 95 % counts (pycontrails scales humidity
     for the same reason).

This is a SCREENING model, not CoCiP: it says where persistent contrails are likely, and attaches
an illustrative energy forcing per km (strong at night, weaker or negative in midday sun). The
warming numbers are estimates for ranking options, never measurements.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from ..sources.openmeteo import ModelGrid, fl_to_hpa
from .reroute import LevelResult

RHI_PERSIST = 0.95
EI_H2O, CP, EPS, Q_FUEL, ETA = 1.23, 1004.0, 0.622, 43.2e6, 0.3
EF_NIGHT, EF_DAY, EF_NOON = 1.6e11, 0.45e11, -0.3e11  # J per km of persistent contrail (illustrative)


def t_crit_c(p_hpa: float) -> float:
    g = EI_H2O * CP * p_hpa * 100 / (EPS * Q_FUEL * (1 - ETA))
    x = math.log(g - 0.053)
    return -46.46 + 9.43 * x + 0.72 * x * x


class Sampler:
    """Interpolates a ModelGrid: bilinear in lon/lat, linear in log-pressure, linear in time."""

    def __init__(self, g: ModelGrid, t0_unix: float):
        self.g = g
        self.hours = (g.times - t0_unix) / 3600.0
        self.lnp = np.log(np.asarray(g.levels_hpa, float))  # descending pressure

    def _w(self, axis: np.ndarray, x: float):
        if x <= axis[0]:
            return 0, 0, 0.0
        if x >= axis[-1]:
            n = len(axis) - 1
            return n, n, 0.0
        i = int(np.searchsorted(axis, x)) - 1
        return i, i + 1, (x - axis[i]) / (axis[i + 1] - axis[i])

    def _hl(self, arr, t, lat, lon):
        g = self.g
        t0, t1, ft = self._w(self.hours, t)
        y0, y1, fy = self._w(g.lats, lat)
        x0, x1, fx = self._w(g.lons, lon)

        def at(ti):
            a = arr[ti]
            top = a[..., y0, x0] * (1 - fx) + a[..., y0, x1] * fx
            bot = a[..., y1, x0] * (1 - fx) + a[..., y1, x1] * fx
            return top * (1 - fy) + bot * fy
        return at(t0) * (1 - ft) + at(t1) * ft

    def at(self, lon: float, lat: float, fl: float, t: float) -> tuple[float, float]:
        """(temperature °C, RHi 0..1) at a point."""
        T = self._hl(self.g.temp_c, t, lat, lon)
        R = self._hl(self.g.rhi, t, lat, lon)
        lp = math.log(fl_to_hpa(fl))
        # levels are in descending pressure; interpolate on -ln p (ascending with height)
        k0, k1, fk = self._w(-self.lnp, -lp)
        return float(T[k0] * (1 - fk) + T[k1] * fk), float(R[k0] * (1 - fk) + R[k1] * fk)

    def wind(self, lon: float, lat: float, t: float) -> tuple[float, float]:
        return float(self._hl(self.g.u250, t, lat, lon)), float(self._hl(self.g.v250, t, lat, lon))


def local_solar_hour(lon: float, t_unix: float) -> float:
    return ((t_unix / 3600.0) % 24 + lon / 15.0) % 24


def ef_per_km(lon: float, t_unix: float, rhi: float, type_factor: float = 1.0) -> float:
    h = local_solar_hour(lon, t_unix)
    base = EF_NIGHT if (h < 6 or h >= 18) else (EF_NOON if 10 <= h < 15 else EF_DAY)
    wet = min(1.0, max(0.0, (rhi - RHI_PERSIST) / (1 - RHI_PERSIST)))
    return base * (0.6 + 0.4 * wet) * type_factor


def persistent(T_c: float, rhi: float, fl: float) -> bool:
    return T_c < t_crit_c(fl_to_hpa(fl)) and rhi >= RHI_PERSIST


def evaluate_track(sampler: Sampler, pts: Sequence[tuple[float, float, float]], seg_km: Sequence[float],
                   fls: Sequence[float], t0_unix: float, c0: int, c1: int, type_factor: float = 1.0) -> LevelResult:
    """pts: (lon, lat, hours after t0); fls: flight level per waypoint. Cruise is c0..c1."""
    iss = [0] * len(pts)
    km = ef = 0.0
    for i in range(c0, min(c1, len(pts))):
        lon, lat, t = pts[i]
        T, R = sampler.at(lon, lat, fls[i], t)
        if persistent(T, R, fls[i]):
            iss[i] = 1
            km += seg_km[i]
            ef += seg_km[i] * ef_per_km(lon, t0_unix + t * 3600, R, type_factor)
    return LevelResult(iss, km, ef)
