"""Emission factors, re-entry burn-up fractions and the aviation comparison. OWNED BY ROLE B.

Every factor has a low, central and high value and the id of the source it comes from; inventory.references()
resolves the ids. Where a published paper gives one central value, the range around it is ours and the note
says so. Emission and burn-up factors are tier "research": the science is still being worked out.

Main sources
  barker2024  Barker, Marais & McDowell (2024), Global 3D rocket launch and re-entry air pollutant and CO2
              emissions at the onset of the megaconstellation era. Scientific Data 11, 1079.
              Table 1 (emission indices, means of Ross & Sheaffer 2014, NASEM 2021, Maloney et al. 2022),
              Eq. 2 (black carbon afterburning), Methods (re-entry ablation and aluminium fractions after
              Schulz & Glassmeier 2021; reusable-booster entry and landing burns).
  gaia2024    Teoh et al. (2024), Global aviation contrail climate effects from 2019 to 2021 (GAIA).
              Atmos. Chem. Phys. 24, 725-744. 2019 totals for fuel and non-volatile particle (soot) mass.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .records import TIERS, ObjectRecord, Tier, Value


@dataclass(frozen=True)
class Factor:
    """A dimensionless multiplier (kg per kg, or a fraction) with its range and source."""
    central: float
    low: float
    high: float
    source: str
    note: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.low <= self.central <= self.high:
            raise ValueError(f"need 0 <= low <= central <= high, got {self.low}, {self.central}, {self.high}")

    def times(self, k: float) -> "Factor":
        return Factor(self.central * k, self.low * k, self.high * k, self.source, self.note)


def apply(v: Value, f: Factor, tier: Tier, note: str | None = None) -> Value:
    """v multiplied by f. Both are non-negative, so the range ends multiply. The tier is the less certain of
    v's and `tier`; the sources are united."""
    tier = max(v.tier, tier, key=TIERS.index)
    sources = "+".join(sorted(set(v.source.split("+")) | set(f.source.split("+"))))
    return Value(v.central * f.central, v.low * f.low, v.high * f.high, v.unit, tier, sources,
                 f.note if note is None else note)


# ---------------------------------------------------------------- launches

PROPELLANTS = ("kerosene", "methane", "propane", "hydrogen", "solid", "hypergolic")

# Black carbon (soot) per kg of propellant before afterburning in the hot plume: barker2024 Table 1, the mean
# of published values (g/kg): kerosene 22, solid 16, hypergolic 16, methane 5; hydrogen none. Very few of these
# have been measured at altitude, so we span half to twice the mean.
_HALF_TO_DOUBLE = "range half to twice the published mean (ours): rocket soot indices are rarely measured"
BC_PRIMARY: dict[str, Factor] = {
    "kerosene": Factor(0.022, 0.011, 0.044, "barker2024", f"Kerosene soot index 22 g/kg; {_HALF_TO_DOUBLE}"),
    "solid": Factor(0.016, 0.008, 0.032, "barker2024", f"Solid-motor soot index 16 g/kg; {_HALF_TO_DOUBLE}"),
    "hypergolic": Factor(0.016, 0.008, 0.032, "barker2024", f"Hypergolic soot index 16 g/kg; {_HALF_TO_DOUBLE}"),
    "methane": Factor(0.005, 0.0025, 0.010, "barker2024", f"Methane soot index 5 g/kg; {_HALF_TO_DOUBLE}"),
    # No published index for propane (Isar Aerospace Spectrum). Chemically it sits between methane and kerosene,
    # so we span the two: our assumption.
    "propane": Factor(0.0135, 0.0025, 0.044, "barker2024",
                      "No published propane index: range spans the methane and kerosene values (our assumption)"),
}

# Solid motors (ammonium perchlorate with aluminium powder): barker2024 Table 1 gives 328 g/kg alumina and
# 217 g/kg chlorine species. Our ranges come from composition: 16-20% aluminium burns to 0.30-0.38 kg Al2O3
# per kg, and 65-72% ammonium perchlorate (30% chlorine by mass) carries 0.19-0.22 kg chlorine per kg.
ALUMINA_SOLID = Factor(0.328, 0.30, 0.38, "barker2024",
                       "Solid-motor alumina 328 g/kg; range from 16-20% aluminium content (ours)")
CHLORINE_SOLID = Factor(0.217, 0.19, 0.23, "barker2024",
                        "Solid-motor chlorine species 217 g/kg, mostly HCl near the ground; range from 65-72% "
                        "ammonium perchlorate (ours)")


def bc_afterburn(h_km: float) -> float:
    """Share of primary soot that survives afterburning at altitude h: barker2024 Eq. 2. Below about 15 km the
    plume reignites in the dense air and burns 96% of the soot; by about 42 km the air is too thin and it all
    survives."""
    return max(0.04, min(1.0, 0.04 * math.exp(0.12 * (h_km - 15))))


# Reusable first stages keep propellant for a re-entry burn across 70-55 km and a landing burn from 3.3 km:
# 5.6% and 1.2% of the stage's propellant (barker2024 Methods, for Falcon; applied to other landing boosters).
ENTRY_BURN_SHARE, ENTRY_BURN_KM = 0.056, (55, 70)
LANDING_BURN_SHARE, LANDING_BURN_KM = 0.012, (0, 5)

# ---------------------------------------------------------------- re-entries

# Mass that ablates (vaporises or melts into droplets) rather than reaching the ground, by object class:
# barker2024 Methods after Schulz & Glassmeier (2021): megaconstellation payloads 100%, other payloads and
# components 80%, upper stages 65%, core stages and fairings 30%, reusable craft 0%. The ranges are ours.
ABLATION: dict[str, Factor] = {
    "megaconstellation": Factor(1.0, 0.9, 1.0, "barker2024",
                                "Megaconstellation satellites are designed to burn up completely"),
    "payload": Factor(0.80, 0.60, 0.95, "barker2024", "80% of a satellite burns up; range 60-95% (ours)"),
    "upper_stage": Factor(0.65, 0.50, 0.80, "barker2024", "65% of an upper stage burns up; range 50-80% (ours)"),
    "core_stage": Factor(0.30, 0.20, 0.40, "barker2024",
                         "30% of a core stage or fairing burns up; range 20-40% (ours)"),
    # Starship's upper stage is a steel, tiled, reusable vehicle that has reached the ocean intact on test flights.
    # barker2024 treat reusable craft as non-ablating; we allow up to 5% for lost tiles and flap damage.
    "starship": Factor(0.01, 0.0, 0.05, "barker2024",
                       "Built to survive re-entry: treated as reusable (0% in Barker et al.), with up to 5% "
                       "for heat-shield and flap damage (ours)"),
}

# Aluminium share of the ablated mass: barker2024 Methods, 40% for payloads (Schulz & Glassmeier 2021) and 70%
# for rocket stages and fairings (Jain 2023; Pisacane 2003). Ranges ours. None for Starship (stainless steel).
ALUMINIUM: dict[str, Factor | None] = {
    "megaconstellation": Factor(0.40, 0.30, 0.50, "barker2024", "40% of a satellite is aluminium; range ours"),
    "payload": Factor(0.40, 0.30, 0.50, "barker2024", "40% of a satellite is aluminium; range ours"),
    "upper_stage": Factor(0.70, 0.50, 0.80, "barker2024", "70% of a rocket stage is aluminium; range ours"),
    "core_stage": Factor(0.70, 0.50, 0.80, "barker2024", "70% of a rocket stage is aluminium; range ours"),
    "starship": None,
}

# Re-entering objects ablate across the upper to middle mesosphere, 80-60 km (barker2024 Methods).
ABLATION_KM = (60, 80)

# GCAT owner codes and name prefixes of satellites in large constellations designed for full burn-up.
MEGACONSTELLATION_OWNERS = {"SPXS", "ONEWEB", "ONEWEBN", "ONEWEBE", "KUIP", "YUANX", "ZXW"}
MEGACONSTELLATION_NAMES = ("STARLINK", "ONEWEB", "KUIPER", "QIANFAN", "HULIANWANG", "GUOWANG")


def reentry_class(obj: ObjectRecord) -> str:
    """Which ABLATION class a catalogued object falls in."""
    name = obj.name.upper()
    if name.startswith("STARSHIP"):
        return "starship"
    if obj.type == "R/B":
        # The Long March 5B core stage reaches orbit; every other catalogued rocket body is an upper stage.
        return "core_stage" if "CZ-5B" in name else "upper_stage"
    if "FAIRING" in name or "SHROUD" in name:
        return "core_stage"
    if obj.operator_code in MEGACONSTELLATION_OWNERS or name.startswith(MEGACONSTELLATION_NAMES):
        return "megaconstellation"
    return "payload"


# ---------------------------------------------------------------- aviation, for scale

# gaia2024: global aviation burned 283 Tg of fuel in 2019, about 79% of it above 25,000 ft (7.6 km).
# 2026 traffic is likely above 2019's, so the range runs higher.
AVIATION_FUEL_KG_PER_YEAR = Factor(283e9, 269e9, 325e9, "gaia2024",
                                   "Global jet fuel burn, 283 Tg in 2019; range -5% to +15% for traffic since (ours)")
# gaia2024: 21.4 Gg of non-volatile particle (soot) mass in 2019, a mean 76 mg per kg of fuel. Older inventories
# used about 33 mg/kg, which sets the low end; the high end (+50%) is ours.
AVIATION_SOOT_KG_PER_YEAR = Factor(21.4e6, 9.3e6, 32e6, "gaia2024",
                                   "Global aircraft soot, 21.4 Gg in 2019; low end uses older inventories' 33 mg/kg")
AVIATION_CRUISE_SHARE = 0.79
AVIATION_CRUISE_KM = (5, 15)   # cruise, about 7.6-13 km, straddles these two 5-km bins
AVIATION_LOW_KM = (0, 10)      # take-off, climb and descent
