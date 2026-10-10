import pytest

from app.constants import AGWP_CO2_J_PER_T
from app.scoring import ef_to_tco2e, flight_score, fuel_co2_t


def test_fuel_co2():
    assert fuel_co2_t(10) == pytest.approx(31.6)


def test_ef_conversion_round_trip():
    assert ef_to_tco2e(AGWP_CO2_J_PER_T * 50) == pytest.approx(50)


def test_flight_score_range_brackets_central():
    s = flight_score(fuel_t=50, ef_j=1.5e14)
    assert s.low < s.central < s.high
    assert s.central - fuel_co2_t(50) == pytest.approx(1.5e14 / AGWP_CO2_J_PER_T)


def test_net_cooling_contrail_range_is_ordered():
    s = flight_score(fuel_t=50, ef_j=-2e13)
    assert s.low <= s.high
