"""Copernicus ERA5 met data through pycontrails' ERA5 datalib.

Needs a Copernicus Climate Data Store account (CDSAPI_URL / CDSAPI_KEY or ~/.cdsapirc).
ERA5 is a reanalysis and lags real time by about five days; use ECMWF HRES (pycontrails HRES
datalib) for forecasts of tonight.
"""
from __future__ import annotations

from datetime import datetime

# Cruise-altitude pressure levels: roughly FL390, FL360, FL340, FL300.
PRESSURE_LEVELS = [200, 225, 250, 300]


def load_met(start: datetime, end: datetime, pressure_levels=PRESSURE_LEVELS):
    """Pressure-level met (temperature, humidity, winds) and single-level radiation for CoCiP."""
    from pycontrails.datalib.ecmwf import ERA5
    from pycontrails.models.cocip import Cocip

    times = (start.replace(tzinfo=None), end.replace(tzinfo=None))
    met = ERA5(time=times, variables=Cocip.met_variables, pressure_levels=pressure_levels).open_metdataset()
    rad = ERA5(time=times, variables=Cocip.rad_variables).open_metdataset()
    return met, rad
