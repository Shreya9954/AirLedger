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
│       ├── sim/              Simulated humidity field, fleet, space events
│       └── ui/               map, rail (flight + reroute), score, ledger, lab, theme
└── backend/                  FastAPI service
    ├── app/
    │   ├── main.py           /api/health, /api/scenario, /api/space-events; serves frontend/
    │   ├── config.py         Settings from environment (.env.example)
    │   ├── constants.py      AGWP, fuel→CO₂, reroute options, aircraft ceilings
    │   ├── scoring.py        The shared tCO₂e score
    │   ├── space_events.py   Launch / re-entry table (illustrative values)
    │   ├── sources/          OpenSky, ERA5 (via pycontrails), Contrails.org clients
    │   └── pipeline/         scenario builder, CoCiP runner, humidity grid,
    │                         reroute options, contrail→flight attribution
    ├── ml/                   Stretch goal: OpenContrails loader, shape features, rule classifier
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

## Live mode: what it needs

| Source | Used for | Setup |
|---|---|---|
| OpenSky Network | Aircraft tracks, origin/destination, ICAO24 for attribution | API client credentials in `.env`; download `aircraftDatabase.csv` to `backend/data/` for aircraft types |
| Copernicus ERA5 | Temperature, humidity and winds at cruise levels | CDS account; key in `.env` or `~/.cdsapirc`. ERA5 lags about 5 days, so use ECMWF HRES for tonight's forecast |
| pycontrails (CoCiP) | Contrail formation, lifetime, energy forcing; PS model fuel burn | `pip install pycontrails[ecmwf]` |
| Contrails.org API | Observed contrails for validation and attribution | Base URL and key in `.env`. **The client's endpoint path and fields are placeholders; check them against the API docs** |
| Google OpenContrails | Training data for the cloud-vs-contrail model | Download records, then use `backend/ml/opencontrails.py` |

The live pipeline (`pipeline/scenario.py`, `pipeline/cocip.py`, `pipeline/humidity_grid.py`, `sources/*`) has not been run against the real services yet. Expect to adjust variable names or API details on the first run. Unit tests cover only the pure logic.

## Model notes

- Score: `tCO₂e = fuel × 3.16 + EF_contrail ÷ 1.48×10¹² J/t + stratospheric particle term`. Contrail efficacy is not applied.
- Reroutes change altitude only across the humid stretch plus 100 km each side, in ±2,000 ft steps that keep the semicircular flight-level rule. Fuel penalty is a simple percentage model (`pipeline/reroute.py`); swap in the PS aircraft performance model for per-type numbers.
- Launch and re-entry values are illustrative placeholders until a published particle-forcing factor exists.
- Demo mode uses fictional carriers. Live mode uses real operators from OpenSky metadata.
