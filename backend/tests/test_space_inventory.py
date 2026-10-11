from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from app.space import factors as F
from app.space import inventory as inv
from app.space import vehicles as V
from app.space.build import build_summary
from app.space.contract import validate_summary
from app.space.records import BIN_EDGES_KM, SPECIES, TIERS, LaunchRecord, ObjectRecord, Value

from .test_space_build import NOW, inputs

A_IDS = {"ll2", "celestrak", "gcat"}
REF_IDS = {r["id"] for r in inv.references()}


def launch(vehicle, families=(), liftoff=None, status="success"):
    return LaunchRecord(id="ll2:x", name=f"{vehicle} | Test", net=datetime(2026, 9, 1, tzinfo=timezone.utc),
                        status=status, provider="Test", country=None, vehicle=vehicle,
                        vehicle_families=tuple(families), liftoff_mass_kg=liftoff)


def obj(name, type_="PAY", mass=800.0, owner=None, tags=()):
    return ObjectRecord(norad=1, cospar="2020-001A", name=name, type=type_, operator=owner or "Test",
                        operator_code=owner, country="US", launch_date=date(2020, 1, 1),
                        decay_date=date(2026, 9, 1), mass_kg=mass, tags=tuple(tags))


F9 = launch("Falcon 9 Block 5", ("Falcon", "Falcon 9"), 549_000)
VEGA = launch("Vega-C", ("Vega",), 210_000)


def check_value(v: Value):
    assert v.unit == "kg"
    assert v.tier in TIERS
    assert 0 <= v.low <= v.central <= v.high
    for tok in v.source.split("+"):
        assert tok in A_IDS | REF_IDS, tok


# ---------------------------------------------------------------- matching

# Every vehicle name Launch Library 2 used in the 90 days to 2026-10-11 (docs/space/notes-a.md).
WINDOW = {
    "Falcon 9 Block 5": "falcon9", "Electron": "electron", "Long March 12": "cz12", "Falcon Heavy": "falconheavy",
    "Starship V3": "starship", "Long March 6A": "cz6a", "Long March 8A": "cz8", "Long March 7A": "cz7a",
    "Kinetica 1": "kinetica1", "Soyuz 2.1b": "soyuz2", "Soyuz 2.1b Fregat-M": "soyuz2", "Soyuz 2.1b Fregat": "soyuz2",
    "Soyuz 2.1a": "soyuz2", "Gravity-1": "gravity1", "KSLV-2 Nuri": "nuri", "Long March 2D": "cz2d",
    "Long March 2C": "cz2c", "Long March 4B": "cz4b", "Long March 6C": "cz6c", "Long March 3B/E": "cz3b",
    "Kuaizhou 11": "kuaizhou", "Zhuque-2E Block 2": "zhuque2", "Zhuque-3": "zhuque3", "Vega-C": "vegac",
    "Spectrum": "spectrum", "GSLV Mk. II": "gslv", "Pallas-1": "pallas1", "Ariane 62": "ariane6", "H3-22": "h3",
    "H3-24": "h3", "Smart Dragon 3": "jielong3", "Vikram-I": "vikram1",
}


@pytest.mark.parametrize("vehicle,key", WINDOW.items())
def test_every_rocket_in_the_window_is_matched(vehicle, key):
    assert inv.match_vehicle(launch(vehicle)) == key


def test_specific_names_win_over_families():
    assert inv.match_vehicle(launch("Long March 12A")) == "cz12a"
    assert inv.match_vehicle(launch("Long March 6")) == "cz6"
    assert inv.match_vehicle(launch("Falcon Heavy", ("Falcon",))) == "falconheavy"
    assert inv.match_vehicle(launch("Some Configuration", ("Falcon", "Falcon 9"))) == "falcon9"


def test_unknown_rocket_gives_nothing():
    unknown = launch("Unknown Rocket Mk 1", ("Mystery",), 100_000)
    assert inv.match_vehicle(unknown) is None
    assert inv.launch_propellant(unknown) is None
    assert inv.launch_deposits(unknown) == []


def test_no_number_without_a_liftoff_mass_or_published_loads():
    assert inv.launch_propellant(launch("Spectrum")) is None
    assert inv.launch_deposits(launch("Vikram-I")) == []
    assert inv.launch_propellant(launch("Spectrum", liftoff=40_000)) is not None


# ---------------------------------------------------------------- the table

def test_vehicle_table_is_well_formed():
    for key, v in V.VEHICLES.items():
        assert v.source in V.WIKI, key
        for s in v.stages:
            assert s.propellant in F.PROPELLANTS, (key, s.label)
            assert 0 <= s.lo_km < s.hi_km, (key, s.label)
            assert s.climb in ("boost", "upper") and s.count >= 1
            assert (s.kg is None) != (s.share is None), (key, s.label)
        if v.stages[0].share is not None:
            assert sum(s.share for s in v.stages) == pytest.approx(1.0), key


def test_propellant_fraction_is_derived_from_the_evidence():
    fr = [p / m for _, _, p, m in V.PROPELLANT_FRACTION_EVIDENCE]
    assert V.PROPELLANT_FRACTION.low == round(min(fr), 3) and V.PROPELLANT_FRACTION.high == round(max(fr), 3)
    assert 0.8 < V.PROPELLANT_FRACTION.low < V.PROPELLANT_FRACTION.central < V.PROPELLANT_FRACTION.high < 0.95


@pytest.mark.parametrize("vehicle,evidence", [
    ("Soyuz 2.1b", "Soyuz-2.1b"), ("Ariane 62", "Ariane 62"), ("Vega-C", "Vega C"), ("H3-22", "H3-22"),
    ("LVM3", "LVM3"), ("GSLV Mk. II", "GSLV Mk II"), ("PSLV-XL", "PSLV-XL"), ("SSLV", "SSLV"),
    ("Proton-M", "Proton-M / Breeze-M"), ("Long March 2C", "Long March 2C"), ("Long March 3B/E", "Long March 3B/E"),
    ("Atlas V 551", "Atlas V 551"),
])
def test_table_loads_match_the_evidence_list(vehicle, evidence):
    total = next(p for name, _, p, _ in V.PROPELLANT_FRACTION_EVIDENCE if name == evidence)
    assert inv.launch_propellant(launch(vehicle)).central == pytest.approx(total)


def test_configuration_changes_booster_count():
    p = lambda name: inv.launch_propellant(launch(name)).central
    assert p("Ariane 64") - p("Ariane 62") == pytest.approx(2 * 141_400)
    assert p("H3-24") - p("H3-22") == pytest.approx(2 * 67_200)
    assert p("H3-30") == pytest.approx(226_000 + 24_600)
    assert p("Atlas V 551") - p("Atlas V N22") == pytest.approx(3 * 44_200)
    assert p("Long March 3B/E") - p("Long March 3C") == pytest.approx(2 * 41_100)
    assert p("Starship V3") > p("Starship")
    assert p("Soyuz 2.1b Fregat-M") - p("Soyuz 2.1b") == pytest.approx(6_650)


# ---------------------------------------------------------------- launches

def test_falcon9_propellant_from_liftoff_mass():
    p = inv.launch_propellant(F9)
    check_value(p)
    assert p.tier == "estimate" and set(p.source.split("+")) == {"ll2", V.METHOD}
    assert 0.82 * 549_000 <= p.low and p.high <= 0.94 * 549_000


def test_failed_launch_keeps_central_but_low_goes_to_zero():
    p = inv.launch_propellant(replace(F9, status="failure"))
    assert p.low == 0 and p.central == inv.launch_propellant(F9).central


@pytest.mark.parametrize("vehicle", list(WINDOW))
def test_deposits_are_valid_and_below_the_top_bin(vehicle):
    L = launch(vehicle, liftoff=300_000)
    total = inv.launch_propellant(L)
    deps = inv.launch_deposits(L)
    for d in deps:
        assert d.lo_km in BIN_EDGES_KM and d.hi_km in BIN_EDGES_KM and d.hi_km - d.lo_km == 5
        assert d.species in SPECIES
        check_value(d.value)
    below = sum(d.value.central for d in deps if d.species == "propellant")
    assert 0 < below <= total.central * (1 + 1e-9)


def test_species_follow_the_propellant():
    f9 = {d.species for d in inv.launch_deposits(F9)}
    assert f9 == {"propellant", "black_carbon"}
    vega = {d.species for d in inv.launch_deposits(VEGA)}
    assert {"alumina", "chlorine", "black_carbon"} <= vega
    ariane = inv.launch_deposits(launch("Ariane 62"))
    # hydrogen core leaves no soot, the solid boosters do
    assert all(d.lo_km < 60 for d in ariane if d.species == "black_carbon")


def test_most_of_a_falcon9_burns_below_120_km_and_the_booster_relights_on_the_way_down():
    deps = inv.launch_deposits(F9)
    prop = {d.lo_km: d.value.central for d in deps if d.species == "propellant"}
    assert 0.75 < sum(prop.values()) / inv.launch_propellant(F9).central < 0.95
    s1 = next(s for s in V.VEHICLES["falcon9"].stages if s.reusable)
    shares = dict((lo, s) for lo, _, s in V.bins(s1))
    assert sum(shares.values()) == pytest.approx(1.0)
    entry = F.ENTRY_BURN_SHARE / 3
    assert shares[55] > entry and shares[65] > entry   # ascent plus the 70-55 km entry burn
    assert shares[0] > shares[30]                         # slow near the pad: more propellant per km


def test_upper_stage_profile_is_truncated_at_the_top():
    s2 = V.VEHICLES["falcon9"].stages[1]
    b = V.bins(s2)
    assert b[0][0] == 70 and b[-1][1] == 120
    assert 0 < sum(s for _, _, s in b) < 1


def test_soot_survives_afterburning_only_high_up():
    assert F.bc_afterburn(0) == F.bc_afterburn(15) == 0.04
    assert F.bc_afterburn(42) == 1 and F.bc_afterburn(80) == 1
    hs = range(0, 60, 5)
    assert all(F.bc_afterburn(a) <= F.bc_afterburn(b) for a, b in zip(hs, hs[1:]))
    bc = {d.lo_km: d.value.central for d in inv.launch_deposits(F9) if d.species == "black_carbon"}
    assert sum(v for k, v in bc.items() if k >= 40) > sum(v for k, v in bc.items() if k < 40)


def test_deterministic():
    assert inv.launch_deposits(F9) == inv.launch_deposits(F9)


# ---------------------------------------------------------------- re-entries

def ablated(o):
    return next(d.value for d in inv.reentry_deposits(o) if d.species == "ablated_mass")


def aluminium(o):
    return next((d.value for d in inv.reentry_deposits(o) if d.species == "aluminium"), None)


def test_starlink_burns_up_completely():
    o = obj("STARLINK-31079", mass=700, owner="SPXS")
    a = ablated(o)
    check_value(a)
    assert a.central == 700 and a.tier == "estimate" and set(a.source.split("+")) == {"gcat", "barker2024"}
    assert aluminium(o).central == pytest.approx(280) and aluminium(o).tier == "research"
    assert all((d.lo_km, d.hi_km) == F.ABLATION_KM for d in inv.reentry_deposits(o))


def test_burn_up_by_object_class():
    assert ablated(obj("COSMOS 1707", mass=1000)).central == pytest.approx(800)
    assert ablated(obj("FALCON 9 R/B", "R/B", 4000)).central == pytest.approx(2600)
    assert aluminium(obj("FALCON 9 R/B", "R/B", 4000)).central == pytest.approx(2600 * 0.7)
    assert ablated(obj("CZ-5B R/B", "R/B", 21000)).central == pytest.approx(6300)
    assert ablated(obj("ONEWEB-0123", mass=150, owner="ONEWEB")).central == 150


def test_starship_does_not_outweigh_the_starlink_fleet():
    o = obj("STARSHIP-14", mass=120_000, owner="SPX")
    a = ablated(o)
    assert a.low == 0 and a.central <= 0.01 * 120_000 and a.high <= 0.05 * 120_000
    assert aluminium(o) is None


def test_landed_massless_and_unknown_objects_leave_nothing():
    assert inv.reentry_deposits(obj("CREW DRAGON 12", mass=9500, owner="SPX", tags=("landed",))) == []
    assert inv.reentry_deposits(obj("ISS DEB", "DEB", mass=0)) == []
    assert inv.reentry_deposits(obj("UNKNOWN", "UNK", mass=None)) == []


def test_upper_stage_uses_dry_mass():
    stage = replace(obj("PAM-D R/B", "R/B", 2200), dry_mass_kg=132)
    assert ablated(stage).central == pytest.approx(132 * 0.65)


# ---------------------------------------------------------------- aviation and sources

def test_aviation_context_scales_with_days():
    a90, a365 = inv.aviation_context(90), inv.aviation_context(365)
    for d in a90:
        check_value(d.value)
    fuel = lambda deps: sum(d.value.central for d in deps if d.species == "propellant")
    assert fuel(a365) == pytest.approx(283e9)
    assert fuel(a90) == pytest.approx(283e9 * 90 / 365)
    assert {d.species for d in a90} == {"propellant", "black_carbon"}
    assert {d.value.tier for d in a90 if d.species == "black_carbon"} == {"research"}


def test_references_are_unique_and_complete():
    refs = inv.references()
    ids = [r["id"] for r in refs]
    assert len(ids) == len(set(ids)) and not (set(ids) & A_IDS)
    for r in refs:
        assert r["name"] and r["url"].startswith("https://")


def test_real_inventory_matches_contract_2_on_fixtures():
    d = build_summary(inputs(), NOW, 90)   # default inventory = this module
    assert validate_summary(d) == []
    assert d["coverage"]["launches_with_data"] == d["coverage"]["launches"]
    assert {c["source"] for c in d["layers"]} == {"launch", "reentry", "aviation"}
