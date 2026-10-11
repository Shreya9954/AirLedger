import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.space.build import Inputs, build_orbits, build_summary
from app.space.contract import validate_orbits, validate_summary
from app.space.records import Deposit, Value
from app.space.sources.celestrak import parse_satcat
from app.space.sources.gcat import parse_objects, parse_orgs
from app.space.sources.launchlib import parse_launch

FIX = Path(__file__).parent / "fixtures" / "space"
DATA = Path(__file__).resolve().parents[2] / "frontend" / "data"
NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def inputs() -> Inputs:
    launches = [parse_launch(r) for r in json.loads(read("ll2_previous.json"))["results"]]
    upcoming = replace(launches[0], id="ll2:upcoming", status="upcoming", net=NOW + timedelta(days=3))
    return Inputs(
        satcat=parse_satcat(read("satcat.csv")),
        gcat=parse_objects(read("gcat_satcat.tsv")),
        orgs=parse_orgs(read("gcat_orgs.tsv")),
        decaying=json.loads(read("gp_decaying.json")),
        launches=launches + [upcoming],
        retrieved={"gcat": NOW.timestamp()},
    )


def is_f9(launch) -> bool:
    return "Falcon 9" in launch.vehicle_families


FAKE = SimpleNamespace(
    match_vehicle=lambda L: "falcon9" if is_f9(L) else None,
    launch_propellant=lambda L: Value(400_000, 380_000, 420_000, "kg", "estimate", "vehicles") if is_f9(L) else None,
    launch_deposits=lambda L: [Deposit("black_carbon", 15, 50, Value(700, 210, 2100, "kg", "research", "factors"))]
    if is_f9(L) else [],
    reentry_deposits=lambda o: [Deposit("ablated_mass", 70, 80, Value.fact(o.end_of_life_mass_kg, "kg", "gcat"))]
    if o.end_of_life_mass_kg else [],
    aviation_context=lambda days: [Deposit("black_carbon", 10, 15, Value(1000, 500, 2000, "kg", "research", "factors"))],
    references=lambda: [{"id": "vehicles", "name": "Vehicle table", "url": ""},
                        {"id": "factors", "name": "Emission factors", "url": ""}],
)


def summary(inv=FAKE) -> dict:
    return build_summary(inputs(), NOW, 90, inv)


def test_summary_matches_contract():
    assert validate_summary(summary()) == []


def test_stub_inventory_also_matches_contract():
    d = build_summary(inputs(), NOW, 90)
    assert validate_summary(d) == []
    assert d["layers"] == [] and d["coverage"]["launches_with_data"] == 0


def test_reentries_in_window_newest_first():
    d = summary()
    assert {r["norad"] for r in d["reentries"]} == {44771, 44772, 45062, 20965, 43900}
    dates = [r["decay_date"] for r in d["reentries"]]
    assert dates == sorted(dates, reverse=True)
    pam = next(r for r in d["reentries"] if r["norad"] == 20965)
    assert pam["mass"]["central"] == 132 and pam["mass"]["tier"] == "fact"
    assert pam["mass"]["note"] == "GCAT marks this mass as uncertain"
    unknown = next(r for r in d["reentries"] if r["norad"] == 43900)
    assert unknown["mass"] is None and unknown["operator"] and unknown["deposits"] == {}


def test_owner_ledger_groups_by_gcat_owner_and_matches_items():
    d = summary()
    owners = d["ledger"]["reentry_owners"]
    assert owners[0]["operator_code"] == "SPXS" and owners[0]["operator"] == "SpaceX (Seattle)"
    assert owners[0]["reentries"] == 3 and owners[0]["mass"]["central"] == 3 * 248
    assert sum(r["reentries"] for r in owners) == len(d["reentries"])
    assert sum(r["reentries_with_mass"] for r in owners) == d["coverage"]["reentries_with_mass"] == 4


def test_launches_and_provider_ledger():
    d = summary()
    upcoming = next(x for x in d["launches"] if x["status"] == "upcoming")
    assert upcoming["deposits"] == {} and upcoming["vehicle_key"] == "falcon9"
    f9 = next(x for x in d["launches"] if x["status"] != "upcoming" and x["vehicle_key"] == "falcon9")
    assert f9["liftoff_mass"]["central"] == 549_000 and f9["propellant"]["tier"] == "estimate"
    providers = {r["provider"]: r for r in d["ledger"]["launch_providers"]}
    assert providers["SpaceX"]["launches"] == 1 and providers["SpaceX"]["launches_with_data"] == 1
    assert d["ledger"]["launch_providers"][0]["provider"] == "SpaceX"
    assert d["coverage"]["launches"] == 2 and d["coverage"]["launches_with_data"] == 1


def test_layers_spread_evenly_into_5_km_bins():
    d = summary()
    launch = [c for c in d["layers"] if c["source"] == "launch"]
    assert [c["lo_km"] for c in launch] == [15, 20, 25, 30, 35, 40, 45]
    assert all(c["hi_km"] - c["lo_km"] == 5 for c in d["layers"])
    assert sum(c["value"]["central"] for c in launch) == 700
    reentry = [c for c in d["layers"] if c["source"] == "reentry"]
    assert [c["lo_km"] for c in reentry] == [70, 75]
    assert sum(c["value"]["central"] for c in reentry) == 3 * 248 + 132
    assert [c["lo_km"] for c in d["layers"] if c["source"] == "aviation"] == [10]


def test_falling_objects_lowest_perigee_first():
    d = summary()
    expected = {o["NORAD_CAT_ID"] for o in json.loads(read("gp_decaying.json"))}
    assert {f["norad"] for f in d["falling"]} == expected
    perigees = [f["perigee_km"] for f in d["falling"]]
    assert perigees == sorted(perigees) and all(f["epoch"].endswith("Z") for f in d["falling"])


def test_monthly_series():
    d = summary()
    months = {m["month"]: m for m in d["monthly"]}
    assert d["monthly"][0]["month"] == "2015-01" and d["monthly"][-1]["month"] == "2026-10"
    assert months["2026-09"]["reentries"] == 2 and months["2026-09"]["reentered_mass"]["central"] == 2 * 248
    assert months["2026-07"]["reentries"] == 1 and months["2026-07"]["reentered_mass"] is None


def test_landed_objects_are_listed_but_kept_out_of_totals():
    data = inputs()
    data.satcat = [replace(r, orbit_type="LAN") if r.norad == 44771 else r for r in data.satcat]
    seen_tags = {}
    inv = SimpleNamespace(**{**vars(FAKE), "reentry_deposits": lambda o: seen_tags.setdefault(o.norad, o.tags) and []})
    d = build_summary(data, NOW, 90, inv)
    assert validate_summary(d) == []
    capsule = next(r for r in d["reentries"] if r["norad"] == 44771)
    assert capsule["landed"] is True and seen_tags[44771] == ("landed",)
    assert all(r["landed"] is False for r in d["reentries"] if r["norad"] != 44771)
    spx = next(r for r in d["ledger"]["reentry_owners"] if r["operator_code"] == "SPXS")
    assert spx["reentries"] == 2 and spx["mass"]["central"] == 2 * 248
    assert d["coverage"]["reentries"] == len(d["reentries"]) - 1
    assert {m["month"]: m for m in d["monthly"]}["2026-09"]["reentries"] == 1


def test_a_failing_inventory_function_does_not_break_the_build():
    broken = SimpleNamespace(**{**vars(FAKE), "launch_deposits": lambda L: 1 / 0})
    d = summary(broken)
    assert validate_summary(d) == []
    assert all(x["deposits"] == {} for x in d["launches"])


def test_sources_include_inventory_references():
    ids = [s["id"] for s in summary()["sources"]]
    assert ids == ["ll2", "celestrak", "gcat", "vehicles", "factors"]


def test_sample_file_matches_contract_and_built_shape():
    sample = json.loads((DATA / "space-sample.json").read_text(encoding="utf-8"))
    assert validate_summary(sample) == [] and sample["sample"] is True
    built = summary()
    assert sample.keys() == built.keys()
    for key in ("launches", "reentries", "falling", "monthly", "layers"):
        assert sample[key][0].keys() == built[key][0].keys(), key
    for key in ("launch_providers", "reentry_owners"):
        assert sample["ledger"][key][0].keys() == built["ledger"][key][0].keys(), key
    assert sample["coverage"].keys() == built["coverage"].keys()


def test_orbits_contract_and_sampling():
    stations = json.loads(read("gp_stations.json"))
    decaying = json.loads(read("gp_decaying.json"))
    active = [dict(stations[0], NORAD_CAT_ID=100_000 + i, OBJECT_NAME=f"SAT {i}") for i in range(50)]
    d = build_orbits(decaying, stations, active, limit=13, now=NOW)
    assert validate_orbits(d) == []
    groups = [o["group"] for o in d["objects"]]
    assert (groups.count("falling"), groups.count("station"), groups.count("active")) == (2, 1, 10)
    assert len({o["NORAD_CAT_ID"] for o in d["objects"]}) == 13
    assert len(build_orbits(decaying, stations, active, limit=1000, now=NOW)["objects"]) == 53


def test_orbit_sample_file_matches_contract():
    assert validate_orbits(json.loads((DATA / "space-orbits-sample.json").read_text(encoding="utf-8"))) == []
