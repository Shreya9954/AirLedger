# Role B notes

Status, decisions, open questions and cross-role requests (`REQUEST(owner): ...`). See SPACE_HANDOFF.md.

## Status (2026-10-11)

**Done.** `inventory.py` now has real bodies with the same signatures. The data lives in two new files:
- `vehicles.py`: the rocket table, name matching, the propellant-fraction evidence, and the height profile.
- `factors.py`: emission factors, burn-up and aluminium fractions, and the aviation comparison.

**Tests:** `tests/test_space_inventory.py` has 97 tests and they all pass. The full backend suite has 148 tests: 147 pass and 1 fails. The failure is in A's file and is expected (see Requests).

**Real data** (built offline from `backend/.cache/space`, 90 days to 2026-10-11): it passes `validate_summary` with no errors, and **73 of 75 launches have data** (`launches_with_data`).
- The two without data are Spectrum and Vikram-I. Neither has a published liftoff mass in LL2 or on Wikipedia, so they stay unknown rather than guessed.
- Totals over the 90 days:
  - Propellant: about 38,000 t at all heights, about 31,500 t of it below 120 km.
  - Soot from launches: about 190 t.
  - Alumina: about 690 t. Chlorine: about 460 t.
  - Ablated (burned-up) mass: about 79 t, with about 38 t of aluminium in it.
  - For scale, aviation soot is about 5,300 t, nearly all of it at 0–15 km.

## Where the numbers come from

**Main papers**
- `barker2024`: Barker, Marais & McDowell (2024), *Scientific Data* 11, 1079.
  - Table 1: soot (black carbon) per kg of propellant: kerosene 22 g, solid 16 g, hypergolic 16 g, methane 5 g. Solid motors also give 328 g alumina and 217 g chlorine.
  - Eq. 2: afterburning. Below about 15 km only 4% of the soot survives; by about 42 km all of it does.
  - Methods:
    - Share of mass that burns up on re-entry: megaconstellation satellites 100%, other satellites 80%, upper stages 65%, core stages and fairings 30%, reusable craft 0%.
    - Aluminium share: 40% for satellites, 70% for rocket stages.
    - Re-entries burn up between 80 and 60 km.
    - Landing boosters keep 5.6% of their propellant for an entry burn at 70–55 km and 1.2% for a landing burn from 3.3 km.
- `gaia2024`: Teoh et al. (2024), *ACP* 24, 725. Global aviation in 2019 burned 283 Tg of fuel, 79% of it above 7.6 km, and emitted 21.4 Gg of soot.

**Rocket propellant**, method 1: published stage loads.
- Taken from Wikipedia infoboxes; each vehicle has its own source id (`wp:<rocket>`) with a URL.
- Vehicles: Soyuz-2, Ariane 6, Vega C, H3, LVM3, GSLV, PSLV, SSLV, Proton-M, Long March 2C and 3B, Atlas V, Vulcan, Starship.
- The low end is 10% below the published load, because some propellant goes unburned.

**Rocket propellant**, method 2: liftoff mass × propellant fraction.
- The fraction is **derived, not chosen**: it is the median (88%) and range (82–93%) of the 12 rockets that publish both stage loads and liftoff mass (`PROPELLANT_FRACTION_EVIDENCE`).
- Used for Falcon 9, Electron, most Long March rockets, Zhuque, Kinetica and others.
- The liftoff mass comes from LL2 when it has one (`ll2`), otherwise from the Wikipedia infobox.

**Our own assumptions.** Each is labelled "(ours)" in its Value note, and the source id is `ual-method`.
- The ranges around the papers' central values.
- Stage shares for method-2 rockets.
- Burn heights per stage.
- The climb shape.

## Decisions

- **Starship upper stage:** 1% burns up (range 0–5%) and no aluminium, because it is stainless steel. STARSHIP-14 (120 t) adds 1.2 t of ablated mass, against 43 t from Starlink. GCAT still lists it as 120 t of re-entered mass, which is correct: that's A's catalogued fact.
- **Landed capsules** (`landed` tag): no deposits. Barker et al. treat reusable craft as non-ablating.
- **Massless or unknown objects:** no deposits.
- **Upper stages:** use GCAT dry mass, via `end_of_life_mass_kg`.
- **Megaconstellations:** identified by GCAT owner (SPXS, ONEWEB, ONEWEBN, ONEWEBE, KUIP, YUANX, ZXW) or by name prefix (STARLINK, ONEWEB, KUIPER, QIANFAN, HULIANWANG, GUOWANG).
- **Failed launches:** the central value is unchanged and the low end goes to 0, because the failure point isn't in the data.
- **Propellant in two places:**
  - `launch_propellant` is the total at all heights.
  - `deposits.propellant` is only the part below 120 km. For a Falcon 9 that is about 83%; an upper stage mostly burns in space.
- **Aviation in the layers chart:** jet fuel uses species `propellant` and aircraft soot uses `black_carbon`. Both are split 79% to cruise (5–15 km bins) and 21% to 0–10 km. Frontend label: "jet fuel".
- **Propane** (Isar's Spectrum) has no published soot index. Its range spans the methane and kerosene values.
- **`references()`** returns every vehicle article in the table, not only those used in the current window. C should show only the sources that the data actually cites.

## Requests

- **REQUEST(A):** `tests/test_space_build.py::test_stub_inventory_also_matches_contract` still expects the stub's output (`layers == []`, `launches_with_data == 0`). Its contract check still passes; only that stub-specific line fails now that B has landed. Suggested fix: pass a stub explicitly, e.g. `build_summary(inputs(), NOW, 90, STUB)` where `STUB` returns None/[] for everything, or drop the second assert.
- **REQUEST(A):** regenerate the snapshot (`python -m app.space.snapshot`) so `frontend/data/space-snapshot.json` carries B's numbers. Built offline, the summary is about 0.45 MB, under the 1 MB budget.
- **Note for C:** a provider's or launch's `propellant` is the total; `deposits.propellant` is the part below 120 km. In `layers`, aviation's "propellant" is jet fuel.
