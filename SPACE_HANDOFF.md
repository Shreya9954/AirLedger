# Space Ledger build: handoff for roles A, B and C

Written 2026-10-11 for three Claude agents working in parallel in this repo. Read all of it before starting, then follow your role's section. This replaces the contrail-calibration plan in `HANDOFF.md`, which is shelved.

## 1. What we're building and why

Upper Air Ledger currently shows a simulated night of North Atlantic contrails. Its launch and re-entry figures are placeholders. We are adding a **space ledger built on real, checkable data**: what launches and re-entering spacecraft leave in the upper atmosphere, and who put it there.

**Why this direction.** The contrail ideas depend on humidity forecasts that are close to a coin toss per flight. Here the headline numbers are catalogue facts:
- what launched
- what re-entered, and when
- how much it weighed

Chemistry and climate effects are shown as labelled estimates or open research.

**The story.** Rules now require satellites in low orbit to come down quickly; the US FCC adopted a 5-year deorbit rule in 2022. They are also designed to burn up completely so no debris reaches the ground. That's safer on the ground, but it puts the most metal into the upper atmosphere. NOAA aircraft found metals from re-entering spacecraft in about 10% of stratospheric particles (Murphy et al., PNAS 2023).

**What the demo shows** (presented indoors on a screen, so it must work offline):
1. **Layers of the sky:** a 0–120 km vertical slice showing what each source leaves at each height.
2. **A globe:** satellites in orbit, falling objects highlighted, recent launch sites.
3. **Ledgers:** launches by provider (propellant and emissions) and re-entries by owner (mass burned up).
4. **The trade-off panel:** re-entered mass per month since 2015, plus the explanation above.
5. **A tag on every number:** Fact, Estimate or Research.

**Out of scope:** predicting where re-entries land, ozone or climate modelling, tCO₂e for space. The existing contrail map and score chart stay untouched; their space placeholders remain labelled illustrative.

## 2. Ground rules (all roles)

- **Additive only.** New files, plus the small edits listed under your role. Don't refactor or delete existing code.
- **Same checkout, separate files.**
  - Touch only the files your role owns (section 4).
  - To change a file you don't own, write the request in your notes file (below) and keep going against the current contract.
- **Notes files.** Each role keeps one: `docs/space/notes-a.md`, `notes-b.md`, `notes-c.md`. Record status, decisions, open questions and cross-role requests there, and read the others' notes when you start and at milestones.
- **Don't commit or push** unless the user asks.
- **No secrets needed.** All sources are public. Don't search the machine for credentials.
- **Be polite to data providers.**
  - CelesTrak: download once per update (GP every 2 h; SATCAT about twice a day). Stop immediately on any non-200 response; ignoring this gets the IP firewalled.
  - Launch Library 2 allows 15 unauthenticated requests per hour. For development, use `https://lldev.thespacedevs.com` (current data, looser limits).
  - Everything goes through role A's disk cache in `backend/.cache/space/` (git-ignored).
- **Python env:** `backend/.venv` (Python 3.12) has fastapi, uvicorn, httpx, pydantic, numpy and pytest. pycontrails is not installed and not needed. Run tests from `backend/` with `.venv/Scripts/python -m pytest`.

## 3. Roles at a glance

| Role | Job | Hands off to |
|---|---|---|
| **A: data plumbing** | Fetch, cache and join CelesTrak, GCAT and Launch Library 2; aggregate; API endpoints; snapshot files | Records to B (Contract 1); summary JSON to C (Contract 2) |
| **B: the numbers** | Rocket propellant table, emission factors, deposits per launch and re-entry by altitude, aviation context; a source for every figure | Functions in `inventory.py` (Contract 1) |
| **C: frontend** | New page sections: layers chart, globe, ledgers, trade-off panel, tags; data loading with offline fallbacks | Reads Contract 2 JSON |

## 4. File ownership

| Owner | Files |
|---|---|
| Shared, frozen (change only via section 7) | `backend/app/space/records.py`, `frontend/data/space-sample.json`, `frontend/data/space-orbits-sample.json`, this file |
| A | `backend/app/space/{cache,build,api,snapshot,contract}.py`, `backend/app/space/sources/**`, `backend/tests/test_space_{records,sources,build}.py`, `backend/tests/fixtures/space/**`, `frontend/data/space-snapshot.json`, `frontend/data/space-orbits.json`; small edit to `backend/app/main.py` (include router) |
| B | `backend/app/space/inventory.py` (a stub exists; replace the bodies, keep the signatures), new `backend/app/space/vehicles.py`, `backend/app/space/factors.py`, `backend/tests/test_space_inventory.py` |
| C | new `frontend/js/space/**`, new `frontend/css/space.css`; small edits to `frontend/index.html` (new sections, nav links, stylesheet link) and `frontend/js/main.js` (one init call) |
| Nobody | Everything else, including the contrail pipeline, `HANDOFF.md`, `README.md` (updated at integration) |

## 5. Contract 1: A ↔ B (Python), in `backend/app/space/records.py`

**Shared types**
- `Value(central, low, high, unit, tier, source, note="")`
  - `tier` ∈ `fact | estimate | research`.
  - `Value.fact(x, unit, source)` sets low = high = central.
  - Adding two Values sums the ranges end to end, takes the least certain tier, and unions the sources (joined with `+`).
  - `vsum()` sums a list, skipping None. `.scale(k)` multiplies all three numbers.
- `Deposit(species, lo_km, hi_km, value)`
  - `species` ∈ `SPECIES` = propellant, black_carbon, alumina, chlorine, ablated_mass, aluminium. All in kg.
  - `lo_km` and `hi_km` must be values from `BIN_EDGES_KM` = 0, 5, …, 120.
  - A deposit spanning several bins is spread evenly across them by A.
- `LaunchRecord`: the Launch Library 2 launch, including `vehicle` (configuration full name), `vehicle_families`, `orbit`, pad position, and `liftoff_mass_kg` (published configuration liftoff mass, may be None). Status ∈ success | failure | partial | upcoming.
- `ObjectRecord`: a CelesTrak SATCAT entry joined to GCAT by NORAD number.
  - Masses: `mass_kg`, `dry_mass_kg`, `mass_uncertain`, and `end_of_life_mass_kg`, which prefers dry mass.
  - Identity: `operator` (display name), `operator_code` (GCAT owner code), `country`.
  - `tags`: contains `"landed"` when the object came down intact and was recovered.

**What B implements in `backend/app/space/inventory.py`:**

```python
match_vehicle(launch: LaunchRecord) -> str | None      # key into B's vehicle table
launch_propellant(launch: LaunchRecord) -> Value | None
launch_deposits(launch: LaunchRecord) -> list[Deposit]
reentry_deposits(obj: ObjectRecord) -> list[Deposit]
aviation_context(days: int) -> list[Deposit]           # global aviation over `days`, for scale
references() -> list[dict]                             # [{"id","name","url"}] for every source id B uses
```

Rules:
- Every `Value.source` token must be either one of A's ids (`ll2`, `celestrak`, `gcat`) or an id listed by `references()`. A's contract test enforces this.
- Return None or `[]` when unknown. Never invent a number without a source.
- Pure functions: no network access, deterministic.
- A calls `launch_deposits` only for launches that have happened, not upcoming ones.

## 6. Contract 2: A → C (JSON)

**Endpoints (A):**
- `GET /api/space/summary?days=90` (7–365): space-summary JSON.
- `GET /api/space/orbits?limit=3000` (100–6000): space-orbits JSON.
- Both return 503 with a message if upstream data is unavailable and nothing is cached.

**Where C loads from, in order:**
1. the API
2. `frontend/data/space-snapshot.json` and `space-orbits.json` (written by A's snapshot script, committed for the offline demo)
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
- "Mass" for a re-entry is the catalogued end-of-life mass, a Fact. How much of it burned up and turned into aluminium is B's Estimate or Research. **Label it "re-entered mass", never "burned up".** Burned-up mass is `deposits.ablated_mass`.
- `landed: true` marks objects that came down intact and were recovered: crew capsules such as Dragon and Soyuz (CelesTrak ORBIT_TYPE `LAN`). They appear in `reentries` but are **excluded from the ledgers, `monthly` and `coverage`**, which count mass that came down to burn up. Show them with a "landed" label.

### space-orbits/1

```
{schema: "space-orbits/1", sample: bool, generated_at, source: "celestrak",
 objects: [OMM record exactly as CelesTrak GP JSON + "group": "falling"|"station"|"active"]}
```

- **6-digit catalogue numbers.** CelesTrak ran out of 5-digit numbers on 2026-07-11, and newer objects have no TLE. Propagate from the OMM fields (e.g. satellite.js `json2satrec`, after verifying it exists in the pinned version), not from TLE strings.
- `objects` contains every falling object, the stations, and a deterministic sample of the active catalogue up to `limit`.

## 7. Changing a contract

Contracts 1 and 2 are frozen.
1. If you need a change, write it in your notes file as `REQUEST(owner): ...` and tell the user.
2. Don't edit shared files yourself.
3. The user decides. Adding optional JSON keys is the cheap kind of change; renaming or removing keys is not.

### Contract change log

- **2026-10-11, A, made before B and C started:**
  - `Reentry.landed` added.
  - Landed objects are excluded from the ledgers, `monthly` and `coverage`.
  - `ObjectRecord.tags` now uses the `"landed"` value.
  - `sources[].retrieved_at` may be null for literature references.
  - Reason: real data showed recovered crew capsules being counted as burned-up mass.

## 8. Role A: data plumbing

Status and log: `docs/space/notes-a.md`. The planning Claude session took this role and started immediately.

**Tasks**
1. `cache.py`: disk cache with a TTL per source.
   - Keep stale data when an upstream fails.
   - After any non-200 response, back off that host for an hour.
   - Never retry in a loop.
2. `sources/celestrak.py`:
   - SATCAT CSV from `https://celestrak.org/pub/satcat.csv` (TTL 12 h).
   - GP JSON from `gp.php?SPECIAL=DECAYING`, `GROUP=stations` and `GROUP=active` (TTL 2 h).
   - Perigee and apogee computed from the OMM elements.
3. `sources/gcat.py`:
   - Files: `tsv/cat/satcat.tsv` and `satcat100k.tsv` (TTL 24 h), plus `tsv/tables/orgs.tsv` for owner names (TTL 7 days).
   - Parsing: tab-separated, header on the first `#` line, values padded with spaces. Masses are in `Mass`, `DryMass` and `TotMass`; flag `?` means uncertain.
   - Join on the `Satcat` number.
4. `sources/launchlib.py`:
   - `/2.3.0/launches/previous/` and `/upcoming/` with `mode=detailed`. The rocket's `launch_mass` (tonnes) only appears in detailed mode.
   - Filter by `net`. TTL 6 h.
   - Base URL from env `LL2_BASE_URL`, defaulting to production.
5. `build.py`: build the records, call B's `inventory` functions, aggregate (ledgers, layers by bin, monthly since 2015, coverage) and emit Contract 2. `contract.py`: a validator that the tests and the snapshot script both run.
6. `api.py` with a router included in `main.py`. It must come before the static mount at `/`.
7. `snapshot.py`: run with `python -m app.space.snapshot` from `backend/`. Writes `frontend/data/space-snapshot.json` and `space-orbits.json`. Budget: summary under 1 MB, orbits under 2 MB.
8. Tests against small fixtures cut from real responses (no network in tests), including a contract test checking that the sample file and built output share the same shape.

**Done when**
- The tests pass.
- `/api/space/summary` and `/api/space/orbits` work against real data.
- A snapshot exists. Regenerate it after B lands.

**Facts checked on 2026-10-11:**
- 315 objects re-entered in the 90 days to 11 Oct.
- 303 of them have a GCAT mass, totalling about 226 t.
- SpaceX's Starlink (owner code `SPXS`) accounts for the largest share.

## 9. Role B: the numbers

Status and log: `docs/space/notes-b.md`.

**Tasks**
1. **`vehicles.py`:** a table for the rockets that make up most recent launches.
   - Which rockets: start from the vehicle names in the snapshot or in Launch Library 2 (e.g. Falcon 9, Falcon Heavy, Starship, the Long March family, Electron, Soyuz-2, Ariane 6, Vulcan, New Glenn, PSLV/GSLV, H3, Kinetica/Zhuque/Ceres).
   - Fields per stage or booster: propellant type (kerosene/LOX, methane/LOX, hydrogen/LOX, solid (AP/Al), hypergolic), propellant mass, and the approximate altitude range over which it burns.
   - Every figure needs a cited source.
   - `match_vehicle` maps Launch Library 2's `vehicle` and `vehicle_families` to a table key.
2. **`factors.py`:** emission factors per propellant type, each with a low, central and high value and a citation.
   - Black carbon for kerosene (and methane, much lower).
   - Alumina and chlorine for solid motors.
   - Ablation fraction and aluminium fraction for re-entering satellites and rocket stages.
   - Tier: propellant mass is `estimate`; emission factors are `research`.
3. **`aviation_context(days)`:** global aviation fuel burn or black carbon at cruise altitude over `days`, from a cited global figure. It gives scale in the layers chart, and the tier is research or estimate.
4. **`references()`:** every source id used.
5. **`test_space_inventory.py`:** checks units, valid bins, low ≤ central ≤ high, every source token resolving, and None or `[]` for unknown rockets.

**Cases found in the real data (handle them explicitly)**
- **Starship upper stages:** for example `STARSHIP-14`, 120 t, a controlled re-entry on 2026-09-28. It's catalogued as a payload with SpaceX (`SPX`) as owner. It is built to survive re-entry, so only its heat shield and some structure ablate; most of it reaches the ocean. A generic satellite burn-up fraction would make this one object outweigh every Starlink re-entry in the window combined (about 43 t).
- **Recovered capsules:** objects with the `landed` tag, such as Crew Dragon (9.5 t) and Soyuz MS (2.9 t). These mostly survive; heat-shield ablation is small.
- **Spent upper stages (R/B):** GCAT's end-of-life mass is the dry mass. For example, a PAM-D stage is 132 kg dry against 2,200 kg fuelled.
- **Tiny debris:** objects with mass 0 (e.g. ISS debris).

**Principles**
- Judges will ask "where does this number come from?" Cite each figure in a comment and in `references()`.
- Prefer wide, honest ranges over precise-looking guesses.
- Don't edit `records.py`. Ask in your notes file instead.

**Done when:** the tests pass and A's build shows `launches_with_data` covering most launches in the window.

## 10. Role C: frontend

Status and log: `docs/space/notes-c.md`.

**Context:** the site is static ES modules with no build step (see `README.md`). The existing structure is `frontend/index.html`, `css/styles.css` (theme tokens for light and dark) and `js/main.js` plus `js/ui/*`. Follow their style: same theme tokens, same section and sheet markup, accessible controls.

**Tasks**
1. `js/space/data.js`: load per section 6 (API, then snapshot, then sample). Show the source credits and a "SAMPLE DATA" label when applicable.
2. **Layers chart.** 0–120 km on the vertical axis, with shaded regions and stacked or grouped bars per source and species. Toggle between species, because they aren't additive across species. Load the `dataviz` skill before charting.
3. **Globe.**
   - Library: globe.gl or three.js from a CDN, with exact versions pinned.
   - Propagate orbits from OMM with satellite.js. Verify OMM support in the pinned version; if it's missing, raise a REQUEST for A to supply positions instead.
   - Draw "falling" objects distinctly, mark launch pads, and keep it smooth (cap the number of points and use a points layer).
4. **Ledgers.** Launch providers and re-entry owners as two sortable tables, reusing the patterns in `js/ui/ledger.js`. Show coverage, e.g. "mass known for 303 of 315".
5. **Trade-off panel.** Monthly re-entered mass since 2015 with the explanation from section 1 and its sources.
6. **Tags.** A small Fact / Estimate / Research badge on every number, with a tooltip showing the range and source.
7. **Wiring.** New sections and nav links in `index.html`, styles in `css/space.css`, and one init call in `main.js`.
   - The space code must not break the existing page if it fails.
   - The existing contrail map and score chart stay unchanged.

**Done when:**
- All of it renders from the sample, the snapshot and the live API.
- It works offline using the snapshot, in light and dark themes, and on a phone-width screen.

## 11. Integration (after all three finish; any one role, as the user directs)

1. Regenerate the snapshot with B's numbers in place.
2. Check that the numbers make sense:
   - the totals in the ledgers match the item lists
   - coverage is shown
   - every Value source resolves
3. Turn Wi-Fi off and check the page still works.
4. Update `README.md` with how to run the space ledger, its sources and their licences. GCAT is CC-BY: cite "data from GCAT (J. McDowell, planet4589.org/space/gcat)".

## 12. Timeline (three agents)

| Phase | Duration |
|---|---|
| Shared contract (done: this file and the shared files) | 0.75 h |
| Parallel roles | 2–2.5 h |
| Integration | 1.25–1.75 h |
| **Total** | **about 4–4.5 h** |

## Sources

- Launch Library 2: https://thespacedevs.com/llapi
- CelesTrak SATCAT format: https://celestrak.org/satcat/satcat-format.php
- CelesTrak usage policy: https://celestrak.org/usage-policy.php
- GCAT: https://planet4589.org/space/gcat/ (column descriptions: https://planet4589.org/space/gcat/web/cat/cols.html)
