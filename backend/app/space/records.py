"""Shared types for the space ledger: the interface between data plumbing (role A) and the numbers (role B).

Frozen contract. Change it only by agreement (see docs/space-ledger.md, "Changing a contract").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Literal

Tier = Literal["fact", "estimate", "research"]
TIERS: tuple[Tier, ...] = ("fact", "estimate", "research")  # least to most uncertain

# Altitude bins for the "layers of the sky" view, in km. Deposits must start and end on these edges.
BIN_EDGES_KM: tuple[int, ...] = tuple(range(0, 125, 5))

# Every quantity is a mass in kg of the named species.
SPECIES: tuple[str, ...] = (
    "propellant",     # propellant burned (launch)
    "black_carbon",   # soot (launch, mostly kerosene engines)
    "alumina",        # aluminium oxide particles (launch, solid motors)
    "chlorine",       # chlorine species (launch, solid motors)
    "ablated_mass",   # spacecraft mass vaporised on re-entry
    "aluminium",      # aluminium within the ablated mass
)


@dataclass(frozen=True)
class Value:
    """A number with its range, unit, certainty tier and where it came from.

    fact      taken directly from a catalogue (counts, dates, catalogued masses)
    estimate  arithmetic on facts plus engineering data, with stated assumptions
    research  depends on emission factors that are still being studied
    """
    central: float
    low: float
    high: float
    unit: str
    tier: Tier
    source: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise ValueError(f"unknown tier {self.tier!r}")
        if not self.low <= self.central <= self.high:
            raise ValueError(f"need low <= central <= high, got {self.low}, {self.central}, {self.high}")

    @classmethod
    def fact(cls, x: float, unit: str, source: str, note: str = "") -> "Value":
        return cls(x, x, x, unit, "fact", source, note)

    def __add__(self, other: "Value") -> "Value":
        if self.unit != other.unit:
            raise ValueError(f"cannot add {self.unit} to {other.unit}")
        tier = max(self.tier, other.tier, key=TIERS.index)
        sources = sorted(set(self.source.split("+")) | set(other.source.split("+")))
        note = self.note if self.note == other.note else ""
        return Value(self.central + other.central, self.low + other.low, self.high + other.high,
                     self.unit, tier, "+".join(sources), note)

    def scale(self, k: float) -> "Value":
        if k < 0:
            raise ValueError("scale factor must be non-negative")
        return Value(self.central * k, self.low * k, self.high * k, self.unit, self.tier, self.source, self.note)

    def to_json(self) -> dict:
        d = {"central": _r(self.central), "low": _r(self.low), "high": _r(self.high),
             "unit": self.unit, "tier": self.tier, "source": self.source}
        if self.note:
            d["note"] = self.note
        return d


def vsum(values: Iterable[Value | None]) -> Value | None:
    """Sum, skipping None. Ranges add end to end, so the result is a conservative envelope."""
    total = None
    for v in values:
        if v is not None:
            total = v if total is None else total + v
    return total


def _r(x: float) -> float:
    return round(x, 3)


@dataclass(frozen=True)
class Deposit:
    """Mass of one species left between lo_km and hi_km. lo_km and hi_km must be BIN_EDGES_KM values;
    a deposit spanning several bins is spread evenly across them when aggregated."""
    species: str
    lo_km: int
    hi_km: int
    value: Value

    def __post_init__(self) -> None:
        if self.species not in SPECIES:
            raise ValueError(f"unknown species {self.species!r}")
        if self.lo_km not in BIN_EDGES_KM or self.hi_km not in BIN_EDGES_KM or self.lo_km >= self.hi_km:
            raise ValueError(f"bad altitude range {self.lo_km}-{self.hi_km} km")
        if self.value.unit != "kg":
            raise ValueError("deposits are in kg")


@dataclass(frozen=True)
class LaunchRecord:
    """One orbital launch attempt, from Launch Library 2."""
    id: str                              # "ll2:<uuid>"
    name: str
    net: datetime                        # UTC
    status: str                          # success | failure | partial | upcoming
    provider: str                        # launch service provider, e.g. "SpaceX"
    country: str | None                  # ISO 3166 alpha-3 of the provider
    vehicle: str                         # configuration full name, e.g. "Falcon 9 Block 5"
    vehicle_families: tuple[str, ...] = ()   # e.g. ("Falcon", "Falcon 9")
    orbit: str | None = None             # target orbit abbreviation, e.g. "LEO", "SSO", "GTO"
    pad_name: str | None = None
    pad_location: str | None = None
    pad_lat: float | None = None
    pad_lon: float | None = None
    liftoff_mass_kg: float | None = None  # published liftoff mass of this configuration


@dataclass(frozen=True)
class ObjectRecord:
    """One catalogued object (CelesTrak SATCAT joined to GCAT by NORAD number)."""
    norad: int
    cospar: str                          # international designator, e.g. "2020-001A"
    name: str
    type: str                            # PAY | R/B | DEB | UNK
    operator: str                        # display name from GCAT organisations, else the code
    operator_code: str | None            # GCAT Owner code, e.g. "SPXS"
    country: str | None                  # GCAT State code, e.g. "US"
    launch_date: date | None
    decay_date: date | None              # None while in orbit
    perigee_km: float | None = None
    apogee_km: float | None = None
    inclination_deg: float | None = None
    mass_kg: float | None = None         # GCAT Mass
    dry_mass_kg: float | None = None     # GCAT DryMass
    mass_uncertain: bool = False         # GCAT flagged the mass with "?"
    tags: tuple[str, ...] = field(default=())  # "landed": came down intact and was recovered (SATCAT ORBIT_TYPE LAN)

    @property
    def end_of_life_mass_kg(self) -> float | None:
        """Mass expected at re-entry: dry mass when known (propellant used up), else catalogued mass."""
        return self.dry_mass_kg if self.dry_mass_kg is not None else self.mass_kg
