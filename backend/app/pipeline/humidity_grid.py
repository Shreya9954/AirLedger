"""Relative humidity over ice on a lon/lat/level/time grid, for the map's ISSR layer.

Output matches what frontend/js/data.js gridAtmosphere() expects: values flattened in
[time][level][lat][lon] order, levels as flight levels, time in hours after scenario start.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np


def build_grid(met, start: datetime, hours: int, bbox, step_deg: float = 1.0) -> dict:
    from pycontrails.physics import thermo, units

    lon_min, lat_min, lon_max, lat_max = bbox
    lons = np.arange(lon_min, lon_max + 1e-9, step_deg)
    lats = np.arange(lat_min, lat_max + 1e-9, step_deg)

    ds = met.data
    q, T = ds["specific_humidity"], ds["air_temperature"]
    levels_hpa = ds["level"].values
    times = ds["time"].values
    t0 = np.datetime64(start.replace(tzinfo=None))
    hours_axis = (times - t0) / np.timedelta64(1, "h")
    keep = (hours_axis >= 0) & (hours_axis <= hours)

    q = q.sel(longitude=lons, latitude=lats, method="nearest").isel(time=keep)
    T = T.sel(longitude=lons, latitude=lats, method="nearest").isel(time=keep)
    p = (levels_hpa * 100.0)[None, None, None, :]  # Pa, broadcast on (lon, lat, time, level) after transpose

    q_v = q.transpose("longitude", "latitude", "time", "level").values
    T_v = T.transpose("longitude", "latitude", "time", "level").values
    rhi = thermo.rhi(q_v, T_v, p)  # (lon, lat, time, level)

    # Reorder to [time][level][lat][lon], with levels sorted by flight level ascending.
    fls = np.round(units.pl_to_ft(levels_hpa) / 100).astype(int)
    order = np.argsort(fls)
    rhi = np.transpose(rhi, (2, 3, 1, 0))[:, order, :, :]
    kept_hours = hours_axis[keep]
    dt = float(kept_hours[1] - kept_hours[0]) if len(kept_hours) > 1 else 1.0

    return {
        "lon0": float(lons[0]), "dlon": step_deg, "nlon": len(lons),
        "lat0": float(lats[0]), "dlat": step_deg, "nlat": len(lats),
        "levels": fls[order].tolist(),
        "t0": float(kept_hours[0]), "dt": dt, "nt": int(len(kept_hours)),
        "values": np.round(np.nan_to_num(rhi), 3).ravel().tolist(),
        "wind": 1.2,  # display-only contrail drift, degrees lon per hour
    }
