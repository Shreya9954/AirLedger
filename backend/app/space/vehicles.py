"""Rocket table for the space ledger: what each vehicle burns, how much, and at what height. OWNED BY ROLE B.

Two ways to get a launch's propellant, and every figure says which one it used:

1. Published stage loads ("kg" on each stage), from the rocket's Wikipedia infobox, which quotes the maker's
   figures. Used as published, with the low end 10% lower because some propellant is left unburned.
2. Liftoff mass x propellant fraction ("share" on each stage). The liftoff mass is Launch Library 2's published
   figure for the configuration, or the Wikipedia infobox when LL2 has none. The propellant fraction is not
   guessed: it is the median and range of PROPELLANT_FRACTION_EVIDENCE below, the rockets for which both the
   stage loads and the liftoff mass are published (82-93%, median 89%). Stage shares split that total between
   stages; they only move propellant between heights and are approximate.

Burn heights are typical ascent values (booster and stage separation), rounded and not per mission. Within a
stage, propellant is spread with a simple climb shape: a stage lifting off from the pad is slow low down, so it
burns more propellant per km there ("boost": share below h = sqrt(h/H)); an upper stage climbs fast at first and
then levels off toward orbit ("upper": share below h = 1 - sqrt((H-h)/(H-h0))). Only the part below 120 km
appears in the layers chart; the rest is burned in space.
"""
from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, replace

from .factors import ENTRY_BURN_KM, ENTRY_BURN_SHARE, LANDING_BURN_KM, LANDING_BURN_SHARE, Factor
from .records import BIN_EDGES_KM, LaunchRecord, Value

TOP_KM = BIN_EDGES_KM[-1]
UNBURNED_LOW = 0.9   # low end of a published load: up to 10% left in the tanks or reserves


@dataclass(frozen=True)
class Stage:
    label: str
    propellant: str              # one of factors.PROPELLANTS
    lo_km: float                 # height at ignition
    hi_km: float                 # height at burnout or separation
    kg: float | None = None      # published propellant load of ONE unit (method 1)
    share: float | None = None   # share of the vehicle's propellant, all units together (method 2)
    count: int = 1               # identical units, e.g. strap-on boosters
    climb: str = "boost"         # "boost" from the pad, or "upper"
    reusable: bool = False       # lands propulsively: keeps propellant for entry and landing burns
    strapon: bool = False        # strap-on boosters whose number depends on the configuration


@dataclass(frozen=True)
class Vehicle:
    key: str
    name: str
    stages: tuple[Stage, ...]
    source: str                  # where the published loads or the fallback liftoff mass come from
    liftoff_kg: float | None = None
    note: str = ""


# Wikipedia articles used as sources: id -> article title.
WIKI = {
    "wp:soyuz-2": "Soyuz-2", "wp:ariane-6": "Ariane_6", "wp:vega-c": "Vega_C", "wp:h3": "H3_(rocket)",
    "wp:lvm3": "LVM3", "wp:gslv": "Geosynchronous_Satellite_Launch_Vehicle",
    "wp:pslv": "Polar_Satellite_Launch_Vehicle", "wp:sslv": "Small_Satellite_Launch_Vehicle",
    "wp:proton-m": "Proton-M", "wp:long-march-2c": "Long_March_2C", "wp:long-march-3b": "Long_March_3B",
    "wp:atlas-v": "Atlas_V", "wp:vulcan": "Vulcan_Centaur", "wp:starship": "SpaceX_Starship",
    "wp:falcon-9": "Falcon_9", "wp:falcon-heavy": "Falcon_Heavy", "wp:electron": "Rocket_Lab_Electron",
    "wp:long-march-12": "Long_March_12", "wp:long-march-12a": "Long_March_12A", "wp:long-march-6": "Long_March_6",
    "wp:long-march-6a": "Long_March_6A", "wp:long-march-6c": "Long_March_6C", "wp:long-march-7": "Long_March_7",
    "wp:long-march-8": "Long_March_8", "wp:long-march-2d": "Long_March_2D", "wp:long-march-4b": "Long_March_4B",
    "wp:long-march-2f": "Long_March_2F", "wp:long-march-5": "Long_March_5", "wp:long-march-11": "Long_March_11",
    "wp:kinetica-1": "Kinetica_1", "wp:kinetica-2": "Kinetica_2", "wp:jielong-3": "Jielong_3",
    "wp:gravity-1": "Gravity-1", "wp:nuri": "Nuri_(rocket)", "wp:pallas-1": "Pallas-1",
    "wp:tianlong-3": "Tianlong-3", "wp:firefly-alpha": "Firefly_Alpha", "wp:minotaur-iv": "Minotaur_IV",
    "wp:zhuque-2": "Zhuque-2", "wp:zhuque-3": "Zhuque-3", "wp:kuaizhou": "Kuaizhou", "wp:ceres-1": "Ceres-1",
    "wp:hyperbola-1": "Hyperbola-1", "wp:vikram-1": "Vikram-1", "wp:spectrum": "Spectrum_(rocket)",
    "wp:angara": "Angara_(rocket_family)", "wp:new-glenn": "New_Glenn", "wp:neutron": "Rocket_Lab_Neutron",
}
METHOD = "ual-method"   # this file and factors.py: propellant fraction, stage shares, burn heights


# ---------------------------------------------------------------- stage templates (method 2)

def _two_stage(prop: str, s1_hi: float = 70, first: float = 0.78, reusable: bool = False,
               upper: str | None = None) -> tuple[Stage, ...]:
    # A two-stage rocket's first stage holds roughly three-quarters of its propellant: 75% for Long March 2C
    # and 70% for Starship Block 3 from published loads. We use 78% for kerosene and methane two-stagers.
    return (Stage("first stage", prop, 0, s1_hi, share=first, reusable=reusable),
            Stage("second stage", upper or prop, s1_hi, 200, share=1 - first, climb="upper"))


def _three_stage(prop: str, upper3: str | None = None) -> tuple[Stage, ...]:
    # Split from Long March 4B's published stage figures (73% / 21% / 6%).
    return (Stage("first stage", prop, 0, 70, share=0.73),
            Stage("second stage", prop, 70, 170, share=0.21, climb="upper"),
            Stage("third stage", upper3 or prop, 170, 250, share=0.06, climb="upper"))


def _small_solid(top: str = "solid", s1_hi: float = 40) -> tuple[Stage, ...]:
    # All-solid small launchers, split like Vega C's published loads (75% / 19% / 5.5% / 0.5%). Their first
    # stages burn for about 60-75 s, so they separate lower than Vega C's (about 40 km rather than 60 km).
    return (Stage("first stage", "solid", 0, s1_hi, share=0.75),
            Stage("second stage", "solid", s1_hi, 100, share=0.19, climb="upper"),
            Stage("third stage", "solid", 100, 180, share=0.055, climb="upper"),
            Stage("fourth stage", top, 180, 250, share=0.005, climb="upper"))


def _shares_note(what: str) -> str:
    return f"Liftoff mass x propellant fraction; {what}"


# ---------------------------------------------------------------- the table

VEHICLES: dict[str, Vehicle] = {v.key: v for v in [
    # --- method 1: published stage loads
    Vehicle("soyuz2", "Soyuz-2 (2.1a / 2.1b)", (
        Stage("4 boosters (Block B-G)", "kerosene", 0, 45, kg=39_160, count=4),
        Stage("core (Block A)", "kerosene", 0, 170, kg=90_100),
        Stage("third stage (Block I)", "kerosene", 170, 230, kg=25_400, climb="upper"),
    ), "wp:soyuz-2", 312_000),
    Vehicle("ariane6", "Ariane 6 (62 / 64)", (
        Stage("P120C boosters", "solid", 0, 60, kg=141_400, count=2, strapon=True),
        Stage("core (Vulcain 2.1)", "hydrogen", 0, 160, kg=140_000),
        Stage("upper (Vinci)", "hydrogen", 160, 250, kg=32_000, climb="upper"),
    ), "wp:ariane-6", 530_000),
    Vehicle("vegac", "Vega C", (
        Stage("P120C", "solid", 0, 60, kg=141_634),
        Stage("Zefiro 40", "solid", 60, 110, kg=36_239, climb="upper"),
        Stage("Zefiro 9", "solid", 110, 180, kg=10_567, climb="upper"),
        Stage("AVUM+", "hypergolic", 180, 250, kg=740, climb="upper"),
    ), "wp:vega-c", 210_000),
    Vehicle("h3", "H3", (
        Stage("SRB-3 boosters", "solid", 0, 50, kg=67_200, count=2, strapon=True),
        Stage("first stage (LE-9)", "hydrogen", 0, 150, kg=226_000),
        Stage("second stage", "hydrogen", 150, 250, kg=24_600, climb="upper"),
    ), "wp:h3", 420_000),
    Vehicle("lvm3", "LVM3", (
        Stage("S200 boosters", "solid", 0, 60, kg=205_000, count=2),
        Stage("L110 core", "hypergolic", 40, 170, kg=116_000, climb="upper"),
        Stage("C25 upper", "hydrogen", 170, 250, kg=28_000, climb="upper"),
    ), "wp:lvm3", 640_000),
    Vehicle("gslv", "GSLV Mk II", (
        Stage("L40H boosters", "hypergolic", 0, 70, kg=42_700, count=4),
        Stage("S139 core", "solid", 0, 70, kg=138_200),
        Stage("GS2 (Vikas)", "hypergolic", 70, 130, kg=39_500, climb="upper"),
        Stage("CUS upper", "hydrogen", 130, 250, kg=12_800, climb="upper"),
    ), "wp:gslv", 414_750),
    Vehicle("pslv", "PSLV", (
        Stage("PSOM-XL boosters", "solid", 0, 35, kg=12_200, count=6, strapon=True),
        Stage("PS1", "solid", 0, 55, kg=138_200),
        Stage("PS2 (Vikas)", "hypergolic", 55, 200, kg=42_000, climb="upper"),
        Stage("PS3", "solid", 200, 300, kg=7_600, climb="upper"),
        Stage("PS4", "hypergolic", 300, 400, kg=2_500, climb="upper"),
    ), "wp:pslv", 320_000, "Stage loads for PSLV-XL; other variants change the booster count"),
    Vehicle("sslv", "SSLV", (
        Stage("SS1", "solid", 0, 50, kg=87_000),
        Stage("SS2", "solid", 50, 100, kg=7_700, climb="upper"),
        Stage("SS3", "solid", 100, 200, kg=4_500, climb="upper"),
        Stage("VTM", "hypergolic", 200, 300, kg=50, climb="upper"),
    ), "wp:sslv", 120_000),
    Vehicle("proton", "Proton-M", (
        Stage("first stage", "hypergolic", 0, 45, kg=428_300),
        Stage("second stage", "hypergolic", 45, 125, kg=157_300, climb="upper"),
        Stage("third stage", "hypergolic", 125, 170, kg=46_562, climb="upper"),
        Stage("Breeze-M", "hypergolic", 170, 250, kg=19_800, climb="upper"),
    ), "wp:proton-m", 705_000),
    Vehicle("cz2c", "Long March 2C", (
        Stage("first stage", "hypergolic", 0, 70, kg=162_706),
        Stage("second stage", "hypergolic", 70, 200, kg=54_667, climb="upper"),
    ), "wp:long-march-2c", 233_000),
    Vehicle("cz3b", "Long March 3B / 3C / 3A", (
        Stage("boosters", "hypergolic", 0, 55, kg=41_100, count=4, strapon=True),
        Stage("core", "hypergolic", 0, 75, kg=186_200),
        Stage("second stage", "hypergolic", 75, 180, kg=49_400, climb="upper"),
        Stage("third stage", "hydrogen", 180, 250, kg=18_200, climb="upper"),
    ), "wp:long-march-3b", 458_970, "Loads for 3B/E; 3C has two boosters and 3A none"),
    Vehicle("atlasv", "Atlas V", (
        Stage("GEM 63 boosters", "solid", 0, 45, kg=44_200, count=5, strapon=True),
        Stage("Common Core Booster", "kerosene", 0, 110, kg=284_089),
        Stage("Centaur III", "hydrogen", 110, 200, kg=20_830, climb="upper"),
    ), "wp:atlas-v", 590_000, "Loads for the 551; the middle digit of the configuration is the booster count"),
    Vehicle("vulcan", "Vulcan Centaur", (
        Stage("GEM 63XL boosters", "solid", 0, 50, kg=47_853, count=4, strapon=True),
        # The BE-4 core's propellant load is not published: 382 t gross mass x 0.92 stage propellant share (ours).
        Stage("core (BE-4)", "methane", 0, 110, kg=351_000),
        Stage("Centaur V", "hydrogen", 110, 200, kg=54_000, climb="upper"),
    ), "wp:vulcan", 546_700, "Core load estimated from its 382 t gross mass; booster count from VC2/VC4/VC6"),
    Vehicle("starship", "Starship", (
        Stage("Super Heavy", "methane", 0, 65, kg=3_650_000, reusable=True),
        Stage("Starship upper stage", "methane", 65, 160, kg=1_600_000, climb="upper"),
    ), "wp:starship", None, "Block 3 loads (3,650 t booster, 1,600 t ship); Block 2 is 3,250 t and 1,500 t"),

    # --- method 2: liftoff mass x propellant fraction, split by approximate stage shares
    Vehicle("falcon9", "Falcon 9", _two_stage("kerosene", s1_hi=70, reusable=True), "wp:falcon-9", 549_000,
            _shares_note("SpaceX does not publish stage loads")),
    Vehicle("falconheavy", "Falcon Heavy", (
        Stage("side boosters", "kerosene", 0, 60, share=0.60, count=2, reusable=True),
        Stage("centre core", "kerosene", 0, 90, share=0.30),
        Stage("second stage", "kerosene", 90, 200, share=0.10, climb="upper"),
    ), "wp:falcon-heavy", 1_420_000, _shares_note("three Falcon 9 cores plus one second stage")),
    Vehicle("electron", "Electron", _two_stage("kerosene", s1_hi=75), "wp:electron", 13_000,
            _shares_note("Rocket Lab does not publish stage loads")),
    Vehicle("cz12", "Long March 12", _two_stage("kerosene"), "wp:long-march-12", 433_000,
            _shares_note("two-stage split")),
    Vehicle("cz12a", "Long March 12A", _two_stage("methane", reusable=True), "wp:long-march-12a", 437_000,
            _shares_note("two-stage split")),
    Vehicle("cz6", "Long March 6", _three_stage("kerosene", upper3="hypergolic"), "wp:long-march-6", 103_000,
            _shares_note("three-stage split")),
    Vehicle("cz6a", "Long March 6A", (
        Stage("4 solid boosters", "solid", 0, 50, share=0.35, count=4),
        Stage("core", "kerosene", 0, 90, share=0.50),
        Stage("second stage", "kerosene", 90, 200, share=0.15, climb="upper"),
    ), "wp:long-march-6a", 530_000, _shares_note("booster share is approximate")),
    Vehicle("cz6c", "Long March 6C", _two_stage("kerosene"), "wp:long-march-6c", 217_000,
            _shares_note("two-stage split")),
    Vehicle("cz7", "Long March 7", (
        Stage("4 boosters", "kerosene", 0, 55, share=0.55, count=4),
        Stage("core", "kerosene", 0, 95, share=0.30),
        Stage("second stage", "kerosene", 95, 200, share=0.15, climb="upper"),
    ), "wp:long-march-7", 597_000, _shares_note("stage shares approximate")),
    Vehicle("cz7a", "Long March 7A", (
        Stage("4 boosters", "kerosene", 0, 55, share=0.53, count=4),
        Stage("core", "kerosene", 0, 95, share=0.29),
        Stage("second stage", "kerosene", 95, 170, share=0.145, climb="upper"),
        Stage("third stage", "hydrogen", 170, 250, share=0.035, climb="upper"),
    ), "wp:long-march-7", 573_000, _shares_note("stage shares approximate")),
    Vehicle("cz8", "Long March 8 / 8A", (
        Stage("2 boosters", "kerosene", 0, 55, share=0.38, count=2),
        Stage("core", "kerosene", 0, 95, share=0.50),
        Stage("second stage", "hydrogen", 95, 200, share=0.12, climb="upper"),
    ), "wp:long-march-8", 371_000, _shares_note("stage shares approximate")),
    Vehicle("cz2d", "Long March 2D", (
        Stage("first stage", "hypergolic", 0, 70, share=0.776),
        Stage("second stage", "hypergolic", 70, 200, share=0.224, climb="upper"),
    ), "wp:long-march-2d", 232_250,
        _shares_note("split from the stage figures on Wikipedia, which look like gross masses so are not used directly")),
    Vehicle("cz4b", "Long March 4B / 4C", (
        Stage("first stage", "hypergolic", 0, 70, share=0.732),
        Stage("second stage", "hypergolic", 70, 170, share=0.212, climb="upper"),
        Stage("third stage", "hypergolic", 170, 250, share=0.056, climb="upper"),
    ), "wp:long-march-4b", 249_200,
        _shares_note("split from the stage figures on Wikipedia, which look like gross masses so are not used directly")),
    Vehicle("cz2f", "Long March 2F", (
        Stage("4 boosters", "hypergolic", 0, 50, share=0.363, count=4),
        Stage("core", "hypergolic", 0, 75, share=0.435),
        Stage("second stage", "hypergolic", 75, 200, share=0.202, climb="upper"),
    ), "wp:long-march-2f", 464_000, _shares_note("split from published gross stage masses")),
    Vehicle("cz5", "Long March 5 / 5B", (
        Stage("4 boosters", "kerosene", 0, 55, share=0.744, count=4),
        Stage("core", "hydrogen", 0, 180, share=0.218),
        Stage("second stage", "hydrogen", 180, 250, share=0.038, climb="upper"),
    ), "wp:long-march-5", 851_800,
        _shares_note("core (165.3 t) and second stage (29.1 t) published, boosters take the rest")),
    Vehicle("cz11", "Long March 11", _small_solid(), "wp:long-march-11", 58_000, _shares_note("all-solid split")),
    Vehicle("kinetica1", "Kinetica 1", _small_solid(), "wp:kinetica-1", 135_000, _shares_note("all-solid split")),
    Vehicle("kinetica2", "Kinetica 2", (
        Stage("2 side boosters", "kerosene", 0, 60, share=0.60, count=2),
        Stage("core", "kerosene", 0, 90, share=0.30),
        Stage("second stage", "kerosene", 90, 200, share=0.10, climb="upper"),
    ), "wp:kinetica-2", 625_000, _shares_note("three cores plus a second stage")),
    Vehicle("jielong3", "Smart Dragon 3 (Jielong 3)", _small_solid(), "wp:jielong-3", 145_000,
            _shares_note("all-solid split")),
    Vehicle("gravity1", "Gravity-1", (
        Stage("4 solid boosters", "solid", 0, 45, share=0.60, count=4),
        Stage("first stage", "solid", 0, 70, share=0.25),
        Stage("second stage", "solid", 70, 150, share=0.11, climb="upper"),
        Stage("third stage", "solid", 150, 250, share=0.04, climb="upper"),
    ), "wp:gravity-1", 405_000, _shares_note("stage shares approximate")),
    Vehicle("kuaizhou", "Kuaizhou", _small_solid(top="hypergolic"), "wp:kuaizhou", None,
            _shares_note("all-solid split; liftoff mass only from LL2 (variants differ)")),
    Vehicle("ceres1", "Ceres-1", _small_solid(top="hypergolic"), "wp:ceres-1", None,
            _shares_note("all-solid split")),
    Vehicle("hyperbola1", "Hyperbola-1", _small_solid(), "wp:hyperbola-1", None, _shares_note("all-solid split")),
    Vehicle("minotaur4", "Minotaur IV", _small_solid(), "wp:minotaur-iv", 86_300, _shares_note("all-solid split")),
    Vehicle("vikram1", "Vikram-I", _small_solid(top="hypergolic"), "wp:vikram-1", None,
            _shares_note("all-solid split; liftoff mass not published")),
    Vehicle("zhuque2", "Zhuque-2", _two_stage("methane"), "wp:zhuque-2", None,
            _shares_note("two-stage split; liftoff mass from LL2 (variants differ)")),
    Vehicle("zhuque3", "Zhuque-3", _two_stage("methane", reusable=True), "wp:zhuque-3", None,
            _shares_note("two-stage split; liftoff mass from LL2 (variants differ)")),
    Vehicle("nuri", "Nuri (KSLV-II)", _three_stage("kerosene"), "wp:nuri", 200_000, _shares_note("three-stage split")),
    Vehicle("pallas1", "Pallas-1", _two_stage("kerosene"), "wp:pallas-1", 220_000, _shares_note("two-stage split")),
    Vehicle("tianlong3", "Tianlong-3", _two_stage("kerosene"), "wp:tianlong-3", 590_000,
            _shares_note("two-stage split")),
    Vehicle("fireflyalpha", "Firefly Alpha", _two_stage("kerosene"), "wp:firefly-alpha", 54_000,
            _shares_note("two-stage split")),
    Vehicle("spectrum", "Spectrum", _two_stage("propane"), "wp:spectrum", None,
            _shares_note("two-stage split; liftoff mass not published")),
    Vehicle("angara", "Angara", (
        Stage("4 boosters (URM-1)", "kerosene", 0, 55, share=0.62, count=4),
        Stage("core (URM-1)", "kerosene", 0, 120, share=0.24),
        Stage("second stage (URM-2)", "kerosene", 120, 200, share=0.09, climb="upper"),
        Stage("upper stage", "hypergolic", 200, 300, share=0.05, climb="upper"),
    ), "wp:angara", None, _shares_note("Angara A5 split; Angara 1.2 has no boosters")),
    Vehicle("newglenn", "New Glenn", (
        Stage("first stage", "methane", 0, 80, share=0.82, reusable=True),
        Stage("second stage", "hydrogen", 80, 200, share=0.18, climb="upper"),
    ), "wp:new-glenn", None, _shares_note("stage shares approximate; liftoff mass from LL2")),
    Vehicle("neutron", "Neutron", _two_stage("methane", reusable=True), "wp:neutron", None,
            _shares_note("two-stage split; liftoff mass from LL2")),
]}

# Launch Library 2 vehicle names -> table key. First match wins, so specific names come before families.
MATCH: list[tuple[str, str]] = [
    (r"falcon heavy", "falconheavy"), (r"falcon 9", "falcon9"), (r"starship|super heavy", "starship"),
    (r"electron|haste", "electron"), (r"neutron", "neutron"),
    (r"long march 12a|changzheng 12a", "cz12a"), (r"long march 12\b", "cz12"),
    (r"long march 6a", "cz6a"), (r"long march 6c", "cz6c"), (r"long march 6\b", "cz6"),
    (r"long march 7a", "cz7a"), (r"long march 7\b", "cz7"), (r"long march 8", "cz8"),
    (r"long march 2c", "cz2c"), (r"long march 2d", "cz2d"), (r"long march 2f", "cz2f"),
    (r"long march 3[abc]", "cz3b"), (r"long march 4[bc]", "cz4b"), (r"long march 5", "cz5"),
    (r"long march 11", "cz11"),
    (r"soyuz[ -]2", "soyuz2"), (r"ariane 6", "ariane6"), (r"vega[ -]?c\b", "vegac"),
    (r"^h3\b|h3-\d\d", "h3"), (r"lvm3|lvm-3|gslv mk\.? ?iii", "lvm3"), (r"gslv", "gslv"), (r"pslv", "pslv"),
    (r"sslv", "sslv"), (r"proton", "proton"), (r"angara", "angara"), (r"atlas v", "atlasv"),
    (r"vulcan", "vulcan"), (r"new glenn", "newglenn"),
    (r"kinetica[ -]?1|lijian[ -]?1", "kinetica1"), (r"kinetica[ -]?2|lijian[ -]?2", "kinetica2"),
    (r"smart dragon 3|jielong[ -]?3", "jielong3"), (r"gravity[ -]?1", "gravity1"), (r"kuaizhou", "kuaizhou"),
    (r"zhuque[ -]?2", "zhuque2"), (r"zhuque[ -]?3", "zhuque3"), (r"nuri|kslv[ -]?(2|ii)", "nuri"),
    (r"pallas[ -]?1", "pallas1"), (r"spectrum", "spectrum"), (r"vikram", "vikram1"), (r"ceres[ -]?1", "ceres1"),
    (r"hyperbola[ -]?1", "hyperbola1"), (r"tianlong[ -]?3", "tianlong3"), (r"firefly alpha|^alpha$", "fireflyalpha"),
    (r"minotaur iv", "minotaur4"),
]
_MATCH = [(re.compile(p), k) for p, k in MATCH]


def match(vehicle: str, families: tuple[str, ...] = ()) -> str | None:
    for text in (vehicle, *families):
        t = text.lower().strip()
        for rx, key in _MATCH:
            if rx.search(t):
                return key
    return None


def stages_for(key: str, vehicle: str) -> tuple[Stage, ...]:
    """The table's stages adjusted for the configuration named in `vehicle` (booster counts, extra stages)."""
    v, name = VEHICLES[key], vehicle.lower()

    def boosters(n: int) -> tuple[Stage, ...]:  # set the strap-on booster count; 0 drops them
        return tuple(replace(s, count=n) if s.strapon else s for s in v.stages if n > 0 or not s.strapon)

    if key == "ariane6":
        return boosters(4 if "64" in name else 2)
    if key == "h3" and (m := re.search(r"h3-(\d)(\d)", name)):
        return boosters(int(m.group(2)))
    if key == "atlasv" and (m := re.search(r"([n\d])(\d)(\d)\b", name)):
        return boosters(int(m.group(2)))
    if key == "vulcan" and (m := re.search(r"vc(\d)", name)):
        return boosters(int(m.group(1)))
    if key == "pslv":
        for tag, n in (("-xl", 6), ("-ql", 4), ("-dl", 2), ("-ca", 0), (" xl", 6), (" ql", 4), (" dl", 2), (" ca", 0)):
            if tag in name:
                return boosters(n)
        return v.stages
    if key == "cz3b":
        return boosters(0 if "3a" in name else 2 if "3c" in name else 4)
    if key == "soyuz2" and "fregat" in name:
        load = 6_650 if "fregat-m" in name else 5_307
        return v.stages + (Stage("Fregat upper stage", "hypergolic", 230, 300, kg=load, climb="upper"),)
    if key == "starship" and not re.search(r"v3|block 3", name):
        return (replace(v.stages[0], kg=3_250_000), replace(v.stages[1], kg=1_500_000))
    if key == "cz5" and "5b" in name:
        return (replace(v.stages[0], share=0.78), replace(v.stages[1], share=0.22))
    if key == "angara" and "1.2" in name:
        return (Stage("first stage (URM-1)", "kerosene", 0, 100, share=0.85),
                Stage("second stage (URM-2)", "kerosene", 100, 200, share=0.15, climb="upper"))
    return v.stages


# ---------------------------------------------------------------- propellant fraction evidence

# Rockets with both published stage loads and a published liftoff mass (all Wikipedia infoboxes):
# (name, source id, total propellant kg, liftoff kg). PROPELLANT_FRACTION is derived from these, not chosen.
PROPELLANT_FRACTION_EVIDENCE: list[tuple[str, str, float, float]] = [
    ("Soyuz-2.1b", "wp:soyuz-2", 4 * 39_160 + 90_100 + 25_400, 312_000),
    ("Ariane 62", "wp:ariane-6", 2 * 141_400 + 140_000 + 32_000, 530_000),
    ("Vega C", "wp:vega-c", 141_634 + 36_239 + 10_567 + 740, 210_000),
    ("H3-22", "wp:h3", 2 * 67_200 + 226_000 + 24_600, 420_000),
    ("LVM3", "wp:lvm3", 2 * 205_000 + 116_000 + 28_000, 640_000),
    ("GSLV Mk II", "wp:gslv", 4 * 42_700 + 138_200 + 39_500 + 12_800, 414_750),
    ("PSLV-XL", "wp:pslv", 6 * 12_200 + 138_200 + 42_000 + 7_600 + 2_500, 320_000),
    ("SSLV", "wp:sslv", 87_000 + 7_700 + 4_500 + 50, 120_000),
    ("Proton-M / Breeze-M", "wp:proton-m", 428_300 + 157_300 + 46_562 + 19_800, 705_000),
    ("Long March 2C", "wp:long-march-2c", 162_706 + 54_667, 233_000),
    ("Long March 3B/E", "wp:long-march-3b", 4 * 41_100 + 186_200 + 49_400 + 18_200, 458_970),
    ("Atlas V 551", "wp:atlas-v", 5 * 44_200 + 284_089 + 20_830, 590_000),
]
_fractions = [p / m for _, _, p, m in PROPELLANT_FRACTION_EVIDENCE]
PROPELLANT_FRACTION = Factor(
    round(statistics.median(_fractions), 3), round(min(_fractions), 3), round(max(_fractions), 3), METHOD,
    f"Propellant is {min(_fractions):.0%}-{max(_fractions):.0%} of liftoff mass across "
    f"{len(_fractions)} rockets with published stage loads (median {statistics.median(_fractions):.0%})")


# ---------------------------------------------------------------- plan and height profile

def plan(launch: LaunchRecord) -> list[tuple[Stage, Value]] | None:
    """Each stage group with the propellant it burns (all units, all heights), or None if unknown."""
    key = match(launch.vehicle, launch.vehicle_families)
    if key is None:
        return None
    v, stages = VEHICLES[key], stages_for(key, launch.vehicle)
    out: list[tuple[Stage, Value]] = []
    if all(s.kg is not None for s in stages):
        note = f"{v.name}: published propellant loads; up to 10% may go unburned" + (f". {v.note}" if v.note else "")
        for s in stages:
            kg = s.kg * s.count
            out.append((s, Value(kg, kg * UNBURNED_LOW, kg, "kg", "estimate", v.source, note)))
    else:
        if launch.liftoff_mass_kg:
            liftoff = Value.fact(launch.liftoff_mass_kg, "kg", "ll2")
        elif v.liftoff_kg:
            liftoff = Value.fact(v.liftoff_kg, "kg", v.source)
        else:
            return None
        f = PROPELLANT_FRACTION
        total = Value(liftoff.central * f.central, liftoff.low * f.low, liftoff.high * f.high, "kg", "estimate",
                      f"{liftoff.source}+{METHOD}", f"{v.name}: {v.note or 'liftoff mass x propellant fraction'}")
        shares = sum(s.share for s in stages)
        out = [(s, total.scale(s.share / shares)) for s in stages]
    if launch.status == "failure":
        # Where in the flight it failed isn't in the data, so the low end goes to zero.
        out = [(s, Value(p.central, 0.0, p.high, p.unit, p.tier, p.source,
                         p.note + "; launch failed, so some propellant may not have burned")) for s, p in out]
    return out


def bins(stage: Stage) -> list[tuple[int, int, float]]:
    """(lo_km, hi_km, share of the stage's propellant) for each 5-km bin below TOP_KM that the stage burns in.
    Shares add up to the part of the stage's burn below TOP_KM, so up to 1."""
    a, b = stage.lo_km, stage.hi_km
    ascent = 1.0
    extra: list[tuple[tuple[int, int], float]] = []
    if stage.reusable:
        ascent -= ENTRY_BURN_SHARE + LANDING_BURN_SHARE
        extra = [(ENTRY_BURN_KM, ENTRY_BURN_SHARE), (LANDING_BURN_KM, LANDING_BURN_SHARE)]

    def below(h: float) -> float:  # share of the ascent burn below height h
        if h <= a:
            return 0.0
        if h >= b:
            return 1.0
        x = (h - a) / (b - a)
        return math.sqrt(x) if stage.climb == "boost" else 1 - math.sqrt(1 - x)

    step = BIN_EDGES_KM[1] - BIN_EDGES_KM[0]
    out: dict[int, float] = {}
    for lo in BIN_EDGES_KM[:-1]:
        share = ascent * (below(lo + step) - below(lo))
        for (elo, ehi), s in extra:   # entry and landing burns, spread evenly over their heights
            overlap = max(0, min(lo + step, ehi) - max(lo, elo))
            share += s * overlap / (ehi - elo)
        if share > 1e-9:
            out[lo] = share
    return [(lo, lo + step, s) for lo, s in out.items()]


def references() -> list[dict]:
    ids = {v.source for v in VEHICLES.values()} | {sid for _, sid, _, _ in PROPELLANT_FRACTION_EVIDENCE}
    refs = [{"id": sid, "name": f"Wikipedia: {WIKI[sid].replace('_', ' ')} (infobox, retrieved 2026-10-11)",
             "url": f"https://en.wikipedia.org/wiki/{WIKI[sid]}", "licence": "CC BY-SA 4.0"} for sid in sorted(ids)]
    refs.append({"id": METHOD, "name": "Upper Air Ledger estimation method: propellant fraction, stage shares and "
                                      "burn heights (backend/app/space/vehicles.py, factors.py)",
                 "url": "https://github.com/Shreya9954/Contrails", "licence": ""})
    return refs
