# Handoff: Upper Air Ledger → Contrails API + calibrated avoidance

Context for a Claude session continuing this work. Written 2026-10-11, summarising a planning conversation with the user. **No code has been written yet.** The user has been asked "Should I start with the demo-mode version?" several times and has not yet said yes. Confirm before implementing.

## 1. The user and the goal

- Building this for a **hackathon**. Wants an "x-factor": something creative, technically interesting and credible. Not maximal complexity.
- Not an atmospheric-science specialist; started out thinking contrails come from old planes. Explain domain points plainly and briefly.
- **Constraint: changes must be additive.** Add a new mode and new files. Do not delete or rewrite existing working code; keep edits to existing files small and behaviour-preserving.
- **Constraint: API keys are NOT on this machine.** The user has keys for the APIs the code calls, but they live elsewhere. There is no `backend/.env`, no `~/.cdsapirc`, no relevant env vars. A broader search of the user's env and other folders for key files was **blocked by the permission classifier as credential exploration. Do not search for credentials again.** Design so the key holder runs scripts and sends back key-free output.

## 2. What the repo does today (verified by reading the code)

Git: branch `main`, clean, two commits (`4793770` initial, `65cf77e` "Add Upper Air Ledger backend and frontend"). About 1,800 lines in total. See `README.md` for the layout.

- **Frontend** (`frontend/`, static ES modules, no build step). One page with four sections:
  1. **Contrail map**: 60 fictional North Atlantic flights over a simulated 12 h night. Humidity is 17 drifting Gaussian blobs (`js/sim/atmosphere.js`). Click a flight to get the rail (`js/ui/rail.js`) with a reroute slider (±2,000/±4,000 ft over the humid stretch ±100 km).
  2. **One score** (`js/ui/score.js`): flights and hard-coded rocket launches/re-entries on one log tCO₂e axis.
  3. **Ledger** (`js/ui/ledger.js`): predicted contrail warming summed by fictional carrier or aircraft type; CSV copy.
  4. **"Cloud or contrail?" lab** (`js/ui/lab.js`): canvas-drawn fake satellite patches. Features are preset from the label, so the "classifier" never looks at pixels.
- **Demo physics** (`js/model.js`): EF/km is a made-up curve (strong at night, slightly negative midday), scaled by humidity and type factor `f` (`js/config.js`). Fuel penalty: 1.1% per 2,000 ft down, 0.7% up, on the deviated share, plus 40 kg. tCO₂e = EF ÷ 1.48e12 J/t.
- **Backend** (`backend/app/main.py`, FastAPI): `/api/health`, `/api/scenario` (404 in demo mode), `/api/space-events`; also serves `frontend/`. `UAL_MODE=demo|live` (default demo). The frontend calls `/api/health` and falls back to the simulation unless the mode is `live`.
- **Live pipeline** (`pipeline/scenario.py`, `cocip.py`, `humidity_grid.py`, `sources/opensky.py`, `sources/era5.py`): OpenSky tracks + ERA5 + local pycontrails CoCiP. **Never run against real services** (the README says so). Caches to `.cache/`.
- `pipeline/reroute.py` `build_options(base, fl, ceiling, fuel_t, dist_km, seg_km, evaluate)` takes the contrail model as a **callback**, so any model source can plug in. `frontend/js/model.js rerouteOptions()` mirrors it.

**Gaps found:**
- **Faked attribution:** `rail.js:22` invents a contrail ID, offset and confidence from the flight ID when `f.attribution` is missing. Live mode never sets it either.
- **Real attribution code is unused:** `pipeline/attribution.py` (wind-advection matching of contrail lines to tracks) is never called.
- **The existing Contrails.org client is wrong:** `sources/contrails_org.py` is a never-called placeholder with the wrong path (`/contrails`), wrong auth (Bearer) and the wrong geometry assumption.
- **The ML code is disconnected:** `backend/ml/` (OpenContrails loader → ash RGB, PCA shape features, 2-rule classifier) is used only by one unit test. There is no model and no torch/tf; nothing analyses imagery.
- **Misleading copy:**
  - `index.html` hard-codes "Everything on this page is simulated."
  - The ledger copy claims detected contrails are matched to aircraft; the table actually sums predictions.
- **Missing data file:** `backend/data/aircraftDatabase.csv` is absent (only needed by the existing `live` mode).

## 3. How the idea evolved, and why (do not re-litigate)

1. **Own CV detector (U-Net on OpenContrails) + attribution → rejected.** The Contrails API and Google already provide near-real-time GOES contrail detections and per-flight attributions, better than we'd build. Judges in this field would ask why we didn't use them.
2. **"This plane caused it" → "why did it happen, could it be avoided, was it forecast"** → then **per-flight blame was dropped**, because:
   - Ice-supersaturation forecasts at a specific place, time and flight level are near a **coin toss** (Gierens et al., ACP 2024). They are much better over larger regions (2025 ARPEGE study: hit rate ~80%, false-alarm ratio ~30% at 150 km tolerance).
   - Satellites cannot see ice-supersaturated air: it is clear air. Water-vapour channels blur several km vertically; sounders read dry in that air. A persistent contrail is itself the best evidence of supersaturation.
   - Altitude is chosen mostly by airline flight planners before departure, using forecasts. Mid-flight changes need ATC clearance, and heavy aircraft may not be able to climb. Nobody mandates contrail avoidance. The tool can't see these constraints, so per-flight blame is unfair even when the forecast flagged the area.
   - Counterfactual altitudes are never observed. "Avoidable" is always a model estimate.
3. **Current direction: decision support under uncertainty, plus a satellite verification loop.**
   - Avoidance pays off on average despite unreliable per-flight forecasts. Night-contrail warming is often many times the fuel cost of avoiding it.
   - The 2023 Google / American Airlines / Breakthrough Energy trial: 70 flights over 6 months, 54% less contrail length (satellite-verified) vs comparison flights. Small sample.
   - Teoh et al. 2020 modelled ~1.7% of flights diverted → ~59% less contrail EF for ~0.014% more fuel. These figures are from memory; verify before quoting.

## 4. The product now

**Pitch:** "Contrail forecasts are a coin toss for any single flight. We use satellites to measure exactly how good the forecast is, and turn that into odds an airline can act on."

**The loop:**
1. **Forecast track record (calibration).** For past flights, record what the forecast or model said at the flown level and whether the satellite saw a persistent contrail. Bin by forecast strength → observed rate. Example shape: strong 60%, weak 25%, none 5%. This measures the forecast, not airlines; we can't see which flights followed advice.
2. **Tonight's ranking.** For each flight and each option (filed FL, ±20, ±40 FL), look up the calibrated probability and compute expected net benefit (below). Rank flights by it.
3. **Neutral "why".** For contrails that formed: which stretch, which times, how deep the humid layer was (do the ±FL runs still show it?), night or day. Description, not verdict.
4. **Fleet-level ledger:** observed facts only (e.g. satellite-confirmed contrail warming per flight-hour by airline). No per-flight blame. No "missed opportunity" column.

**Expected net benefit of option d:**

```
E[d] = p0 · W0  −  pd · Wd  −  F_d
p0, pd = calibrated P(persistent contrail) at the filed level and at the new level
W0, Wd = warming if it forms (EF / AGWP_CO2, tCO2e) at each level
F_d    = extra fuel CO2 for the option (existing extra_fuel_t × 3.16)
```

- Both probabilities are needed. Using only p0 overstates the benefit and can recommend moving into another humid layer.
- Worked example (illustrative): 0.6·38 − 0.15·30 − 1.2 = **+17.1 t**.
- Known simplification: p0 and pd are correlated (the forecast may put the layer at the wrong height). Ignored for the hackathon.
- **Implementation:** add optional probabilities to `rerouteOptions()` (JS) and `build_options()` (Py), **defaulting to 1** so current behaviour and existing tests are unchanged.

**Stretch idea: "planes as humidity sensors".** Satellite-confirmed contrails, or their absence, from nearby flights at other levels within about an hour are observational evidence of the humid layer's vertical extent.
- **Use 1:** correct the odds after the fact.
- **Use 2:** in-flight updates: "planes ahead are contrailing at FL360; FL340 looks clear."
- **Caveat:** absence of a detection is weak evidence. The satellite misses thin or young contrails and ones under higher cloud.

**Primary audience:** airline flight planners. Researchers and regulators get the aggregates (size of the prize, forecast skill). Journalists get fleet-level observed facts.

## 5. External APIs (checked against docs 2026-10-10; response details unverified without a key)

**Contrails API (Breakthrough Energy)**
- Base URL `https://api.contrails.org`, header `x-api-key`. Keys by email to api@contrails.org.
- Research endpoints may change without notice; observation endpoints are "experimental, not complete datasets".

| Endpoint | Returns | Notes |
|---|---|---|
| `POST /v0/trajectory/cocip` | CoCiP on a supplied trajectory; output lists align 1:1 with input waypoints | Fleet mode batches several flights. `/v0/trajectory/cocip-contrail` gives contrail evolution. A vertical-profile notebook exists. **Unknown:** which met data it uses for past times (forecast vs reanalysis) |
| `GET /v1/observations/contrails-org/goes/L1/detections?time=` | NetCDF bitmap with per-pixel confidence | GOES-East full disk, every 10 min, vision-transformer model, since early 2024. Time is naive ISO, floored to 10 min |
| `GET /v1/observations/contrails-org/goes/L2/segments?time=` | JSON; WKT line strings | **In the GOES projection, not WGS84** (needs pyproj). No 1:1 claim with flights |
| `GET /v1/observations/google/geostationary/L4/attributions?flight=...` | Per flight: `attributions[{start_time,end_time,length_meters}]`, `observations[{time,length_meters,source}]` | Pass-through of Google Contrail Watch. Flight id `{IATA carrier}~{number}~{YYYY-MM-DD}~{dep IATA}`, e.g. `AF~6113~2025-02-12~TLS`; case-sensitive; repeatable. **Per-flight lookup only, no bbox query** |
| `GET /v1/adsb/telemetry` | Hourly Parquet | Parameters unverified. Flight-number format may differ from attribution ids (`AF6113` vs `6113`) |
| Forecast API `/v1/grids` | NetCDF at standard FLs | Variables and past-forecast availability unverified |
| Forecast API `/v1/regions` | GeoJSON avoidance polygons per threshold | Variables and past-forecast availability unverified |

**Google Contrails API v2** (direct; access on request; data CC BY-NC 4.0)
- Attribution fields:
  - `flightDetails`: carrier, number, date, icao24, origin/dest, callsign, analysed distance.
  - `contrail` aggregate: **absent means "not analysed", NOT "no contrail"**.
  - `segments`, each with a method: observation-only, CoCiP, or observation-enhanced CoCiP.
  - `effectiveEnergyForcingJoules`.
- Satellites: GOES 2019–2026; Meteosat FCI 2024–2026 (beta); Himawari 2025–2026.
- Release notes: GOES-West detections added 2026-06-23; `GetAttributionMetrics` (aggregates by bounds, time and method) added 2026-08-03.

**Calibration data caveats (must handle):**
- Negatives need care: Google's absent = not analysed. Option: check L1 detections near the wind-advected track, which gives `pipeline/attribution.py` a real job.
- Detection misses mean observed rates are a lower bound; present them that way.
- If past forecasts aren't retrievable, archive them going forward. Meanwhile, calibrate whatever met the trajectory endpoint uses, and **label it "model skill", not "forecast skill"**.

## 6. Build plan (additive). New mode `UAL_MODE=api`

**Order:** demo-mode version first (works offline today, no key) → API mode against documented shapes and fixtures → fixes once real responses come back.

**New files**
- `backend/app/sources/contrails_api.py`: real client for the endpoints above. Leave `contrails_org.py` untouched.
- `backend/app/pipeline/api_scenario.py`:
  - Output: same JSON shape as `scenario.py` plus per-flight `explain` and probability fields.
  - Reuses `build_options()` with an `evaluate` callback that calls `/v0/trajectory/cocip`.
- `backend/app/pipeline/explain.py`: neutral "why" from per-waypoint output. Pure; usable by `live` too.
- `backend/app/pipeline/calibration.py`: build the forecast-strength → observed-rate table and look up probabilities.
- `backend/scripts/check_contrails_api.py`:
  - Who runs it: the key holder.
  - What it does: read-only calls to each endpoint; reports which ones the key unlocks.
  - Output: sanitised sample responses (key stripped) saved to `backend/tests/fixtures/`.
- `backend/scripts/archive_forecasts.py`: only if past forecasts aren't available.
- **Snapshot for the demo:** the key holder builds the demo night once to a JSON file committed to the repo (e.g. `frontend/data/snapshot.json`), so the demo needs no key or network. The frontend load order becomes: API → snapshot → simulation.
- `backend/tests/test_explain.py`, `test_calibration.py`, `test_contrails_api.py` (using fixtures).
- `frontend/js/ui/explain.js`: "why" panel plus probability display.
- `frontend/js/sim/forecast.js`: demo-mode "forecast" = perturbed copy of the sim atmosphere (blob position/FL/strength errors) vs the sim "truth"; produces a simulated calibration table so the offline demo shows the full loop.
- Optional `frontend/js/ui/calibration.js`: "forecast track record" reliability chart section (load the `dataviz` skill before charting).

**Small edits to existing files (behaviour-preserving)**
- `backend/app/main.py`: route `/api/scenario` to `api_scenario` when mode is `api` (~5 lines).
- `backend/app/config.py`, `.env.example`: reuse `CONTRAILS_ORG_URL` (default `https://api.contrails.org`) and `CONTRAILS_ORG_KEY`.
- `backend/requirements.txt`: pandas, pyarrow (Parquet); pyproj (GOES projection); xarray/netCDF4 if not pulled in.
- `backend/app/pipeline/reroute.py`, `frontend/js/model.js`: optional probabilities defaulting to 1 (formula above).
- `frontend/js/data.js`:
  - Accept mode `api` like `live`.
  - Snapshot fallback.
  - Pass new fields through.
- `frontend/js/ui/rail.js`: if the flight has real `explain`/probability data, show the new panel in place of the faked attribution block; otherwise render as now.
- `frontend/js/ui/ledger.js`: extra observed-only columns, shown only when the data exists.
- `frontend/js/sim/fleet.js`: one line attaching demo forecast/probabilities.
- `frontend/index.html`: track-record section; mode-dependent caveat copy.
- `README.md`: new-mode section.

**Untouched:** existing `live` pipeline, `attribution.py` (until reused), `backend/ml/`, lab section, space events, score chart, theme/util/geo.

**Keep in sync:** `frontend/js/config.js` ↔ `backend/app/constants.py`; `model.js` ↔ `reroute.py`; `sim/space.js` ↔ `space_events.py`.

## 7. Domain notes (for explaining to the user and judges)

- **Formation:** hot, humid exhaust mixes with air at about −40 °C or colder; vapour freezes on soot and other particles (Schmidt–Appleman criterion). Most jets at cruise meet it.
- **Persistence:** only in ice-supersaturated air, otherwise the trail evaporates in seconds to a minute. These layers are often a few hundred metres to ~1 km deep, which is why ±2,000 ft works. About 2% of flights cause about 80% of contrail warming (Teoh et al. 2020, Japan).
- **Warming:**
  - Night contrails only trap heat.
  - Daytime contrails also reflect sunlight; some net-cool.
  - Bright surfaces or cloud below reduce the reflection's importance.
- **Aircraft effects are secondary and mixed:**
  - More efficient engines form contrails slightly *more* readily (cooler exhaust). Schumann 2000: in a side-by-side flight, the A340 made a contrail and the B707 didn't.
  - Lean-burn, low-soot engines and low-aromatic fuels (incl. many SAFs) mean fewer, larger ice crystals and weaker contrails (~50–70% fewer crystals; Voigt et al. 2021).
  - The last two citations are from memory; verify before quoting.
- **Flight planning runs on forecasts:**
  - World Area Forecast Centres (Met Office, NOAA) issue winds and temperatures aloft.
  - The NAT tracks are redrawn twice daily.
  - Aircraft report temperature and wind; very few measure humidity, and mostly at lower altitudes.
  - Standard planning has no humidity or contrail layer; contrail forecasts are an add-on built from model humidity, the least reliable model output.

## 8. Open questions

1. User go-ahead to start implementing (demo mode first).
2. Which Contrails API products the user's key unlocks (run the check script).
3. Met data behind `/v0/trajectory/cocip` for past times; whether past forecast grids/regions are retrievable.
4. How to obtain reliable negatives for calibration.
5. Demo night and region (ideally a night with many observed North Atlantic contrails; GOES-East covers the western and central Atlantic well, the European side poorly).
6. Whether to keep the off-story "Cloud or contrail?" lab section (currently: keep, per additive constraint).

## Sources

- Contrails API docs: https://apidocs.contrails.org/ — observations: https://apidocs.contrails.org/observations.html — attribution notebook: https://apidocs.contrails.org/notebooks/flight-attribution.html — GOES detections: https://apidocs.contrails.org/notebooks/goes_detections.html — Research API: https://apidocs.contrails.org/notebooks/research_api.html — fleet mode: https://apidocs.contrails.org/notebooks/fleet_mode.html — vertical profile: https://apidocs.contrails.org/notebooks/vertical_profile.html
- Google Contrails API attributions: https://developers.google.com/contrails/reference/v2/attributions/overview — release notes: https://developers.google.com/contrails/release_notes
- Gierens et al., ACP 2024: https://acp.copernicus.org/articles/24/7911/2024/ — ACP 2025: https://acp.copernicus.org/articles/25/17253/2025/ — ARPEGE ISSR verification: https://bibliotheque.meteo.fr/pub/DOC00060840-modeling-and-verifying-ice-supersaturated-regions.html — MIT nowcasting: https://dspace.mit.edu/handle/1721.1/155350
- AA/Google trial (Aug 2023): https://news.aa.com/news/news-details/2023/American-Airlines-participates-in-first-of-its-kind-research-on-contrail-avoidance-CORP-OTH-08/default.aspx
