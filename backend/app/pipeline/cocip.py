"""Run the pycontrails Contrail Cirrus Prediction model (CoCiP) on one flight at a chosen level.

Requires `pip install pycontrails[ecmwf]`. Imports are local so the rest of the backend and
its tests run without the science stack.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from ..constants import CRUISE_END, CRUISE_START
from .reroute import LevelResult

FT_PER_FL = 100
M_PER_FT = 0.3048


def _cocip(met, rad):
    from pycontrails.models.cocip import Cocip
    from pycontrails.models.humidity_scaling import ExponentialBoostHumidityScaling
    from pycontrails.models.ps_model import PSFlight

    return Cocip(met=met, rad=rad, params={
        "humidity_scaling": ExponentialBoostHumidityScaling(),
        "aircraft_performance": PSFlight(),
        "max_age": np.timedelta64(12, "h"),
    })


def make_flight(flight_id: str, type_code: str, lons, lats, times: list[datetime], fl_per_point):
    from pycontrails import Flight

    return Flight(
        longitude=np.asarray(lons, float),
        latitude=np.asarray(lats, float),
        altitude=np.asarray(fl_per_point, float) * FT_PER_FL * M_PER_FT,
        time=np.asarray([t.replace(tzinfo=None) for t in times], dtype="datetime64[ns]"),
        flight_id=flight_id,
        aircraft_type=type_code,
    )


def evaluate(met, rad, flight_id: str, type_code: str, lons, lats, times, fl_per_point) -> tuple[LevelResult, float]:
    """Contrail result for the cruise waypoints, plus total fuel burned (t) from the PS model."""
    flight = make_flight(flight_id, type_code, lons, lats, times, fl_per_point)
    out = _cocip(met, rad).eval(source=flight)

    ef = np.nan_to_num(np.asarray(out["ef"], float))
    seg_km = np.nan_to_num(np.asarray(flight.segment_length(), float)) / 1000
    persistent = (ef != 0).astype(int)
    persistent[:CRUISE_START] = 0
    persistent[CRUISE_END:] = 0

    fuel_t = 0.0
    if "fuel_flow" in out:
        dt_s = np.nan_to_num(np.asarray(flight.segment_duration(), float))
        fuel_t = float(np.nansum(np.asarray(out["fuel_flow"], float) * dt_s) / 1000)

    return LevelResult(
        issr=persistent.tolist(),
        km=float((seg_km * persistent).sum()),
        ef=float((ef * persistent).sum()),
    ), fuel_t


def hours_to_datetimes(start: datetime, hours) -> list[datetime]:
    return [start + timedelta(hours=float(h)) for h in hours]
