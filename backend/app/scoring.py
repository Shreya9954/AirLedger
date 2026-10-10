"""The shared climate-impact score: tonnes CO2-equivalent over 100 years (tCO2e).

Aviation:  fuel CO2  +  contrail energy forcing / AGWP_CO2
Space:     fuel CO2  +  stratospheric particle term (black carbon, alumina), with wide ranges
"""
from __future__ import annotations

from dataclasses import dataclass

from .constants import AGWP_CO2_J_PER_T, CO2_PER_FUEL


def fuel_co2_t(fuel_t: float) -> float:
    return fuel_t * CO2_PER_FUEL


def ef_to_tco2e(ef_j: float) -> float:
    """Contrail energy forcing (J) -> tCO2e over 100 years. Efficacy is not applied."""
    return ef_j / AGWP_CO2_J_PER_T


@dataclass(frozen=True)
class Score:
    central: float
    low: float
    high: float


# Contrail EF uncertainty is roughly a factor of two, dominated by humidity forecasts.
CONTRAIL_LOW, CONTRAIL_HIGH = 0.5, 1.8


def flight_score(fuel_t: float, ef_j: float) -> Score:
    co2 = fuel_co2_t(fuel_t)
    c = ef_to_tco2e(ef_j)
    lo, hi = sorted((co2 + c * CONTRAIL_LOW, co2 + c * CONTRAIL_HIGH))
    return Score(co2 + c, lo, hi)
