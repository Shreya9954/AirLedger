from datetime import date

import pytest

from app.space.records import Deposit, ObjectRecord, Value, vsum


def test_fact_has_no_range():
    v = Value.fact(5, "kg", "gcat")
    assert v.low == v.central == v.high == 5 and v.tier == "fact"


def test_add_sums_ranges_and_keeps_least_certain_tier():
    s = Value(10, 8, 12, "kg", "estimate", "vehicles") + Value.fact(5, "kg", "gcat")
    assert (s.central, s.low, s.high) == (15, 13, 17)
    assert s.tier == "estimate"
    assert s.source == "gcat+vehicles"


def test_add_rejects_mixed_units():
    with pytest.raises(ValueError):
        Value.fact(1, "kg", "a") + Value.fact(1, "t", "a")


def test_range_must_bracket_central_and_tier_must_be_known():
    with pytest.raises(ValueError):
        Value(5, 6, 7, "kg", "fact", "a")
    with pytest.raises(ValueError):
        Value(5, 5, 5, "kg", "guess", "a")


def test_vsum_skips_none():
    assert vsum([None, None]) is None
    assert vsum([None, Value.fact(2, "kg", "a"), Value.fact(3, "kg", "a")]).central == 5


def test_scale():
    v = Value(10, 5, 20, "kg", "research", "f").scale(0.5)
    assert (v.central, v.low, v.high, v.tier) == (5, 2.5, 10, "research")


def test_deposit_checks_species_bins_and_unit():
    ok = Value.fact(1, "kg", "a")
    Deposit("black_carbon", 15, 50, ok)
    for bad in (("soot", 15, 50, ok), ("black_carbon", 12, 50, ok), ("black_carbon", 50, 15, ok),
                ("black_carbon", 15, 50, Value.fact(1, "t", "a"))):
        with pytest.raises(ValueError):
            Deposit(*bad)


def test_end_of_life_mass_prefers_dry_mass():
    base = dict(norad=1, cospar="2000-001A", name="X", type="R/B", operator="O", operator_code="O", country=None,
                launch_date=date(2000, 1, 1), decay_date=None)
    assert ObjectRecord(**base, mass_kg=2200, dry_mass_kg=132).end_of_life_mass_kg == 132
    assert ObjectRecord(**base, mass_kg=2200).end_of_life_mass_kg == 2200


def test_to_json_omits_empty_note():
    assert "note" not in Value.fact(1, "kg", "a").to_json()
    assert Value.fact(1, "kg", "a", "uncertain").to_json()["note"] == "uncertain"
