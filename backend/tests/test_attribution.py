from app.pipeline.attribution import advect, attribute, mean_offset_km

EASTWARD_20MS = lambda lon, lat, t: (20.0, 0.0)  # noqa: E731


def track(lat, t0=0.0):
    return [(-40 + i * 0.5, lat, t0 + i * 0.05) for i in range(21)]


def test_advect_moves_east_with_wind():
    moved = advect([(-40.0, 50.0, 0.0)], at_hours=1.0, wind=EASTWARD_20MS)
    assert moved[0][0] > -40 and moved[0][1] == 50.0


def test_offset_zero_for_identical_lines():
    line = [(-40 + i, 50.0) for i in range(5)]
    assert mean_offset_km(line, line) < 1e-6


def test_attributes_to_the_closest_advected_flight():
    flights = {"A": track(50.0), "B": track(51.0)}
    observed_h = 1.5
    line = advect(track(50.0), observed_h, EASTWARD_20MS)[2:15]
    m = attribute("CT-1", line, observed_h, flights, EASTWARD_20MS)
    assert m is not None and m.flight_id == "A" and m.offset_km < 1 and m.confidence > 0.9


def test_no_match_beyond_threshold():
    line = [(-30 + i * 0.5, 60.0) for i in range(10)]
    assert attribute("CT-2", line, 1.0, {"A": track(50.0)}, EASTWARD_20MS) is None
