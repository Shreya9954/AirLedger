"""Checks that a summary or orbits document matches Contract 2 in docs/space-ledger.md.

Used by the tests (against both the sample file and built output) and by the snapshot script, so the
frontend's sample and the real data cannot drift apart.
"""
from __future__ import annotations

from .records import BIN_EDGES_KM, SPECIES, TIERS

SUMMARY_KEYS = {"schema", "sample", "generated_at", "window", "sources", "bins_km", "regions", "launches",
                "reentries", "falling", "ledger", "layers", "monthly", "coverage"}
LAUNCH_KEYS = {"id", "name", "net", "status", "provider", "country", "vehicle", "vehicle_key", "orbit", "pad",
               "liftoff_mass", "propellant", "deposits"}
REENTRY_KEYS = {"norad", "cospar", "name", "type", "operator", "operator_code", "country", "launch_date",
                "decay_date", "landed", "mass", "deposits"}
FALLING_KEYS = {"norad", "cospar", "name", "type", "operator", "operator_code", "country", "perigee_km",
                "apogee_km", "epoch", "mass"}
PROVIDER_KEYS = {"provider", "country", "launches", "launches_with_data", "propellant", "deposits"}
OWNER_KEYS = {"operator", "operator_code", "country", "reentries", "reentries_with_mass", "mass", "deposits"}
LAYER_KEYS = {"lo_km", "hi_km", "source", "species", "value"}
MONTH_KEYS = {"month", "launches", "reentries", "reentries_with_mass", "reentered_mass"}
COVERAGE_KEYS = {"launches", "launches_with_data", "reentries", "reentries_with_mass", "falling",
                 "falling_with_mass"}
SOURCE_KEYS = {"id", "name", "url", "licence", "retrieved_at"}
VALUE_KEYS = {"central", "low", "high", "unit", "tier", "source"}
STATUSES = {"success", "failure", "partial", "upcoming"}
OBJECT_TYPES = {"PAY", "R/B", "DEB", "UNK"}
LAYER_SOURCES = {"launch", "reentry", "aviation"}
OMM_KEYS = {"OBJECT_NAME", "OBJECT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
            "ARG_OF_PERICENTER", "MEAN_ANOMALY", "NORAD_CAT_ID", "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"}


def validate_summary(d: dict) -> list[str]:
    errs: list[str] = []
    _keys(errs, "summary", d, SUMMARY_KEYS)
    if errs:
        return errs
    if d["schema"] != "space-summary/1":
        errs.append(f"schema is {d['schema']!r}")
    ids = set()
    for i, s in enumerate(d["sources"]):
        _keys(errs, f"sources[{i}]", s, SOURCE_KEYS)
        ids.add(s.get("id"))
    if list(d["bins_km"]) != list(BIN_EDGES_KM):
        errs.append("bins_km differs from BIN_EDGES_KM")

    def value(where: str, v, nullable: bool = True) -> None:
        if v is None:
            if not nullable:
                errs.append(f"{where}: null")
            return
        _keys(errs, where, v, VALUE_KEYS)
        if v.get("tier") not in TIERS:
            errs.append(f"{where}: tier {v.get('tier')!r}")
        if not (v.get("low", 0) <= v.get("central", 0) <= v.get("high", 0)):
            errs.append(f"{where}: low <= central <= high fails")
        for tok in str(v.get("source", "")).split("+"):
            if tok not in ids:
                errs.append(f"{where}: source {tok!r} not in sources")

    def deposits(where: str, deps: dict) -> None:
        for sp, v in deps.items():
            if sp not in SPECIES:
                errs.append(f"{where}: unknown species {sp!r}")
            value(f"{where}.{sp}", v, nullable=False)

    for i, x in enumerate(d["launches"]):
        w = f"launches[{i}]"
        _keys(errs, w, x, LAUNCH_KEYS)
        if x.get("status") not in STATUSES:
            errs.append(f"{w}: status {x.get('status')!r}")
        value(f"{w}.liftoff_mass", x.get("liftoff_mass"))
        value(f"{w}.propellant", x.get("propellant"))
        deposits(f"{w}.deposits", x.get("deposits", {}))
        if x.get("status") == "upcoming" and x.get("deposits"):
            errs.append(f"{w}: upcoming launch has deposits")
    for i, x in enumerate(d["reentries"]):
        w = f"reentries[{i}]"
        _keys(errs, w, x, REENTRY_KEYS)
        if x.get("type") not in OBJECT_TYPES:
            errs.append(f"{w}: type {x.get('type')!r}")
        value(f"{w}.mass", x.get("mass"))
        deposits(f"{w}.deposits", x.get("deposits", {}))
    for i, x in enumerate(d["falling"]):
        _keys(errs, f"falling[{i}]", x, FALLING_KEYS)
        value(f"falling[{i}].mass", x.get("mass"))
    ledger = d["ledger"]
    _keys(errs, "ledger", ledger, {"launch_providers", "reentry_owners"})
    for i, x in enumerate(ledger.get("launch_providers", [])):
        _keys(errs, f"launch_providers[{i}]", x, PROVIDER_KEYS)
        value(f"launch_providers[{i}].propellant", x.get("propellant"))
        deposits(f"launch_providers[{i}].deposits", x.get("deposits", {}))
    for i, x in enumerate(ledger.get("reentry_owners", [])):
        _keys(errs, f"reentry_owners[{i}]", x, OWNER_KEYS)
        value(f"reentry_owners[{i}].mass", x.get("mass"))
        deposits(f"reentry_owners[{i}].deposits", x.get("deposits", {}))
    for i, x in enumerate(d["layers"]):
        w = f"layers[{i}]"
        _keys(errs, w, x, LAYER_KEYS)
        if x.get("source") not in LAYER_SOURCES or x.get("species") not in SPECIES:
            errs.append(f"{w}: source/species {x.get('source')!r}/{x.get('species')!r}")
        if x.get("lo_km") not in BIN_EDGES_KM or x.get("hi_km", 0) - x.get("lo_km", 0) != 5:
            errs.append(f"{w}: not a 5 km bin")
        value(f"{w}.value", x.get("value"), nullable=False)
    for i, x in enumerate(d["monthly"]):
        w = f"monthly[{i}]"
        _keys(errs, w, x, MONTH_KEYS)
        value(f"{w}.reentered_mass", x.get("reentered_mass"))
        if (x.get("reentered_mass") is None) != (x.get("reentries_with_mass") == 0):
            errs.append(f"{w}: reentered_mass must be null exactly when reentries_with_mass is 0")
    _keys(errs, "coverage", d["coverage"], COVERAGE_KEYS)
    return errs


def validate_orbits(d: dict) -> list[str]:
    errs: list[str] = []
    _keys(errs, "orbits", d, {"schema", "sample", "generated_at", "source", "objects"})
    if errs:
        return errs
    if d["schema"] != "space-orbits/1":
        errs.append(f"schema is {d['schema']!r}")
    for i, o in enumerate(d["objects"]):
        _keys(errs, f"objects[{i}]", o, OMM_KEYS | {"group"})
        if o.get("group") not in {"falling", "station", "active"}:
            errs.append(f"objects[{i}]: group {o.get('group')!r}")
    return errs


def _keys(errs: list[str], where: str, d, required: set[str]) -> None:
    if not isinstance(d, dict):
        errs.append(f"{where}: not an object")
        return
    missing = required - d.keys()
    if missing:
        errs.append(f"{where}: missing {sorted(missing)}")
