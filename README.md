# Upper Air Ledger

A live map that predicts where aircraft contrails will form and persist, prices the altitude change that would avoid them, and puts rocket launches and satellite re-entries on the same climate scale (tCO₂e over 100 years).

Audiences: airline flight-operations and sustainability teams (reroute decisions), regulators and researchers (one shared metric), and journalists and watchdogs (warming attributed to carriers and aircraft types).

## Layout

```
upper-air-ledger/
├── frontend/                 Static site, no build step (ES modules)
│   ├── index.html
│   ├── css/styles.css        Theme tokens (light + dark), layout
│   └── js/
│       ├── main.js           Entry point: wires everything together
│       ├── config.js         Shared constants (mirrors backend/app/constants.py)
│       ├── util.js           PRNG, geodesy, formatting
│       ├── geo.js            Map bounds, coastlines, airports
│       ├── model.js          Contrail EF, track evaluation, reroute options (demo mode)
│       ├── data.js           Loads a scenario from the API, else simulates one
│       ├── attribution.js    Matches satellite contrail detections to flights (mirrors the backend)
│       ├── sim/              Simulated humidity field, fleet, space events
│       └── ui/               map, rail (flight + reroute), score, ledger, lab, theme
└── backend/                  FastAPI service
    ├── app/
    │   ├── main.py           /api/health, /api/scenario, /api/space-events; serves frontend/
    │   ├── config.py         Settings from environment (.env.example)
    │   ├── constants.py      AGWP, fuel→CO₂, reroute options, aircraft ceilings
    │   ├── scoring.py        The shared tCO₂e score
    │   ├── space_events.py   Launch / re-entry table (illustrative values)
    │   ├── sources/          OpenSky, ERA5 (via pycontrails), Contrails.org GOES detections
    │   └── pipeline/         scenario builder, CoCiP runner, humidity grid, reroute options,
    │                         cruise wind, contrail→flight attribution of satellite detections
    ├── ml/                   Stretch goal: OpenContrails loader, shape features, rule classifier,
    │                         and `python -m ml.evaluate <records>` to score the rule on real records
    └── tests/                pytest suite for scoring, reroute, attribution, shape features
```

## Run it

**Frontend only (simulated night):** the page needs to be served over HTTP because it uses ES modules.

```sh
cd frontend
python3 -m http.server 8000
# open http://localhost:8000
```

**Hosted:** every push to `main` publishes `frontend/` to GitHub Pages at https://shreya9954.github.io/Contrails/ (simulated night only; there is no backend there).

**With the backend:**

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # then fill in credentials
set -a; source .env; set +a
.venv/bin/uvicorn app.main:app --reload
# open http://localhost:8000
```

With `UAL_MODE=demo` (the default), the API reports demo mode and the frontend simulates the night itself. With `UAL_MODE=live`, `/api/scenario` builds a real scenario and caches it under `.cache/`. The page shows `LIVE` or `SIMULATED FEED` in the header.

**Tests:**

```sh
cd backend
.venv/bin/python -m pytest
```

## Real night (the default view)

The site opens on a real window of North Atlantic traffic, built offline into `frontend/data/real-night.json` and committed, so it works without keys or a backend:

- **Observed:** flight tracks from the OpenSky Network's public REST API, plus aircraft type and operator from its aircraft database.
- **Forecast:** temperature, humidity over ice and wind at 300, 250 and 200 hPa from **ECMWF IFS** and **NOAA GFS**, via Open-Meteo (CC BY 4.0). Their humidity is reported relative to ice at cruise temperatures, capped at 100%; 95% or more counts as ice-saturated.
- **Model:** a screening model (`backend/app/pipeline/screening.py`): the Schmidt–Appleman criterion (Schumann 1996) plus ice saturation, with illustrative warming per km. It runs separately under each forecast. Altitude options are priced with `reroute.py`, and a change is recommended when its net benefit is positive, ranked first by whether both forecasts agree.
- **Validation:** the page reports how often the two forecasts agree where either predicts a persistent contrail (the real forecast uncertainty), ranges on every estimate, and the published 2023 Google/American Airlines/Breakthrough Energy trial. Satellite comparison runs only with `CONTRAILS_ORG_KEY`; otherwise the page says it was not checked.
- **Fairness:** who benefits and who pays, whether changes move noise or pollution onto communities (all changes are at cruise altitude), and the limits of the data.

Rebuild the snapshot from `backend/` (about 5 minutes; Open-Meteo's free tier limits requests per minute, and downloads are cached in `backend/.cache/realnight/`):

```sh
.venv/bin/python -m app.pipeline.real_night --fresh
```

The header button switches between the real night and the simulation.

## Space ledger

Below the contrail sections, the space ledger shows what real rocket launches and re-entering spacecraft leave in the upper atmosphere, by altitude, with who launched them and whose hardware came down. Every number is tagged Fact, Estimate or Research and links to its source. It needs no API keys.

- **Data:** CelesTrak (satellite catalogue and orbits), GCAT (masses and owners) and Launch Library 2 (launches). Emission factors from Barker, Marais & McDowell (2024), *Scientific Data* 11, 1079; aviation comparison from Teoh et al. (2024), *ACP* 24, 725.
- **Offline:** the page loads the API, then the committed snapshot in `frontend/data/space-snapshot.json` and `space-orbits.json`, then a labelled sample. Refresh the snapshot from `backend/` with `.venv/bin/python -m app.space.snapshot` (set `LL2_BASE_URL=https://lldev.thespacedevs.com/2.3.0` while developing; production Launch Library allows 15 requests an hour).
- **Be polite to CelesTrak:** downloads are cached in `backend/.cache/space/`, and after any failure the code backs off that host for an hour. CelesTrak blocks addresses that retry.
- **Licences:** data from GCAT (J. McDowell, planet4589.org/space/gcat), CC-BY. satellite.js 6.0.1 is vendored under its MIT licence in `frontend/js/space/vendor/`.
- Data formats and sources in detail: [docs/space-ledger.md](docs/space-ledger.md).

## Live mode: what it needs

| Source | Used for | Setup |
|---|---|---|
| OpenSky Network | Aircraft tracks, origin/destination, ICAO24 → aircraft type and operator | API client credentials in `.env`. Aircraft database (90 MB, not in git): `curl -o backend/data/aircraftDatabase.csv https://s3.opensky-network.org/data-samples/metadata/aircraftDatabase.csv` |
| Copernicus ERA5 | Temperature, humidity and winds at cruise levels | CDS account; key in `.env` or `~/.cdsapirc`. ERA5 lags about 5 days, so use ECMWF HRES for tonight's forecast |
| pycontrails (CoCiP) | Contrail formation, lifetime, energy forcing; PS model fuel burn | `pip install pycontrails[ecmwf]` |
| Contrails.org API | Contrail line segments detected in GOES-East images (`/v1/observations/contrails-org/goes/L2/segments`), matched to flights by wind advection | `CONTRAILS_ORG_KEY` in `.env` (from api@contrails.org, sent as `x-api-key`). Without it, live mode still runs and the page says satellite confirmation is off. The provider marks this endpoint experimental |
| Google OpenContrails | Scoring the shape rule now; training data for a future model | Download records, then `cd backend && .venv/bin/python -m ml.evaluate <folder>` |

The live pipeline (`pipeline/scenario.py`, `pipeline/cocip.py`, `pipeline/humidity_grid.py`, `sources/*`) has not been run against the real services yet. Expect to adjust variable names or API details on the first run. Unit tests cover only the pure logic.

## Model notes

- Score: `tCO₂e = fuel × 3.16 + EF_contrail ÷ 1.48×10¹² J/t + stratospheric particle term`. Contrail efficacy is not applied.
- Reroutes change altitude only across the humid stretch plus 100 km each side, in ±2,000 ft steps that keep the semicircular flight-level rule. Fuel penalty is a simple percentage model (`pipeline/reroute.py`); swap in the PS aircraft performance model for per-type numbers.
- Launch and re-entry values are illustrative placeholders until a published particle-forcing factor exists.
- Demo mode uses fictional carriers. Live mode uses real operators from OpenSky metadata.
