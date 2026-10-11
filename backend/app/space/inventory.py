"""What each launch and re-entry leaves in the atmosphere, by altitude. OWNED BY ROLE B.

Implements Contract 1 (SPACE_HANDOFF.md). The data lives in vehicles.py (rockets) and factors.py (emission and
burn-up factors, aviation); this module turns a LaunchRecord or ObjectRecord into Values and Deposits.

Tiers: catalogued masses stay "fact"; propellant and ablated mass are "estimate" (arithmetic on facts plus
engineering data); soot, alumina, chlorine and aluminium are "research" (their factors are still being studied).
Pure functions: no network, deterministic. Unknown rockets and objects give None or [].
"""
from __future__ import annotations

from . import factors as F
from . import vehicles as V
from .records import Deposit, LaunchRecord, ObjectRecord, Value, vsum

_GLOBAL_SOURCES = [
    {"id": "barker2024", "name": "Barker, Marais & McDowell (2024), Global 3D rocket launch and re-entry air "
                                 "pollutant and CO2 emissions at the onset of the megaconstellation era, "
                                 "Scientific Data 11, 1079",
     "url": "https://doi.org/10.1038/s41597-024-03910-z", "licence": "CC BY 4.0"},
    {"id": "gaia2024", "name": "Teoh et al. (2024), Global aviation contrail climate effects from 2019 to 2021, "
                               "Atmos. Chem. Phys. 24, 725-744",
     "url": "https://doi.org/10.5194/acp-24-725-2024", "licence": "CC BY 4.0"},
]


def match_vehicle(launch: LaunchRecord) -> str | None:
    """Key into the vehicle table for this launch's rocket, or None if the rocket isn't covered."""
    return V.match(launch.vehicle, launch.vehicle_families)


def launch_propellant(launch: LaunchRecord) -> Value | None:
    """Total propellant burned by the launch at all heights (kg), or None if unknown."""
    p = V.plan(launch)
    return vsum(v for _, v in p) if p else None


def launch_deposits(launch: LaunchRecord) -> list[Deposit]:
    """Propellant, soot, alumina and chlorine left below 120 km, per 5-km bin. Empty if unknown."""
    out: list[Deposit] = []
    for stage, prop in V.plan(launch) or []:
        bc = F.BC_PRIMARY.get(stage.propellant)
        for lo, hi, share in V.bins(stage):
            p = prop.scale(share)
            out.append(Deposit("propellant", lo, hi, p))
            if bc is not None:
                survive = F.bc_afterburn((lo + hi) / 2)
                out.append(Deposit("black_carbon", lo, hi, F.apply(
                    p, bc.times(survive), "research",
                    f"{bc.note}; afterburning in the plume removes up to 96% below about 40 km (Barker et al. Eq. 2)")))
            if stage.propellant == "solid":
                out.append(Deposit("alumina", lo, hi, F.apply(p, F.ALUMINA_SOLID, "research")))
                out.append(Deposit("chlorine", lo, hi, F.apply(p, F.CHLORINE_SOLID, "research")))
    return out


def reentry_deposits(obj: ObjectRecord) -> list[Deposit]:
    """Ablated mass and the aluminium in it, between 60 and 80 km. Empty if unknown, massless or landed."""
    m = obj.end_of_life_mass_kg
    if not m or m <= 0 or "landed" in obj.tags:
        # Recovered capsules come down intact: barker2024 treat reusable craft as non-ablating.
        return []
    kind = F.reentry_class(obj)
    lo, hi = F.ABLATION_KM
    mass = Value.fact(m, "kg", "gcat")
    ablated = F.apply(mass, F.ABLATION[kind], "estimate")
    out = [Deposit("ablated_mass", lo, hi, ablated)]
    al = F.ALUMINIUM[kind]
    if al is not None:
        out.append(Deposit("aluminium", lo, hi, F.apply(ablated, al, "research", f"{F.ABLATION[kind].note}; {al.note}")))
    return out


def aviation_context(days: int) -> list[Deposit]:
    """Global aviation over `days` days, for scale: jet fuel (as "propellant") and soot (as "black_carbon")."""
    k = days / 365
    cruise, low = F.AVIATION_CRUISE_SHARE, 1 - F.AVIATION_CRUISE_SHARE
    out = []
    for species, f, tier in (("propellant", F.AVIATION_FUEL_KG_PER_YEAR, "estimate"),
                             ("black_carbon", F.AVIATION_SOOT_KG_PER_YEAR, "research")):
        total = Value(f.central * k, f.low * k, f.high * k, "kg", tier, f.source, f.note)
        out.append(Deposit(species, *F.AVIATION_CRUISE_KM, total.scale(cruise)))
        out.append(Deposit(species, *F.AVIATION_LOW_KM, total.scale(low)))
    return out


def references() -> list[dict]:
    """One entry per source id used in Value.source by this module: {"id", "name", "url"} (plus "licence")."""
    return _GLOBAL_SOURCES + V.references()
