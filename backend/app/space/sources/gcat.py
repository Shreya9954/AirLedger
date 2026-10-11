"""GCAT, Jonathan McDowell's General Catalog of Artificial Space Objects: masses and owners.

Licence CC-BY-4.0; cite as "data from GCAT (J. McDowell, planet4589.org/space/gcat)".
Files are tab-separated with space padding; the first line starting with '#' is the header.
Objects with catalogue numbers of 100000 and above are in a separate file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..cache import Cache

BASE = "https://planet4589.org/space/gcat/tsv"
CATALOGS = {
    "gcat_satcat": f"{BASE}/cat/satcat.tsv",
    "gcat_satcat100k": f"{BASE}/cat/satcat100k.tsv",
}
ORGS_URL = f"{BASE}/tables/orgs.tsv"
TTL_CAT = 24 * 3600
TTL_ORGS = 7 * 24 * 3600


@dataclass(frozen=True)
class GcatObject:
    satcat: int
    jcat: str
    name: str
    owner: str | None          # organisation code, e.g. "SPXS"
    state: str | None          # country code, e.g. "US"
    mass_kg: float | None
    dry_mass_kg: float | None
    mass_uncertain: bool       # GCAT flagged Mass with "?"
    dry_mass_uncertain: bool   # GCAT flagged DryMass with "?"

    @property
    def end_of_life_mass_kg(self) -> float | None:
        return self.dry_mass_kg if self.dry_mass_kg is not None else self.mass_kg

    @property
    def end_of_life_mass_uncertain(self) -> bool:
        return self.dry_mass_uncertain if self.dry_mass_kg is not None else self.mass_uncertain


def read_tsv(text: str) -> Iterator[dict[str, str]]:
    header = None
    for line in text.splitlines():
        if line.startswith("#"):
            if header is None:
                header = line[1:].split("\t")
            continue
        if header is None or not line.strip():
            continue
        yield dict(zip(header, (v.strip() for v in line.split("\t"))))


def parse_objects(text: str) -> dict[int, GcatObject]:
    """Objects keyed by catalogue number. Where several GCAT entries share a number, the primary
    satcat entry (JCAT starting with 'S') wins."""
    out: dict[int, GcatObject] = {}
    for r in read_tsv(text):
        sat = r.get("Satcat", "")
        if not sat.isdigit():
            continue
        n = int(sat)
        jcat = r.get("JCAT", "")
        if n in out and (out[n].jcat.startswith("S") or not jcat.startswith("S")):
            continue
        out[n] = GcatObject(
            satcat=n,
            jcat=jcat,
            name=r.get("Name", ""),
            owner=_text(r.get("Owner")),
            state=_text(r.get("State")),
            mass_kg=_num(r.get("Mass")),
            dry_mass_kg=_num(r.get("DryMass")),
            mass_uncertain="?" in r.get("MassFlag", ""),
            dry_mass_uncertain="?" in r.get("DryFlag", ""),
        )
    return out


def parse_orgs(text: str) -> dict[str, str]:
    """Organisation code -> English display name."""
    names: dict[str, str] = {}
    for r in read_tsv(text):
        code = r.get("Code", "")
        if code and code not in names:
            names[code] = _text(r.get("EName")) or _text(r.get("Name")) or code
    return names


class GcatClient:
    def __init__(self, cache: Cache):
        self.cache = cache

    def objects(self) -> dict[int, GcatObject]:
        out: dict[int, GcatObject] = {}
        for key, url in CATALOGS.items():
            out.update(parse_objects(self.cache.get(key, url, TTL_CAT).decode("utf-8")))
        return out

    def orgs(self) -> dict[str, str]:
        return parse_orgs(self.cache.get("gcat_orgs", ORGS_URL, TTL_ORGS).decode("utf-8"))


def _text(s: str | None) -> str | None:
    s = (s or "").strip()
    return None if s in ("", "-") else s


def _num(s: str | None) -> float | None:
    s = (s or "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None
