import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.space.cache import BACKOFF_S, Cache, UpstreamError
from app.space.sources.celestrak import omm_perigee_apogee, parse_gp, parse_satcat
from app.space.sources.gcat import parse_objects, parse_orgs
from app.space.sources.launchlib import parse_launch

FIX = Path(__file__).parent / "fixtures" / "space"


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_parse_satcat():
    rows = {r.norad: r for r in parse_satcat(read("satcat.csv"))}
    starlink = rows[44771]
    assert starlink.type == "PAY" and starlink.decay_date == date(2026, 9, 18)
    assert starlink.cospar.startswith("2019-")
    assert rows[25544].decay_date is None and rows[25544].launch_date == date(1998, 11, 20)


def test_parse_gcat_objects():
    objs = parse_objects(read("gcat_satcat.tsv"))
    assert objs[44771].owner == "SPXS" and objs[44771].mass_kg == 260 and objs[44771].dry_mass_kg == 248
    pam = objs[20965]  # a spent upper stage: 2,200 kg fuelled, 132 kg dry, both flagged uncertain
    assert pam.end_of_life_mass_kg == 132 and pam.end_of_life_mass_uncertain
    assert 43900 not in objs
    assert objs[25544].jcat.startswith("S")


def test_uncertainty_follows_the_mass_actually_used():
    header = "#JCAT\tSatcat\tName\tOwner\tState\tMass\tMassFlag\tDryMass\tDryFlag\n"
    objs = parse_objects(header + "S00001\t00001\tA\tX\tUS\t2200\t?\t132\t \n"
                                  "S00002\t00002\tB\tX\tUS\t500\t?\t-\t \n")
    assert objs[1].end_of_life_mass_kg == 132 and not objs[1].end_of_life_mass_uncertain
    assert objs[2].end_of_life_mass_kg == 500 and objs[2].end_of_life_mass_uncertain


def test_parse_orgs():
    assert parse_orgs(read("gcat_orgs.tsv"))["SPXS"] == "SpaceX (Seattle)"


def test_omm_perigee_apogee_for_iss():
    perigee, apogee = omm_perigee_apogee(json.loads(read("gp_stations.json"))[0])
    assert 380 < perigee <= apogee < 440


def test_parse_gp_rejects_text_reply():
    with pytest.raises(ValueError):
        parse_gp(b"No GP data found")


def test_parse_launch():
    f9 = parse_launch(json.loads(read("ll2_previous.json"))["results"][0])
    assert f9.status == "success" and f9.provider == "SpaceX" and f9.country == "USA"
    assert f9.vehicle == "Falcon 9 Block 5" and "Falcon 9" in f9.vehicle_families
    assert f9.liftoff_mass_kg == 549_000 and f9.orbit == "PO"
    assert f9.pad_lat == pytest.approx(34.632) and f9.net.tzinfo is not None


def test_parse_launch_status_mapping():
    r = json.loads(read("ll2_previous.json"))["results"][0]
    assert parse_launch(dict(r, status={"abbrev": "Go"})).status == "upcoming"
    assert parse_launch(dict(r, status={"abbrev": "Partial Failure"})).status == "partial"
    assert parse_launch(dict(r, status={"abbrev": "In Flight"})) is None


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def cache_with(tmp_path, handler, clock):
    return Cache(tmp_path, client=httpx.Client(transport=httpx.MockTransport(handler)), clock=clock)


URL = "https://example.org/data"


def test_cache_reuses_a_fresh_copy(tmp_path):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, content=b"v1")

    clock = Clock()
    c = cache_with(tmp_path, handler, clock)
    assert c.get("k", URL, ttl_s=60) == b"v1"
    clock.t += 30
    assert c.get("k", URL, ttl_s=60) == b"v1" and len(calls) == 1
    clock.t += 60
    c.get("k", URL, ttl_s=60)
    assert len(calls) == 2


def test_cache_backs_off_after_an_error_and_serves_the_stale_copy(tmp_path):
    replies = iter([httpx.Response(200, content=b"old"), httpx.Response(403), httpx.Response(200, content=b"new")])
    calls = []

    def handler(req):
        calls.append(req)
        return next(replies)

    clock = Clock()
    c = cache_with(tmp_path, handler, clock)
    assert c.get("k", URL, ttl_s=60) == b"old"
    clock.t += 100
    assert c.get("k", URL, ttl_s=60) == b"old" and len(calls) == 2   # 403: stale copy served
    clock.t += 10
    assert c.get("k", URL, ttl_s=60) == b"old" and len(calls) == 2   # backing off: no request
    clock.t += BACKOFF_S
    assert c.get("k", URL, ttl_s=60) == b"new" and len(calls) == 3


def test_cache_raises_when_there_is_no_copy(tmp_path):
    c = cache_with(tmp_path, lambda req: httpx.Response(500), Clock())
    with pytest.raises(UpstreamError):
        c.get("k", URL, ttl_s=60)


def test_cache_sends_params(tmp_path):
    seen = {}

    def handler(req):
        seen.update(req.url.params)
        return httpx.Response(200, content=b"[]")

    cache_with(tmp_path, handler, Clock()).get("k", URL, 60, params={"SPECIAL": "DECAYING", "FORMAT": "json"})
    assert seen == {"SPECIAL": "DECAYING", "FORMAT": "json"}
