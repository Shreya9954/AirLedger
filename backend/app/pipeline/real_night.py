"""Build the "real night" snapshot: observed flight tracks + two forecasts + screening model.

    cd backend && .venv/bin/python -m app.pipeline.real_night [--hours 10] [--max-flights 90]

Writes frontend/data/real-night.json, which the site loads by default. No API keys needed:
  * OBSERVED: flight tracks from the OpenSky Network (anonymous REST API; ADS-B receivers on land,
    so the mid-Atlantic is a coverage gap) and aircraft type/operator from OpenSky's aircraft database.
  * FORECAST: temperature, humidity over ice and wind at 300/250/200 hPa from ECMWF IFS and NOAA GFS,
    via Open-Meteo.
  * MODEL: where persistent contrails form (screening.py), their illustrative warming, and the
    altitude options (reroute.py), computed separately under each forecast.
  * SATELLITE: GOES contrail detections from Contrails.org, matched to flights, only when
    CONTRAILS_ORG_KEY is set. Otherwise the snapshot says so; nothing is invented in its place.
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..config import settings
from ..constants import AGWP_CO2_J_PER_T, CO2_PER_FUEL, CRUISE_END, CRUISE_START, DEFAULT_CEILING, N_WAYPOINTS
from ..space_events import SPACE_EVENTS
from ..sources.openmeteo import LEVELS_HPA, fetch_grid, hpa_to_fl
from ..sources.opensky import AircraftDatabase, OpenSkyClient
from .geometry import haversine_km, resample
from .reroute import build_options
from .screening import Sampler, evaluate_track
from .wind import GridWind

log = logging.getLogger(__name__)
OUT = Path(__file__).resolve().parents[3] / "frontend" / "data" / "real-night.json"
CACHE = settings.cache_dir / "realnight"
MODELS = ("ecmwf", "gfs")
PRIMARY = "ecmwf"
CONTRAIL_LOW, CONTRAIL_HIGH = 0.5, 1.8  # same factor-of-two range as scoring.py

# Fuel burn at cruise (t/h) and relative contrail strength, by ICAO type family. Mirrors the
# demo table in frontend/js/config.js; families not listed fall back to a size class.
FAMILIES = [
    (("A38",), 11.5, 1.3, 430), (("B74",), 10.5, 1.3, 430), (("B77",), 7.4, 1.25, 410), (("A35",), 5.8, 1.0, 410),
    (("B78",), 5.4, 1.0, 410), (("A33", "A34"), 5.7, 1.15, 410), (("B76",), 5.1, 1.15, 410), (("A30",), 5.0, 1.15, 400),
    (("MD1",), 7.0, 1.2, 410), (("B75",), 3.5, 0.9, 420), (("B73", "B38", "B39"), 2.6, 0.8, 410),
    (("A32", "A31", "A20N", "A21N", "A19N"), 2.5, 0.7, 390), (("E1", "E2", "CRJ", "BCS", "A22"), 1.7, 0.6, 410),
]
DEFAULT_BURN, DEFAULT_F = 4.0, 1.0
CARGO = {"FDX", "UPS", "GTI", "CLX", "ABW", "BOX", "CKS", "ATN", "NCR", "MPH", "GEC", "AJT", "DHK", "BCS", "PAC"}


def aircraft_class(type_code: str) -> tuple[float, float, int, bool]:
    """(burn t/h, contrail factor, ceiling FL, known?)."""
    for prefixes, burn, f, ceil in FAMILIES:
        if any(type_code.startswith(p) for p in prefixes):
            return burn, f, ceil, True
    return DEFAULT_BURN, DEFAULT_F, DEFAULT_CEILING, False


# --------------------------------------------------------------------------- download (cached)


def _cached(name: str, fetch):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if path.exists():
        return json.loads(path.read_text())
    data = fetch()
    path.write_text(json.dumps(data))
    return data


def fetch_tracks(bbox, max_flights: int, now: int) -> dict:
    client = OpenSkyClient(settings.opensky_client_id, settings.opensky_client_secret)
    states = client.states(bbox)
    cruising = sorted((s for s in states if s[7] and s[7] > 9000 and not s[8]), key=lambda s: s[0])
    step = max(1, len(cruising) // (max_flights * 2))  # spread the sample across the box
    tracks = []
    for s in cruising[::step]:
        if len(tracks) >= max_flights:
            break
        try:
            pts = client.track(s[0], 0)
        except httpx.HTTPError as exc:
            log.warning("track %s failed: %s", s[0], exc)
            if getattr(getattr(exc, "response", None), "status_code", 0) == 429:
                break  # rate limited: stop politely with what we have
            continue
        if len(pts) >= 10:
            tracks.append({"icao24": s[0], "callsign": (s[1] or "").strip(),
                           "path": [[p.time, p.lat, p.lon, p.baro_alt_m] for p in pts if not p.on_ground]})
        time.sleep(0.4)
    return {"fetched_at": now, "states_seen": len(states), "cruising": len(cruising), "tracks": tracks}


# --------------------------------------------------------------------------- build


def _fl(alt_m: float) -> float:
    return alt_m / 0.3048 / 100


def _robust(opts_by_model: dict) -> dict:
    """Pick the altitude change that helps under BOTH forecasts, with an uncertainty range."""
    best = None
    for d in (-40, -20, 20, 40):
        per = [opts_by_model[m].get(str(d)) for m in MODELS]
        if any(o is None for o in per) or all(o.get("km", 0) == opts_by_model[m]["0"]["km"] for o, m in zip(per, MODELS)):
            continue
        nets = [o["net"] for o in per]
        avoided = [o["avoided"] for o in per]
        extra = per[0]["extraCO2"]
        rng = (min(a * (CONTRAIL_LOW if a > 0 else CONTRAIL_HIGH) for a in avoided) - extra,
               max(a * (CONTRAIL_HIGH if a > 0 else CONTRAIL_LOW) for a in avoided) - extra)
        cand = {"d": d, "net_by_model": dict(zip(MODELS, nets)), "avoided_by_model": dict(zip(MODELS, avoided)),
                "extraCO2": extra, "net_mean": sum(nets) / 2, "net_range": rng, "agree": all(n > 0 for n in nets)}
        key = (cand["agree"], cand["net_mean"])
        if cand["net_mean"] > 0 and (best is None or key > (best["agree"], best["net_mean"])):
            best = cand
    return best


def build(raw_tracks: dict, grids: dict, db: AircraftDatabase, hours: float, now: int, bbox=None) -> dict:
    t0 = int((now - hours * 3600) // 3600 * 3600)  # window start, on the hour
    lon_min, lat_min, lon_max, lat_max = bbox or settings.bbox
    samplers = {m: Sampler(grids[m], t0) for m in MODELS}
    flights, agree_pts, total_pts, pts_either, pts_both = [], 0, 0, 0, 0
    for tr in raw_tracks["tracks"]:
        # Cruise points inside the window and inside the forecast grid (outside it we have no humidity).
        path = [p for p in tr["path"] if p[3] and p[3] > 7500 and p[0] >= t0
                and lat_min <= p[1] <= lat_max and lon_min <= p[2] <= lon_max]
        if len(path) < 10 or path[-1][0] - path[0][0] < 1800:
            continue
        ts = [(p[0] - t0) / 3600 for p in path]
        lats = resample([p[1] for p in path], ts, N_WAYPOINTS)
        lons = resample([p[2] for p in path], ts, N_WAYPOINTS)
        fls = resample([_fl(p[3]) for p in path], ts, N_WAYPOINTS)
        hrs = resample(ts, ts, N_WAYPOINTS)
        pts = [(lons[i], lats[i], hrs[i]) for i in range(N_WAYPOINTS)]
        seg = [haversine_km((lons[i], lats[i]), (lons[i + 1], lats[i + 1])) for i in range(N_WAYPOINTS - 1)] + [0.0]
        dist = sum(seg)
        cruise_fl = int(round(statistics.median(fls[CRUISE_START:CRUISE_END]) / 10) * 10)
        type_code, op = db.lookup(tr["icao24"])
        op = op or tr["callsign"][:3]
        burn, tf, ceil, known = aircraft_class(type_code)
        dur = hrs[-1] - hrs[0]
        fuel = burn * dur

        per_model = {}
        for m in MODELS:
            sm = samplers[m]
            base = evaluate_track(sm, pts, seg, fls, t0, CRUISE_START, CRUISE_END, tf)

            def evaluate(new_fl, window, sm=sm):
                w0, w1 = window
                shift = new_fl - cruise_fl
                return evaluate_track(sm, pts, seg, [f + shift if w0 <= i <= w1 else f for i, f in enumerate(fls)],
                                      t0, CRUISE_START, CRUISE_END, tf)
            per_model[m] = {"base": base, "opts": build_options(base, cruise_fl, ceil, fuel, dist, seg, evaluate)}
        e_iss, g_iss = per_model["ecmwf"]["base"].issr, per_model["gfs"]["base"].issr
        agree = sum(e_iss[i] == g_iss[i] for i in range(CRUISE_START, CRUISE_END))
        agree_pts += agree
        total_pts += CRUISE_END - CRUISE_START
        pts_either += sum(1 for i in range(CRUISE_START, CRUISE_END) if e_iss[i] or g_iss[i])
        pts_both += sum(1 for i in range(CRUISE_START, CRUISE_END) if e_iss[i] and g_iss[i])

        prim = per_model[PRIMARY]
        rec = _robust({m: per_model[m]["opts"] for m in MODELS})
        if rec:
            w = prim["opts"]["best"] if prim["opts"]["best"]["d"] == rec["d"] else None
            iss = [i for i in range(CRUISE_START, CRUISE_END) if e_iss[i] or g_iss[i]]
            pad = max(1, round(100 / (dist / N_WAYPOINTS))) if dist else 1
            i0, i1 = max(0, iss[0] - pad), min(N_WAYPOINTS - 1, iss[-1] + pad)
            night = sum(1 for i in iss if not (6 <= (( (t0 + pts[i][2] * 3600) / 3600) % 24 + pts[i][0] / 15) % 24 < 18))
            rec.update({
                "from": [round(lons[i0], 2), round(lats[i0], 2), round(hrs[i0], 3)],
                "to": [round(lons[i1], 2), round(lats[i1], 2), round(hrs[i1], 3)],
                "new_fl": cruise_fl + rec["d"],
                "reasons": [r for r in (
                    f"predicted persistent contrail: {round(prim['base'].km)} km (ECMWF), {round(per_model['gfs']['base'].km)} km (GFS)",
                    "mostly at night, when contrails only trap heat" if iss and night / len(iss) > 0.5 else None,
                ) if r],
                "matched_primary": w is not None,
            })

        def pack(r):
            return {"iss": r.issr, "km": round(r.km, 1), "ef": r.ef}
        flights.append({
            "id": len(flights), "icao24": tr["icao24"], "cs": tr["callsign"] or tr["icao24"],
            "carrier": {"code": op, "name": db.operator_name(op) or op}, "cargo": op in CARGO,
            "type": type_code or "UNKN", "type_known": known, "o": "—", "d": "—",
            "dist": dist, "dur": dur, "dep": hrs[0], "arr": hrs[-1], "fl": cruise_fl,
            "pts": [[round(lons[i], 4), round(lats[i], 4), round(hrs[i], 4)] for i in range(N_WAYPOINTS)],
            "seg": [round(x, 2) for x in seg], "fuel": fuel, "co2": fuel * CO2_PER_FUEL,
            "base": pack(prim["base"]), "opts": prim["opts"],
            "models": {m: {"base": pack(per_model[m]["base"]), "best": per_model[m]["opts"]["best"]} for m in MODELS},
            "agreement": agree / (CRUISE_END - CRUISE_START),
            "observed": {"points": len(path), "first_unix": path[0][0], "last_unix": path[-1][0]},
            "recommendation": rec, "attribution": None,
        })

    # Map layer: ECMWF RHi on the grid, scaled so >= 1 means at or above the 95 % persistence threshold.
    g = grids[PRIMARY]
    keep = [k for k, t in enumerate(g.times) if t0 - 3600 <= t <= t0 + (hours + 1) * 3600]
    order = sorted(range(len(LEVELS_HPA)), key=lambda k: -LEVELS_HPA[k])  # ascending flight level
    values = [round(float(g.rhi[t, k, j, i]) / 0.95, 3) for t in keep for k in order
              for j in range(len(g.lats)) for i in range(len(g.lons))]
    u = float(sum(g.u250[keep].ravel()) / g.u250[keep].size)
    atmosphere = {
        "lon0": float(g.lons[0]), "dlon": float(g.lons[1] - g.lons[0]), "nlon": len(g.lons),
        "lat0": float(g.lats[0]), "dlat": float(g.lats[1] - g.lats[0]), "nlat": len(g.lats),
        "levels": [round(hpa_to_fl(LEVELS_HPA[k])) for k in order],
        "t0": (g.times[keep[0]] - t0) / 3600, "dt": 1.0, "nt": len(keep), "values": values,
        "wind": round(u * 3600 / (111320 * 0.643), 3),  # mean 250 hPa eastward drift, degrees lon per hour at 50°N
    }

    recs = [f for f in flights if f["recommendation"]]
    with_contrail = {m: sum(1 for f in flights if f["models"][m]["base"]["km"] > 0) for m in MODELS}
    both = sum(1 for f in flights if all(f["models"][m]["base"]["km"] > 0 for m in MODELS))
    either = sum(1 for f in flights if any(f["models"][m]["base"]["km"] > 0 for m in MODELS))
    start = datetime.fromtimestamp(t0, timezone.utc)
    return {
        "schema": "real-night/1",
        "label": f"N. ATLANTIC · {start:%d %b %Y %H:%M}–{datetime.fromtimestamp(t0 + hours * 3600, timezone.utc):%H:%M}Z".upper(),
        "start_hour": start.hour + start.minute / 60, "hours": hours, "t0_unix": t0,
        "atmosphere": atmosphere, "flights": flights, "space_events": SPACE_EVENTS,
        "observations": None,
        "provenance": {
            "tracks": {"source": "OpenSky Network REST API (anonymous)", "fetched_at": raw_tracks["fetched_at"],
                       "aircraft_seen": raw_tracks["states_seen"], "cruising": raw_tracks["cruising"],
                       "tracks_used": len(flights), "type_known": sum(f["type_known"] for f in flights)},
            "forecast": {"source": "Open-Meteo (ECMWF IFS 0.25°, NOAA GFS)", "levels_hpa": list(LEVELS_HPA),
                         "grid_deg": atmosphere["dlon"], "primary": PRIMARY},
            "satellite": {"status": "not_connected",
                          "reason": "Contrails.org GOES detections need an API key (CONTRAILS_ORG_KEY); none was set for this build."},
        },
        "validation": {
            "cruise_points": total_pts, "agreement": agree_pts / total_pts if total_pts else None,
            # Of the points where either forecast predicts a persistent contrail, the share where both do.
            "contrail_points_either": pts_either, "contrail_points_both": pts_both,
            "contrail_overlap": pts_both / pts_either if pts_either else None,
            "flights": len(flights), "contrail_flights": with_contrail, "both_models": both, "either_model": either,
            "recommended": len(recs), "recommended_agree": sum(1 for f in recs if f["recommendation"]["agree"]),
            "net_mean": sum(f["recommendation"]["net_mean"] for f in recs),
            "net_range": [sum(f["recommendation"]["net_range"][0] for f in recs), sum(f["recommendation"]["net_range"][1] for f in recs)],
            "extraCO2": sum(f["recommendation"]["extraCO2"] for f in recs),
        },
    }


def attach_satellite(snapshot: dict, grids: dict, hours: float) -> None:
    """Match GOES detections to the flights when a Contrails.org key is configured."""
    from ..sources.contrails_org import ContrailsOrgClient
    from .observed import attribute_observations

    t0 = snapshot["t0_unix"]
    start = datetime.fromtimestamp(t0, timezone.utc)
    end = datetime.fromtimestamp(t0 + hours * 3600, timezone.utc)
    client = ContrailsOrgClient(settings.contrails_org_key, settings.contrails_org_url)
    dets = client.segments_between(start, end, settings.bbox, step_min=settings.obs_step_min)
    g = grids[PRIMARY]
    import numpy as np
    wind = GridWind(g.lons, g.lats, (g.times - t0) / 3600, np.transpose(g.u250, (2, 1, 0)), np.transpose(g.v250, (2, 1, 0)))
    tracks = {f["id"]: [tuple(p) for p in f["pts"]] for f in snapshot["flights"]}
    obs = [(d.id, (d.observed_at - start).total_seconds() / 3600, d.line) for d in dets]
    matches = attribute_observations(obs, tracks, wind)
    for f in snapshot["flights"]:
        f["attribution"] = matches.get(f["id"])
    snapshot["observations"] = len(dets)
    snapshot["provenance"]["satellite"] = {"status": "connected", "detections": len(dets), "matched_flights": len(matches)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hours", type=float, default=10.0)
    ap.add_argument("--max-flights", type=int, default=90)
    ap.add_argument("--grid", type=float, default=2.0, help="forecast grid spacing in degrees")
    ap.add_argument("--fresh", action="store_true", help="ignore cached downloads")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.fresh and CACHE.exists():
        for p in CACHE.glob("*.json"):
            p.unlink()
    now = int(time.time())
    raw = _cached("tracks.json", lambda: fetch_tracks(settings.bbox, args.max_flights, now))
    now = raw["fetched_at"]
    grids = fetch_grid(settings.bbox, args.grid, cache_dir=CACHE)
    db = AircraftDatabase(settings.opensky_aircraft_db)
    snap = build(raw, grids, db, args.hours, now)
    if settings.contrails_org_key:
        attach_satellite(snap, grids, args.hours)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, separators=(",", ":")))
    v = snap["validation"]
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB): {v['flights']} flights, {v['recommended']} recommendations, "
          f"forecast agreement {v['agreement']:.0%}" if v["agreement"] is not None else f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
