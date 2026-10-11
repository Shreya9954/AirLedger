"""Assemble the space ledger: fetch through the cache, join the catalogues, ask role B's inventory for
deposits, and aggregate into Contract 2 (space-summary/1 and space-orbits/1, see SPACE_HANDOFF.md).

gather_* functions touch the network (through the cache); build_* functions are pure.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from types import ModuleType

from . import inventory as default_inventory
from .cache import Cache
from .records import SPECIES, BIN_EDGES_KM, Deposit, LaunchRecord, ObjectRecord, Value, vsum
from .sources.celestrak import CelestrakClient, SatcatRow, omm_perigee_apogee
from .sources.gcat import GcatClient, GcatObject
from .sources.launchlib import LaunchLibClient

log = logging.getLogger(__name__)

UPCOMING_DAYS = 14
MONTHLY_FROM = date(2015, 1, 1)
BIN_KM = BIN_EDGES_KM[1] - BIN_EDGES_KM[0]
OBJECT_TYPES = {"PAY", "R/B", "DEB", "UNK"}

REGIONS = [
    {"id": "troposphere", "name": "Troposphere", "lo_km": 0, "hi_km": 12},
    {"id": "stratosphere", "name": "Stratosphere", "lo_km": 12, "hi_km": 50},
    {"id": "mesosphere", "name": "Mesosphere", "lo_km": 50, "hi_km": 85},
    {"id": "thermosphere", "name": "Thermosphere", "lo_km": 85, "hi_km": 120},
]

SOURCES = {
    "ll2": {"id": "ll2", "name": "Launch Library 2 (The Space Devs)", "url": "https://thespacedevs.com/llapi",
            "licence": "The Space Devs terms of use"},
    "celestrak": {"id": "celestrak", "name": "CelesTrak SATCAT and GP data (T.S. Kelso)",
                  "url": "https://celestrak.org", "licence": "CelesTrak usage policy"},
    "gcat": {"id": "gcat", "name": "GCAT (J. McDowell)", "url": "https://planet4589.org/space/gcat",
             "licence": "CC-BY-4.0", "citation": "data from GCAT (J. McDowell, planet4589.org/space/gcat)"},
}


@dataclass
class Inputs:
    satcat: list[SatcatRow]
    gcat: dict[int, GcatObject]
    orgs: dict[str, str]
    decaying: list[dict]
    launches: list[LaunchRecord]
    retrieved: dict[str, float | None] = field(default_factory=dict)


# ---------------------------------------------------------------- network (through the cache)

def gather(cache: Cache, now: datetime, days: int) -> Inputs:
    cel, gc, ll = CelestrakClient(cache), GcatClient(cache), LaunchLibClient(cache)
    # Two fixed look-back sizes so different `days` values share LL2 pages (15 requests an hour).
    since = datetime.combine(now.date() - timedelta(days=90 if days <= 90 else 365), time(), timezone.utc)
    launches = ll.previous(since) + ll.upcoming(now + timedelta(days=UPCOMING_DAYS))
    return Inputs(
        satcat=cel.satcat(),
        gcat=gc.objects(),
        orgs=gc.orgs(),
        decaying=cel.gp(special="DECAYING"),
        launches=launches,
        retrieved={"celestrak": cache.fetched_at("celestrak_satcat"),
                   "gcat": cache.fetched_at("gcat_satcat"),
                   "ll2": cache.fetched_at(f"ll2_previous_{since:%Y%m%d}_p0")},
    )


def summary(cache: Cache, days: int = 90, now: datetime | None = None, inv: ModuleType = default_inventory) -> dict:
    now = now or datetime.now(timezone.utc)
    return build_summary(gather(cache, now, days), now, days, inv)


def orbits(cache: Cache, limit: int = 3000, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cel = CelestrakClient(cache)
    return build_orbits(cel.gp(special="DECAYING"), cel.gp(group="stations"), cel.gp(group="active"), limit, now)


# ---------------------------------------------------------------- pure assembly

def object_record(row: SatcatRow, g: GcatObject | None, orgs: dict[str, str]) -> ObjectRecord:
    code = g.owner if g else None
    return ObjectRecord(
        norad=row.norad, cospar=row.cospar, name=row.name,
        type=row.type if row.type in OBJECT_TYPES else "UNK",
        operator=orgs.get(code, code) if code else (row.owner or "Unknown"),
        operator_code=code,
        country=g.state if g else None,
        launch_date=row.launch_date, decay_date=row.decay_date,
        perigee_km=row.perigee_km, apogee_km=row.apogee_km, inclination_deg=row.inclination_deg,
        mass_kg=g.mass_kg if g else None,
        dry_mass_kg=g.dry_mass_kg if g else None,
        mass_uncertain=g.end_of_life_mass_uncertain if g else False,
        tags=("landed",) if row.orbit_type == "LAN" else (),
    )


def mass_value(o: ObjectRecord) -> Value | None:
    m = o.end_of_life_mass_kg
    if m is None:
        return None
    return Value.fact(m, "kg", "gcat", "GCAT marks this mass as uncertain" if o.mass_uncertain else "")


def spread(d: Deposit) -> list[tuple[int, Value]]:
    """A deposit split evenly across the 5 km bins it spans: [(bin_lo_km, value)]."""
    n = (d.hi_km - d.lo_km) // BIN_KM
    return [(d.lo_km + i * BIN_KM, d.value.scale(1 / n)) for i in range(n)]


def by_species(deps: list[Deposit]) -> dict[str, dict]:
    grouped: dict[str, list[Value]] = defaultdict(list)
    for d in deps:
        grouped[d.species].append(d.value)
    return {sp: vsum(grouped[sp]).to_json() for sp in SPECIES if sp in grouped}


def build_summary(inputs: Inputs, now: datetime, days: int, inv: ModuleType = default_inventory) -> dict:
    end = now.date()
    start = end - timedelta(days=days)
    rows_by_norad = {r.norad: r for r in inputs.satcat}
    layer_deps: list[tuple[str, Deposit]] = []

    # Re-entries in the window, newest first. Objects that landed intact (recovered capsules) are listed
    # but kept out of the ledgers, monthly totals and coverage, which are about mass that came down to burn up.
    reentries, owners = [], defaultdict(list)
    for row in sorted((r for r in inputs.satcat if r.decay_date and start <= r.decay_date <= end),
                      key=lambda r: (r.decay_date, r.norad), reverse=True):
        o = object_record(row, inputs.gcat.get(row.norad), inputs.orgs)
        m = mass_value(o)
        deps = _call(inv.reentry_deposits, [], o)
        layer_deps += [("reentry", d) for d in deps]
        landed = "landed" in o.tags
        if not landed:
            owners[o.operator_code or o.operator].append((o, m, deps))
        reentries.append({
            "norad": o.norad, "cospar": o.cospar, "name": o.name, "type": o.type,
            "operator": o.operator, "operator_code": o.operator_code, "country": o.country,
            "launch_date": _d(o.launch_date), "decay_date": _d(o.decay_date), "landed": landed,
            "mass": m.to_json() if m else None, "deposits": by_species(deps),
        })

    # Launches in the window plus the next UPCOMING_DAYS, newest first.
    horizon = now + timedelta(days=UPCOMING_DAYS)
    seen, chosen = set(), []
    for L in inputs.launches:
        if L.id in seen:
            continue
        seen.add(L.id)
        if (L.status == "upcoming" and L.net <= horizon) or (L.status != "upcoming" and start <= L.net.date() <= end):
            chosen.append(L)
    launches, providers = [], defaultdict(list)
    for L in sorted(chosen, key=lambda x: x.net, reverse=True):
        prop = _call(inv.launch_propellant, None, L)
        deps = [] if L.status == "upcoming" else _call(inv.launch_deposits, [], L)
        if L.status != "upcoming":
            layer_deps += [("launch", d) for d in deps]
            providers[L.provider].append((L, prop, deps))
        launches.append({
            "id": L.id, "name": L.name, "net": _iso(L.net), "status": L.status,
            "provider": L.provider, "country": L.country, "vehicle": L.vehicle,
            "vehicle_key": _call(inv.match_vehicle, None, L), "orbit": L.orbit,
            "pad": {"name": L.pad_name, "location": L.pad_location, "lat": L.pad_lat, "lon": L.pad_lon},
            "liftoff_mass": Value.fact(L.liftoff_mass_kg, "kg", "ll2",
                                       "Published liftoff mass for this rocket configuration").to_json()
            if L.liftoff_mass_kg else None,
            "propellant": prop.to_json() if prop else None,
            "deposits": by_species(deps),
        })

    # Objects still in orbit on CelesTrak's decaying list, lowest perigee first.
    falling = []
    for omm in inputs.decaying:
        row = rows_by_norad.get(int(omm["NORAD_CAT_ID"]))
        if row is None or row.decay_date is not None:
            continue
        o = object_record(row, inputs.gcat.get(row.norad), inputs.orgs)
        perigee, apogee = omm_perigee_apogee(omm)
        m = mass_value(o)
        falling.append({
            "norad": o.norad, "cospar": o.cospar, "name": o.name, "type": o.type,
            "operator": o.operator, "operator_code": o.operator_code, "country": o.country,
            "perigee_km": round(perigee, 1), "apogee_km": round(apogee, 1),
            "epoch": _omm_epoch(omm["EPOCH"]), "mass": m.to_json() if m else None,
        })
    falling.sort(key=lambda f: f["perigee_km"])

    aviation = _call(inv.aviation_context, [], days)
    happened = [x for items in providers.values() for x in items]
    reentry_items = [x for items in owners.values() for x in items]
    return {
        "schema": "space-summary/1",
        "sample": False,
        "generated_at": _iso(now),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "sources": _sources(inputs.retrieved, _call(inv.references, [])),
        "bins_km": list(BIN_EDGES_KM),
        "regions": REGIONS,
        "launches": launches,
        "reentries": reentries,
        "falling": falling,
        "ledger": {"launch_providers": _provider_rows(providers), "reentry_owners": _owner_rows(owners)},
        "layers": _layers(layer_deps + [("aviation", d) for d in aviation]),
        "monthly": _monthly(inputs, end),
        "coverage": {
            "launches": len(happened),
            "launches_with_data": sum(1 for _, p, _ in happened if p is not None),
            "reentries": len(reentry_items),
            "reentries_with_mass": sum(1 for _, m, _ in reentry_items if m is not None),
            "falling": len(falling),
            "falling_with_mass": sum(1 for f in falling if f["mass"] is not None),
        },
    }


def build_orbits(decaying: list[dict], stations: list[dict], active: list[dict], limit: int, now: datetime) -> dict:
    """Every falling object, the stations, then an evenly spread, deterministic sample of the active
    catalogue up to `limit` objects in total."""
    objects, seen = [], set()

    def add(o: dict, group: str) -> None:
        n = int(o["NORAD_CAT_ID"])
        if n not in seen:
            seen.add(n)
            objects.append(dict(o, group=group))

    for o in decaying:
        add(o, "falling")
    for o in stations:
        add(o, "station")
    rest = sorted((o for o in active if int(o["NORAD_CAT_ID"]) not in seen), key=lambda o: int(o["NORAD_CAT_ID"]))
    room = max(0, limit - len(objects))
    if len(rest) > room:
        rest = [rest[int(i * len(rest) / room)] for i in range(room)]
    for o in rest:
        add(o, "active")
    return {"schema": "space-orbits/1", "sample": False, "generated_at": _iso(now), "source": "celestrak",
            "objects": objects}


def _provider_rows(providers: dict[str, list]) -> list[dict]:
    rows = []
    for name, items in providers.items():
        prop = vsum(p for _, p, _ in items)
        rows.append({
            "provider": name,
            "country": next((L.country for L, _, _ in items if L.country), None),
            "launches": len(items),
            "launches_with_data": sum(1 for _, p, _ in items if p is not None),
            "propellant": prop.to_json() if prop else None,
            "deposits": by_species([d for _, _, deps in items for d in deps]),
        })
    return sorted(rows, key=lambda r: (-(r["propellant"] or {}).get("central", -1), -r["launches"], r["provider"]))


def _owner_rows(owners: dict[str, list]) -> list[dict]:
    rows = []
    for _, items in owners.items():
        o = items[0][0]
        mass = vsum(m for _, m, _ in items)
        rows.append({
            "operator": o.operator, "operator_code": o.operator_code, "country": o.country,
            "reentries": len(items),
            "reentries_with_mass": sum(1 for _, m, _ in items if m is not None),
            "mass": mass.to_json() if mass else None,
            "deposits": by_species([d for _, _, deps in items for d in deps]),
        })
    return sorted(rows, key=lambda r: (-(r["mass"] or {}).get("central", -1), -r["reentries"], r["operator"]))


def _layers(tagged: list[tuple[str, Deposit]]) -> list[dict]:
    cells: dict[tuple[str, str, int], list[Value]] = defaultdict(list)
    for src, d in tagged:
        for lo, v in spread(d):
            cells[(src, d.species, lo)].append(v)
    out = []
    for (src, sp, lo), vals in sorted(cells.items(), key=lambda kv: (kv[0][0], SPECIES.index(kv[0][1]), kv[0][2])):
        total = vsum(vals)
        if total.high > 0:
            out.append({"lo_km": lo, "hi_km": lo + BIN_KM, "source": src, "species": sp, "value": total.to_json()})
    return out


def _monthly(inputs: Inputs, end: date) -> list[dict]:
    months: dict[str, dict] = {}
    y, m = MONTHLY_FROM.year, MONTHLY_FROM.month
    while (y, m) <= (end.year, end.month):
        months[f"{y:04d}-{m:02d}"] = {"launches": set(), "reentries": 0, "with_mass": 0, "mass": 0.0}
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    for row in inputs.satcat:
        if row.launch_date and MONTHLY_FROM <= row.launch_date <= end and len(row.cospar) >= 8:
            months[row.launch_date.strftime("%Y-%m")]["launches"].add(row.cospar[:8])
        if row.decay_date and MONTHLY_FROM <= row.decay_date <= end and row.orbit_type != "LAN":
            mm = months[row.decay_date.strftime("%Y-%m")]
            mm["reentries"] += 1
            g = inputs.gcat.get(row.norad)
            mass = g.end_of_life_mass_kg if g else None
            if mass is not None:
                mm["with_mass"] += 1
                mm["mass"] += mass
    return [{
        "month": k, "launches": len(v["launches"]), "reentries": v["reentries"],
        "reentries_with_mass": v["with_mass"],
        "reentered_mass": Value.fact(v["mass"], "kg", "gcat").to_json() if v["with_mass"] else None,
    } for k, v in months.items()]


def _sources(retrieved: dict[str, float | None], refs: list[dict]) -> list[dict]:
    out = []
    for sid, s in SOURCES.items():
        t = retrieved.get(sid)
        out.append(dict(s, retrieved_at=_iso(datetime.fromtimestamp(t, timezone.utc)) if t else None))
    for r in refs:
        out.append({"id": r["id"], "name": r.get("name", r["id"]), "url": r.get("url", ""),
                    "licence": r.get("licence", ""), "retrieved_at": None})
    return out


def _call(fn, default, *args):
    """Role B's functions must not take the whole ledger down: log and fall back to 'unknown'."""
    try:
        result = fn(*args)
    except Exception:
        log.exception("inventory.%s failed", getattr(fn, "__name__", fn))
        return default
    return list(result) if isinstance(default, list) else result


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _d(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _omm_epoch(s: str) -> str:
    return _iso(datetime.fromisoformat(s).replace(tzinfo=timezone.utc))
