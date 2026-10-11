# Role A notes

Status, decisions, open questions and cross-role requests (`REQUEST(owner): ...`). See SPACE_HANDOFF.md.

## Status (2026-10-11)

**Done. A's lane is complete and tested.** The only follow-up is regenerating the snapshot once B lands.

- **Sources:**
  - `sources/celestrak.py`: SATCAT CSV and GP/OMM.
  - `sources/gcat.py`: masses, owners, organisation names.
  - `sources/launchlib.py`: LL2 2.3.0, detailed mode.
- **Plumbing:**
  - `cache.py`: TTLs, stale fallback, one-hour back-off per host after any error.
  - `build.py`: joins and aggregation.
  - `contract.py`: validator.
  - `api.py`: `/api/space/summary`, `/api/space/orbits`, included in `main.py` before the static mount.
  - `snapshot.py`: writes the offline files.
- **Tests:** `test_space_{records,sources,build}.py` against fixtures in `tests/fixtures/space/`. The full backend suite (51 tests) passes.
- **Snapshot written from real data:** `frontend/data/space-snapshot.json` (0.22 MB) and `space-orbits.json` (1.32 MB, 3,000 objects). B's numbers are still the stub, so `launches_with_data` is 0 and `layers` is empty. Rerun after B lands.

## How to run (from `backend/`)

- **Tests:** `.venv/Scripts/python -m pytest -q`
- **Snapshot:** `.venv/Scripts/python -m app.space.snapshot`. It reuses `backend/.cache/space/`. For development, set `LL2_BASE_URL=https://lldev.thespacedevs.com/2.3.0` to spare the 15-requests-an-hour production limit.
- **API:** `.venv/Scripts/uvicorn app.main:app --reload`, then open `/api/space/summary?days=90` and `/api/space/orbits?limit=3000`. Built results are kept for 10 minutes.

## What the real data shows (90 days to 2026-10-11)

- **Launches:** 75 (74 successes, 1 failure) on 31 vehicle types, plus 4 upcoming in the next 14 days.
- **Re-entries:** 315 in total.
  - 2 landed: CREW DRAGON 12 (9.5 t) and SOYUZ-MS 28 (2.9 t). These are flagged `landed` and kept out of the totals.
  - The other 313 split into 218 payloads, 67 debris, 24 rocket bodies and 4 unknown.
  - 301 of the 313 have a GCAT mass. Re-entered mass is about 213 t once the landed capsules are excluded.
- **Largest single object:** STARSHIP-14, 120 t, owner `SPX`, a controlled re-entry on 2026-09-28. Next is SpaceX (Seattle) (`SPXS`, i.e. Starlink) with 138 objects, about 43 t.
- **Falling now:** 72 objects, 67 with mass. The lowest is DELTA 2 R/B(1) at a 154 km perigee.
- **Re-entered mass per year, landed objects excluded:** 2015: 131 t, 2019: 176 t, 2022: 278 t, 2024: 470 t, 2025: 498 t, 2026 to 11 Oct: 488 t. These are sums of GCAT end-of-life masses and include Starship stages.
- **Launches per month** count distinct international designators in SATCAT. That means launches that put catalogued objects in orbit; failures and suborbital flights are usually not counted.

## Decisions

- **End-of-life mass** is GCAT `DryMass` when present, else `Mass`. The uncertainty flag follows whichever mass is used.
- **Operator names:** the GCAT organisation `EName`, else `Name`. Objects with no GCAT entry fall back to CelesTrak's owner code.
- **Launch Library 2** fetches either 90 or 365 days back (two fixed sizes), so different `days` values share cached pages.
- **In-flight launches** (LL2 status "In Flight") are skipped until they have an outcome.
- **Role B failures:** if a B function raises, the build logs it and treats the value as unknown, so the page never breaks because of an inventory bug.

## Requests

- **REQUEST(B): vehicles to cover**, from the 75 launches in the current window: Falcon 9 Block 5 (30), Electron (6), Long March 12 (3), Falcon Heavy (2), Starship V3 (2), Long March 6A/8A/7A (2 each), Kinetica 1 (2), Soyuz 2.1b (2, plus 2 Fregat variants), Gravity-1 (2), and one each of KSLV-2 Nuri, Long March 2D/2C/4B/6C/3B/E, Kuaizhou 11, Zhuque-2E, Zhuque-3, Vega-C, Spectrum, GSLV Mk II, Pallas-1, Ariane 62, H3-22, Smart Dragon 3, Vikram-I. The top 10 cover about 70% of launches. Match on `vehicle` and `vehicle_families`; LL2 gives e.g. ("Falcon", "Falcon 9").
- **REQUEST(B):** handle Starship and the `landed` tag explicitly (see SPACE_HANDOFF.md §9).
- **REQUEST(C):**
  - Label re-entry `mass` as "re-entered mass", and use `deposits.ablated_mass` for "burned up".
  - Show `landed` objects with a "landed" label.
  - Show coverage as "mass known for N of M".
  - Note the monthly launch definition above wherever the chart shows launches.
