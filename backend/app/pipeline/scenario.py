"""Build a live scenario: OpenSky tracks + ERA5 met -> CoCiP per altitude option -> JSON for the UI."""
from __future__ import annotations

import json
import logging
from datetime import timedelta

from ..config import Settings
from ..constants import AIRCRAFT, CO2_PER_FUEL, DEFAULT_CEILING, N_WAYPOINTS
from ..space_events import SPACE_EVENTS
from ..sources.contrails_org import ContrailsOrgClient
from ..sources.era5 import load_met
from ..sources.opensky import AircraftDatabase, OpenSkyClient, cruising_aircraft
from . import cocip
from .geometry import haversine_km, resample
from .humidity_grid import build_grid
from .observed import attribute_observations
from .reroute import build_options
from .wind import wind_from_met

log = logging.getLogger(__name__)


def _fl(alt_m: float) -> int:
    """Round a barometric altitude to the nearest flight level in steps of 10."""
    return int(round(alt_m / 0.3048 / 1000)) * 10


def build_live_scenario(s: Settings) -> dict:
    start, end = s.start, s.start + timedelta(hours=s.hours)
    t0 = int(start.timestamp())
    mid = t0 + s.hours * 1800

    log.info("Loading ERA5 %s – %s", start, end)
    met, rad = load_met(start - timedelta(hours=1), end + timedelta(hours=1))

    log.info("Fetching aircraft from OpenSky")
    client = OpenSkyClient(s.opensky_client_id, s.opensky_client_secret)
    if not s.opensky_aircraft_db.exists():
        log.warning("%s is missing: aircraft types and operators will be unknown (see .env.example)", s.opensky_aircraft_db)
    db = AircraftDatabase(s.opensky_aircraft_db)
    aircraft = cruising_aircraft(client, db, s.bbox, at=mid, limit=s.max_flights)

    flights = []
    for k, ac in enumerate(aircraft):
        pts_t = [(p.time - t0) / 3600 for p in ac.track]
        lons = resample([p.lon for p in ac.track], pts_t, N_WAYPOINTS)
        lats = resample([p.lat for p in ac.track], pts_t, N_WAYPOINTS)
        hrs = resample(pts_t, pts_t, N_WAYPOINTS)
        alts = [p.baro_alt_m for p in ac.track if p.baro_alt_m]
        fl = _fl(max(alts)) if alts else 350
        seg = [haversine_km((lons[i], lats[i]), (lons[i + 1], lats[i + 1])) for i in range(N_WAYPOINTS - 1)] + [0.0]
        dist = sum(seg)
        times = cocip.hours_to_datetimes(start, hrs)

        def run(fl_at):
            return cocip.evaluate(met, rad, ac.callsign or ac.icao24, ac.type_code, lons, lats, times, fl_at)

        try:
            base, fuel_t = run([fl] * N_WAYPOINTS)

            def evaluate(new_fl, window):
                w0, w1 = window
                res, _ = run([new_fl if w0 <= i <= w1 else fl for i in range(N_WAYPOINTS)])
                return res

            ceiling = AIRCRAFT.get(ac.type_code, ("", DEFAULT_CEILING))[1]
            opts = build_options(base, fl, ceiling, fuel_t, dist, seg, evaluate)
        except Exception:  # one bad track should not sink the whole scenario
            log.exception("CoCiP failed for %s", ac.callsign)
            continue

        flights.append({
            "id": k, "cs": ac.callsign or ac.icao24,
            "carrier": {"code": ac.operator_icao, "name": ac.operator_icao},
            "type": ac.type_code, "o": ac.origin, "d": ac.destination,
            "dist": dist, "dur": hrs[-1] - hrs[0], "dep": hrs[0], "arr": hrs[-1], "fl": fl,
            "pts": [[lons[i], lats[i], hrs[i]] for i in range(N_WAYPOINTS)], "seg": seg,
            "fuel": fuel_t, "co2": fuel_t * CO2_PER_FUEL,
            "base": {"iss": base.issr, "km": base.km, "ef": base.ef}, "opts": opts,
        })

    n_obs = attach_attributions(s, met, flights) if s.contrails_org_key else None

    return {
        "label": f"LIVE · {start:%d %b %Y %H:%MZ} + {s.hours} H".upper(),
        "start_hour": start.hour + start.minute / 60, "hours": s.hours,
        "atmosphere": build_grid(met, start, s.hours, s.bbox),
        "flights": flights,
        "space_events": SPACE_EVENTS,
        "observations": n_obs,  # satellite detections fetched; None when Contrails.org is not configured
    }


def attach_attributions(s: Settings, met, flights: list[dict]) -> int:
    """Fetch GOES contrail detections for the window, match each to a flight by wind advection, and
    set flight["attribution"] on the flights that made one. Returns the number of detections."""
    start, end = s.start, s.start + timedelta(hours=s.hours)
    client = ContrailsOrgClient(s.contrails_org_key, s.contrails_org_url)
    detections = client.segments_between(start, end, s.bbox, step_min=s.obs_step_min)
    log.info("Contrails.org: %d detections in the window", len(detections))
    if not detections:
        return 0
    wind = wind_from_met(met, start)
    tracks = {f["id"]: [tuple(p) for p in f["pts"]] for f in flights}
    obs = [(d.id, (d.observed_at - start).total_seconds() / 3600, d.line) for d in detections]
    matches = attribute_observations(obs, tracks, wind)
    for f in flights:
        f["attribution"] = matches.get(f["id"])
    log.info("Attributed detections to %d flights", len(matches))
    return len(detections)


def cached_scenario(s: Settings) -> dict:
    path = s.cache_dir / f"scenario-{s.start:%Y%m%dT%H%M}-{s.hours}h.json"
    if path.exists():
        return json.loads(path.read_text())
    sc = build_live_scenario(s)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sc))
    return sc
