# Space ledger: data formats and sources

The space ledger sections of the page (layers of the sky, globe, launch and re-entry ledgers, trade-off panel) show what rocket launches and re-entering spacecraft leave in the upper atmosphere, from public catalogues: CelesTrak, GCAT and Launch Library 2. They sit alongside the contrail map as the space side of the upper-air picture. Every number is tagged Fact, Estimate or Research with its source.

Run from `backend/`: tests with `.venv/bin/python -m pytest`, the offline snapshot with `.venv/bin/python -m app.space.snapshot`, the API with `.venv/bin/uvicorn app.main:app` (`/api/space/summary?days=90`, `/api/space/orbits?limit=3000`).

## Data providers

Be polite to data providers:
  - CelesTrak: download once per update (GP every 2 h; SATCAT about twice a day). Stop immediately on any non-200 response; ignoring this gets the IP firewalled.
  - Launch Library 2 allows 15 unauthenticated requests per hour. For development, use `https://lldev.thespacedevs.com` (current data, looser limits).
  - Everything goes through the disk cache in `backend/.cache/space/` (git-ignored).

## Contract 1: data records ↔ emission numbers (Python), in `backend/app/space/records.py`

**Shared types**
- `Value(central, low, high, unit, tier, source, note="")`
  - `tier` ∈ `fact | estimate | research`.
  - `Value.fact(x, unit, source)` sets low = high = central.
  - Adding two Values sums the ranges end to end, takes the least certain tier, and unions the sources (joined with `+`).
  - `vsum()` sums a list, skipping None. `.scale(k)` multiplies all three numbers.
- `Deposit(species, lo_km, hi_km, value)`
  - `species` ∈ `SPECIES` = propellant, black_carbon, alumina, chlorine, ablated_mass, aluminium. All in kg.
  - `lo_km` and `hi_km` must be values from `BIN_EDGES_KM` = 0, 5, …, 120.
  - A deposit spanning several bins is spread evenly across them by the build.
- `LaunchRecord`: the Launch Library 2 launch, including `vehicle` (configuration full name), `vehicle_families`, `orbit`, pad position, and `liftoff_mass_kg` (published configuration liftoff mass, may be None). Status ∈ success | failure | partial | upcoming.
- `ObjectRecord`: a CelesTrak SATCAT entry joined to GCAT by NORAD number.
  - Masses: `mass_kg`, `dry_mass_kg`, `mass_uncertain`, and `end_of_life_mass_kg`, which prefers dry mass.
  - Identity: `operator` (display name), `operator_code` (GCAT owner code), `country`.
  - `tags`: contains `"landed"` when the object came down intact and was recovered.

**Implemented in `backend/app/space/inventory.py`:**

```python
match_vehicle(launch: LaunchRecord) -> str | None      # key into the inventory's vehicle table
launch_propellant(launch: LaunchRecord) -> Value | None
launch_deposits(launch: LaunchRecord) -> list[Deposit]
reentry_deposits(obj: ObjectRecord) -> list[Deposit]
aviation_context(days: int) -> list[Deposit]           # global aviation over `days`, for scale
references() -> list[dict]                             # [{"id","name","url"}] for every source id B uses
```

Rules:
- Every `Value.source` token must be either one of the data layer's ids (`ll2`, `celestrak`, `gcat`) or an id listed by `references()`. The contract test enforces this.
- Return None or `[]` when unknown. Never invent a number without a source.
- Pure functions: no network access, deterministic.
- The build calls `launch_deposits` only for launches that have happened, not upcoming ones.

## Contract 2: backend → frontend (JSON)

**Endpoints:**
- `GET /api/space/summary?days=90` (7–365): space-summary JSON.
- `GET /api/space/orbits?limit=3000` (100–6000): space-orbits JSON.
- Both return 503 with a message if upstream data is unavailable and nothing is cached.

**Where the frontend loads from, in order:**
1. the API
2. `frontend/data/space-snapshot.json` and `space-orbits.json` (written by `python -m app.space.snapshot`, committed for the offline demo)
3. `space-sample.json` and `space-orbits-sample.json`

If `sample` is true, show a visible "SAMPLE DATA" label.

### space-summary/1

The worked example is `frontend/data/space-sample.json`. Every key below is always present. Arrays may be empty. Values may be null only where marked.

```
schema        "space-summary/1"
sample        bool
generated_at  ISO-8601 UTC
window        {start: "YYYY-MM-DD", end: "YYYY-MM-DD", days: int}
sources       [{id, name, url, licence, retrieved_at|null, citation?}]    # every Value.source token resolves here; retrieved_at is null for literature references
bins_km       [0,5,...,120]
regions       [{id, name, lo_km, hi_km}]   # nominal: troposphere 0-12, stratosphere 12-50, mesosphere 50-85, thermosphere 85-120
launches      [Launch]       # in window plus the next 14 days (status "upcoming"); newest first
reentries     [Reentry]      # decayed within window; newest first
falling       [Falling]      # still in orbit and on CelesTrak's decaying list; lowest perigee first
ledger        {launch_providers: [ProviderRow], reentry_owners: [OwnerRow]}   # each sorted by its mass, descending
layers        [{lo_km, hi_km, source: "launch"|"reentry"|"aviation", species, value: Value}]   # one cell per 5-km bin; zero cells omitted
monthly       [{month: "YYYY-MM", launches: int, reentries: int, reentries_with_mass: int, reentered_mass: Value|null}]   # from 2015-01; null iff reentries_with_mass == 0
coverage      {launches, launches_with_data, reentries, reentries_with_mass, falling, falling_with_mass}

Value        {central, low, high, unit: "kg", tier: "fact"|"estimate"|"research", source, note?}
Launch       {id, name, net, status: "success"|"failure"|"partial"|"upcoming", provider, country|null,
              vehicle, vehicle_key|null, orbit|null, pad: {name, location, lat, lon} (fields may be null),
              liftoff_mass: Value|null, propellant: Value|null, deposits: {species: Value}}
Reentry      {norad, cospar, name, type: "PAY"|"R/B"|"DEB"|"UNK", operator, operator_code|null, country|null,
              launch_date|null, decay_date, landed: bool, mass: Value|null, deposits: {species: Value}}
Falling      {norad, cospar, name, type, operator, operator_code|null, country|null, perigee_km, apogee_km, epoch, mass: Value|null}
ProviderRow  {provider, country|null, launches, launches_with_data, propellant: Value|null, deposits: {species: Value}}
OwnerRow     {operator, operator_code|null, country|null, reentries, reentries_with_mass, mass: Value|null, deposits: {species: Value}}
```

Notes:
- Launch providers (Launch Library 2 names) and object owners (GCAT codes) are deliberately separate tables. Don't try to merge "SpaceX" with "SPXS".
- `launches_with_data` = launches for which B returned a propellant figure.
- "Mass" for a re-entry is the catalogued end-of-life mass, a Fact. How much of it burned up and turned into aluminium is the inventory's Estimate or Research. **Label it "re-entered mass", never "burned up".** Burned-up mass is `deposits.ablated_mass`.
- `landed: true` marks objects that came down intact and were recovered: crew capsules such as Dragon and Soyuz (CelesTrak ORBIT_TYPE `LAN`). They appear in `reentries` but are **excluded from the ledgers, `monthly` and `coverage`**, which count mass that came down to burn up. Show them with a "landed" label.

### space-orbits/1

```
{schema: "space-orbits/1", sample: bool, generated_at, source: "celestrak",
 objects: [OMM record exactly as CelesTrak GP JSON + "group": "falling"|"station"|"active"]}
```

- **6-digit catalogue numbers.** CelesTrak ran out of 5-digit numbers on 2026-07-11, and newer objects have no TLE. Propagate from the OMM fields (e.g. satellite.js `json2satrec`, after verifying it exists in the pinned version), not from TLE strings.
- `objects` contains every falling object, the stations, and a deterministic sample of the active catalogue up to `limit`.

### Contract change log

- **2026-10-11:**
  - `Reentry.landed` added.
  - Landed objects are excluded from the ledgers, `monthly` and `coverage`.
  - `ObjectRecord.tags` now uses the `"landed"` value.
  - `sources[].retrieved_at` may be null for literature references.
  - Reason: real data showed recovered crew capsules being counted as burned-up mass.

## Facts checked on 2026-10-11
- 315 objects re-entered in the 90 days to 11 Oct.
- 303 of them have a GCAT mass, totalling about 226 t.
- SpaceX's Starlink (owner code `SPXS`) accounts for the largest share.

## Sources

- Launch Library 2: https://thespacedevs.com/llapi
- CelesTrak SATCAT format: https://celestrak.org/satcat/satcat-format.php
- CelesTrak usage policy: https://celestrak.org/usage-policy.php
- GCAT: https://planet4589.org/space/gcat/ (column descriptions: https://planet4589.org/space/gcat/web/cat/cols.html)
