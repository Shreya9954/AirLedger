from app.constants import AGWP_CO2_J_PER_T, N_WAYPOINTS
from app.pipeline.reroute import LevelResult, build_options, extra_fuel_t, humid_window

SEG = [50.0] * N_WAYPOINTS


def contrail_between(a, b, ef_per_point=1e13):
    iss = [1 if a <= i < b else 0 for i in range(N_WAYPOINTS)]
    n = b - a
    return LevelResult(iss, km=n * 50.0, ef=n * ef_per_point)


def test_window_is_padded_by_100_km():
    w = humid_window(contrail_between(40, 60).issr, SEG)
    assert w == (38, 61)  # two 50 km segments each side


def test_no_contrail_no_window():
    assert humid_window([0] * N_WAYPOINTS, SEG) is None


def test_descending_costs_more_than_climbing():
    assert extra_fuel_t(-20, 60, 1000, 5000) > extra_fuel_t(20, 60, 1000, 5000) > 0
    assert extra_fuel_t(0, 60, 1000, 5000) == 0


def test_best_option_avoids_contrail():
    base = contrail_between(40, 60)
    dry = LevelResult([0] * N_WAYPOINTS, 0.0, 0.0)
    # climbing clears the humid layer, descending does not
    opts = build_options(base, 350, 410, fuel_t=60, dist_km=6900, seg_km=SEG,
                         evaluate=lambda fl, w: dry if fl > 350 else base)
    assert opts["best"]["d"] == 20
    assert opts["best"]["avoided"] == base.ef / AGWP_CO2_J_PER_T
    assert opts["-20"]["net"] < 0


def test_ceiling_blocks_options():
    base = contrail_between(40, 60)
    opts = build_options(base, 390, 390, 30, 5000, SEG, evaluate=lambda fl, w: base)
    assert opts["20"] is None and opts["40"] is None
