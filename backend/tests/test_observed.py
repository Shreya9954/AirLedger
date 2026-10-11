from datetime import datetime, timezone

import httpx
import numpy as np
import pytest

from app.pipeline.attribution import advect
from app.pipeline.observed import attribute_observations
from app.pipeline.wind import GridWind
from app.sources.contrails_org import SEGMENTS_PATH, ContrailsOrgClient, floor_10min, parse_linestring

EASTWARD_20MS = lambda lon, lat, t: (20.0, 0.0)  # noqa: E731


def track(lat, t0=0.0):
    return [(-40 + i * 0.5, lat, t0 + i * 0.05) for i in range(21)]


# --------------------------------------------------------------------------- Contrails.org client


def test_parse_linestring():
    assert parse_linestring("LINESTRING (-90.1 35.2, -89.8 35.6)") == [(-90.1, 35.2), (-89.8, 35.6)]
    assert parse_linestring("LINESTRING Z (1 2 3, 4 5 6)") == [(1.0, 2.0), (4.0, 5.0)]
    with pytest.raises(ValueError):
        parse_linestring("POINT (1 2)")


def test_floor_10min():
    assert floor_10min(datetime(2026, 10, 10, 21, 37, 12)) == datetime(2026, 10, 10, 21, 30)


def test_segments_request_and_parse():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"], seen["time"], seen["key"] = request.url.path, request.url.params["time"], request.headers["x-api-key"]
        return httpx.Response(200, json=[
            {"timestamp": "2026-10-10T21:30:00.000000", "geometry": "LINESTRING (-40 50, -39 50.2)"},
            {"timestamp": "2026-10-10T21:30:00.000000", "geometry": "LINESTRING (10 80, 11 80)"},  # outside bbox
        ])

    client = ContrailsOrgClient("secret", transport=httpx.MockTransport(handler))
    got = client.segments_between(datetime(2026, 10, 10, 21, 34, tzinfo=timezone.utc),
                                  datetime(2026, 10, 10, 21, 35, tzinfo=timezone.utc), (-82, 26, 14, 68))
    assert seen == {"path": SEGMENTS_PATH, "time": "2026-10-10T21:30:00", "key": "secret"}
    assert len(got) == 1 and got[0].line == [(-40.0, 50.0), (-39.0, 50.2)]
    assert got[0].id == "GOES-20261010T2130-0" and got[0].observed_at.tzinfo is not None


def test_missing_time_step_is_empty_not_an_error():
    client = ContrailsOrgClient("k", transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    assert client.segments(datetime(2026, 10, 10, 21, 0)) == []


def test_client_needs_a_key():
    with pytest.raises(ValueError):
        ContrailsOrgClient("")


# --------------------------------------------------------------------------- wind


def test_grid_wind_nearest_lookup():
    lons, lats, hours = np.array([-50.0, -40.0]), np.array([40.0, 50.0]), np.array([0.0, 1.0])
    u = np.zeros((2, 2, 2))
    u[1, 1, 1] = 30.0
    w = GridWind(lons, lats, hours, u, np.zeros_like(u))
    assert w(-41.0, 49.0, 0.9) == (30.0, 0.0)
    assert w(-49.0, 41.0, 0.9) == (0.0, 0.0)
    assert w(10.0, 80.0, 99.0) == (30.0, 0.0)  # clamps to the grid edge


# --------------------------------------------------------------------------- observations -> flights


def test_detection_is_attributed_to_the_flight_that_made_it():
    tracks = {"A": track(50.0), "B": track(51.0)}
    obs_h = 1.5
    line = advect(track(50.0), obs_h, EASTWARD_20MS)[2:15]
    got = attribute_observations([("GOES-1", obs_h, line)], tracks, EASTWARD_20MS)
    assert set(got) == {"A"}
    a = got["A"]
    assert a["id"] == "GOES-1" and a["offset_km"] < 1 and a["confidence"] > 0.9 and a["n_matched"] == 1
    assert 0 < a["age_min"] <= 90  # midpoint of waypoints 2..14, flown 0.1..0.7 h, seen at 1.5 h


def test_detections_older_than_max_age_are_not_matched():
    line = advect(track(50.0), 1.5, EASTWARD_20MS)[2:15]
    assert attribute_observations([("GOES-1", 5.0, line)], {"A": track(50.0)}, EASTWARD_20MS) == {}


def test_best_match_is_kept_and_matches_are_counted():
    tracks = {"A": track(50.0)}
    exact = advect(track(50.0), 1.5, EASTWARD_20MS)[2:15]
    shifted = [(lon, lat + 0.05) for lon, lat in exact]  # ~5.6 km off
    got = attribute_observations([("near", 1.5, shifted), ("exact", 1.5, exact)], tracks, EASTWARD_20MS)
    assert got["A"]["id"] == "exact" and got["A"]["n_matched"] == 2
