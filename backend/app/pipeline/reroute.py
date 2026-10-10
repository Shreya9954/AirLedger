"""Altitude-change options for one flight: extra fuel CO2 versus contrail warming avoided.

Pure functions, so they are unit-tested without pycontrails. The contrail results per option
come from cocip.py; this module only decides the window, the fuel penalty and the best option.
Output shape matches frontend/js/model.js rerouteOptions().
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from ..constants import CO2_PER_FUEL, CRUISE_END, CRUISE_START, DEFAULT_CEILING, DELTAS_FL, MIN_FL, WINDOW_PAD_KM
from ..scoring import ef_to_tco2e


@dataclass
class LevelResult:
    issr: list[int]   # 1 where a persistent contrail forms at this waypoint
    km: float         # persistent contrail length
    ef: float         # energy forcing, J


def humid_window(issr: Sequence[int], seg_km: Sequence[float], pad_km: float = WINDOW_PAD_KM,
                 c0: int = CRUISE_START, c1: int = CRUISE_END) -> tuple[int, int] | None:
    """First..last contrail waypoint, padded by pad_km each side and clipped to cruise."""
    idx = [i for i in range(c0, c1) if issr[i]]
    if not idx:
        return None
    w0, km = idx[0], 0.0
    while w0 > c0 and km < pad_km:
        w0 -= 1
        km += seg_km[w0]
    w1, km = idx[-1], 0.0
    while w1 < c1 and km < pad_km:
        km += seg_km[w1]
        w1 += 1
    return w0, w1


def extra_fuel_t(delta_fl: int, fuel_t: float, window_km: float, dist_km: float) -> float:
    """Fuel penalty of flying delta_fl off the filed level across the window.

    Descending costs more than climbing (denser air, more drag): 1.1% vs 0.7% per 2,000 ft,
    applied to the share of the route that is deviated, plus 40 kg for the level changes.
    Replace with pycontrails' PS aircraft performance model for per-type numbers.
    """
    if delta_fl == 0:
        return 0.0
    pct = 0.011 * (-delta_fl / 20) if delta_fl < 0 else 0.007 * (delta_fl / 20)
    return fuel_t * (window_km / dist_km) * pct + 0.04


def build_options(base: LevelResult, fl: int, ceiling: int | None, fuel_t: float, dist_km: float,
                  seg_km: Sequence[float], evaluate: Callable[[int, tuple[int, int]], LevelResult]) -> dict:
    """evaluate(new_fl, window) runs the contrail model with new_fl applied inside window."""
    ceiling = ceiling or DEFAULT_CEILING
    window = humid_window(base.issr, seg_km)
    wkm = sum(seg_km[window[0]:window[1] + 1]) if window else 0.0
    out: dict = {}
    for d in DELTAS_FL:
        nf = fl + d
        if nf > ceiling or nf < MIN_FL:
            out[str(d)] = None
            continue
        if d == 0 or window is None:
            out[str(d)] = {"d": d, "fl": nf, "km": base.km, "ef": base.ef, "avoided": 0.0, "extraCO2": 0.0, "net": 0.0}
            continue
        r = evaluate(nf, window)
        extra = extra_fuel_t(d, fuel_t, wkm, dist_km) * CO2_PER_FUEL
        avoided = ef_to_tco2e(base.ef - r.ef)
        out[str(d)] = {"d": d, "fl": nf, "km": r.km, "ef": r.ef, "avoided": avoided, "extraCO2": extra, "net": avoided - extra}
    best = out["0"]
    for d in DELTAS_FL:
        o = out[str(d)]
        if o and o["net"] > best["net"]:
            best = o
    out["best"] = best
    out["wkm"] = wkm
    return out
