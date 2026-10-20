import httpx
import numpy as np
import pytest

from app.pipeline import real_night
from app.pipeline.screening import Sampler, ef_per_km, evaluate_track, persistent, t_crit_c
from app.sources import openmeteo
from app.sources.openmeteo import ModelGrid, fl_to_hpa, hpa_to_fl

T0 = 1_800_000_000  # an exact hour


def grid(name="ecmwf", temp=-55.0, rhi=1.0, u=20.0):
    lons, lats, times = np.array([-40.0, -30.0]), np.array([45.0, 55.0]), np.array([T0, T0 + 3600, T0 + 7200], float)
    shape = (3, 3, 2, 2)
    return ModelGrid(name, lons, lats, (300, 250, 200), times, np.full(shape, temp), np.full(shape, rhi),
                     np.full((3, 2, 2), u), np.zeros((3, 2, 2)))


# --------------------------------------------------------------------------- atmosphere helpers


def test_flight_level_pressure_round_trip():
    for fl in (300, 340, 390):
        assert hpa_to_fl(fl_to_hpa(fl)) == pytest.approx(fl, abs=0.5)
    assert round(hpa_to_fl(250)) == 340 and round(hpa_to_fl(200)) == 387


def test_wind_direction_is_where_it_comes_from():
    u, v = openmeteo._wind_uv(np.array([10.0]), np.array([270.0]))  # from the west -> blows east
    assert u[0] == pytest.approx(10.0) and abs(v[0]) < 1e-9


def test_fetch_grid_parses_both_models():
    def handler(request):
        n = len(request.url.params["latitude"].split(","))
        hourly = {"time": [T0, T0 + 3600]}
        for model in openmeteo.MODELS.values():
            for p in openmeteo.LEVELS_HPA:
                hourly[f"temperature_{p}hPa_{model}"] = [-50.0, -51.0]
                hourly[f"relative_humidity_{p}hPa_{model}"] = [96, 100]
            hourly[f"wind_speed_250hPa_{model}"] = [30.0, 30.0]
            hourly[f"wind_direction_250hPa_{model}"] = [270.0, 270.0]
        return httpx.Response(200, json=[{"hourly": hourly}] * n)
    old = openmeteo._time.sleep
    openmeteo._time.sleep = lambda s: None
    try:
        g = openmeteo.fetch_grid((-40, 40, -30, 50), 10.0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    finally:
        openmeteo._time.sleep = old
    assert set(g) == {"ecmwf", "gfs"}
    e = g["ecmwf"]
    assert e.temp_c.shape == (2, 3, 2, 2) and e.rhi.max() == pytest.approx(1.0) and e.u250[0, 0, 0] == pytest.approx(30.0)


# --------------------------------------------------------------------------- screening model


def test_schmidt_appleman_threshold_is_about_minus_42_at_250_hpa():
    assert t_crit_c(250) == pytest.approx(-42, abs=1.5)
    assert t_crit_c(200) < t_crit_c(300)  # higher up, colder threshold


def test_persistence_needs_cold_and_ice_saturated_air():
    assert persistent(-55, 0.97, 340)
    assert not persistent(-55, 0.80, 340)  # too dry: contrail evaporates
    assert not persistent(-30, 1.00, 340)  # too warm: no contrail forms


def test_night_contrails_warm_and_noon_ones_can_cool():
    assert ef_per_km(0.0, T0 - T0 % 86400 + 2 * 3600, 1.0) > 0          # 02:00 local at 0°E
    assert ef_per_km(0.0, T0 - T0 % 86400 + 12 * 3600, 1.0) < 0         # noon


def test_evaluate_track_counts_only_persistent_cruise_points():
    pts = [(-35.0, 50.0, 0.5)] * 10
    seg = [10.0] * 10
    wet = evaluate_track(Sampler(grid(rhi=1.0), T0), pts, seg, [340] * 10, T0, 2, 8)
    dry = evaluate_track(Sampler(grid(rhi=0.5), T0), pts, seg, [340] * 10, T0, 2, 8)
    assert wet.km == pytest.approx(60.0) and wet.issr[:2] == [0, 0] and dry.km == 0


# --------------------------------------------------------------------------- build


def test_aircraft_class():
    assert real_night.aircraft_class("B77W")[:2] == (7.4, 1.25)
    assert real_night.aircraft_class("A20N")[0] == 2.5
    assert real_night.aircraft_class("ZZZZ")[3] is False


class FakeDB:
    def lookup(self, icao24):
        return ("B789", "XAA")

    def operator_name(self, op):
        return "Example Air"


def raw(lat=50.0):
    path = [[T0 + 600 + 60 * k, lat, -39.0 + 0.1 * k, 10973.0] for k in range(80)]  # FL360, 80 minutes
    return {"fetched_at": T0 + 3 * 3600, "states_seen": 10, "cruising": 1, "tracks": [{"icao24": "abc123", "callsign": "XAA1", "path": path}]}


def test_build_recommends_a_change_when_both_forecasts_see_a_thin_humid_layer():
    def layered(name):
        g = grid(name)
        g.rhi[:, 0] = 0.5   # 300 hPa (FL301): dry
        g.rhi[:, 1] = 1.0   # 250 hPa (FL340): ice-saturated
        g.rhi[:, 2] = 1.0   # 200 hPa (FL387): ice-saturated
        return g
    snap = real_night.build(raw(), {"ecmwf": layered("ecmwf"), "gfs": layered("gfs")}, FakeDB(), 3, T0 + 3 * 3600,
                            bbox=(-41, 44, -29, 56))
    f = snap["flights"][0]
    assert f["models"]["ecmwf"]["base"]["km"] > 0 and f["agreement"] == pytest.approx(1.0)
    r = f["recommendation"]
    assert r and r["d"] < 0 and r["agree"] and r["net_range"][0] <= r["net_mean"] <= r["net_range"][1]
    assert snap["provenance"]["satellite"]["status"] == "not_connected" and snap["observations"] is None
    assert snap["validation"]["contrail_overlap"] == pytest.approx(1.0)


def test_build_drops_points_outside_the_forecast_area():
    snap = real_night.build(raw(lat=70.0), {"ecmwf": grid(), "gfs": grid("gfs")}, FakeDB(), 3, T0 + 3 * 3600,
                            bbox=(-41, 44, -29, 56))
    assert snap["flights"] == []
