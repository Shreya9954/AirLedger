"""Wind at cruise altitude for advecting flight tracks during attribution.

GridWind is a nearest-neighbour lookup on a lon/lat/time grid (fast enough for the thousands of
calls attribution makes); wind_from_met() builds one from the ERA5 data the scenario already loads.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

CRUISE_LEVEL_HPA = 250.0  # about FL340


class GridWind:
    def __init__(self, lons, lats, hours, u, v):
        """u, v: (lon, lat, time) arrays in m/s; hours: time axis in hours after scenario start."""
        self.lons = np.asarray(lons, float)
        self.lats = np.asarray(lats, float)
        self.hours = np.asarray(hours, float)
        self.u = np.asarray(u, float)
        self.v = np.asarray(v, float)

    @staticmethod
    def _nearest(axis: np.ndarray, x: float) -> int:
        i = int(np.searchsorted(axis, x))
        if i <= 0:
            return 0
        if i >= len(axis):
            return len(axis) - 1
        return i if axis[i] - x < x - axis[i - 1] else i - 1

    def __call__(self, lon: float, lat: float, t_hours: float) -> tuple[float, float]:
        i, j, k = self._nearest(self.lons, lon), self._nearest(self.lats, lat), self._nearest(self.hours, t_hours)
        return float(self.u[i, j, k]), float(self.v[i, j, k])


def wind_from_met(met, start: datetime, level_hpa: float = CRUISE_LEVEL_HPA) -> GridWind:
    """GridWind at the pressure level nearest level_hpa from a pycontrails MetDataset."""
    ds = met.data.sel(level=level_hpa, method="nearest")
    t0 = np.datetime64(start.replace(tzinfo=None))
    hours = (ds["time"].values - t0) / np.timedelta64(1, "h")
    lons, lats = ds["longitude"].values, ds["latitude"].values
    u = ds["eastward_wind"].transpose("longitude", "latitude", "time").values
    v = ds["northward_wind"].transpose("longitude", "latitude", "time").values
    lon_order, lat_order = np.argsort(lons), np.argsort(lats)
    return GridWind(lons[lon_order], lats[lat_order], hours, u[lon_order][:, lat_order], v[lon_order][:, lat_order])
