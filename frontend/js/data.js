// Loads the scenario the UI renders. Asks the backend first; if it is unreachable or running in
// demo mode, builds the simulated night locally so the page always works on its own.
import { simAtmosphere } from './sim/atmosphere.js';
import { simFleet } from './sim/fleet.js';
import { SPACE_EVENTS } from './sim/space.js';
import { attributeDetections, simDetections } from './attribution.js';
import { D2R } from './util.js';

const API = '/api';

async function getJSON(path, ms = 2500) {
  const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), ms);
  try {
    const res = await fetch(API + path, { signal: ctl.signal });
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
    return await res.json();
  } finally { clearTimeout(timer); }
}

// Backend humidity grid -> the same rhi(lon, lat, fl, t) interface as the simulation.
// values are flattened [time][level][lat][lon]; bilinear in space, nearest in level and time.
export function gridAtmosphere(g) {
  const { lon0, dlon, nlon, lat0, dlat, nlat, levels, t0, dt, nt, values, wind } = g;
  const nearest = (arr, v) => arr.reduce((bi, x, i) => (Math.abs(x - v) < Math.abs(arr[bi] - v) ? i : bi), 0);
  function rhi(lon, lat, fl, t) {
    const k = nearest(levels, fl), ti = Math.max(0, Math.min(nt - 1, Math.round((t - t0) / dt)));
    const x = (lon - lon0) / dlon, y = (lat - lat0) / dlat;
    if (x < 0 || y < 0 || x > nlon - 1 || y > nlat - 1) return 0;
    const x0 = Math.min(nlon - 2, Math.floor(x)), y0 = Math.min(nlat - 2, Math.floor(y)), fx = x - x0, fy = y - y0;
    const base = (ti * levels.length + k) * nlat * nlon, at = (yy, xx) => values[base + yy * nlon + xx];
    return (at(y0, x0) * (1 - fx) + at(y0, x0 + 1) * fx) * (1 - fy) + (at(y0 + 1, x0) * (1 - fx) + at(y0 + 1, x0 + 1) * fx) * fy;
  }
  return { wind: wind ?? 1.2, rhi };
}

export async function loadScenario() {
  try {
    const health = await getJSON('/health', 1500);
    if (health.mode === 'live') {
      const sc = await getJSON('/scenario', 120000);
      return {
        source: 'live', label: sc.label, startHour: sc.start_hour, hours: sc.hours,
        atmos: gridAtmosphere(sc.atmosphere), flights: sc.flights, space: sc.space_events,
        detections: sc.observations == null ? null : { total: sc.observations, matchedFlights: sc.flights.filter(f => f.attribution).length }
      };
    }
  } catch (err) {
    console.info('Backend unavailable, using simulated feed:', err.message);
  }
  const startHour = 21, hours = 12, atmos = simAtmosphere(), flights = simFleet(atmos, startHour);
  return {
    source: 'demo', label: 'N. ATLANTIC · 10–11 OCT 2026', startHour, hours,
    atmos, flights, space: SPACE_EVENTS, detections: simulatedAttribution(flights, atmos, hours)
  };
}

// Run the attribution matcher on simulated detections and report how often it picked the flight
// that actually made each one (the matcher never sees that answer).
function simulatedAttribution(flights, atmos, hours) {
  const dets = simDetections(flights, atmos, hours);
  const wind = (lon, lat) => [atmos.wind * 111320 * Math.cos(lat * D2R) / 3600, 0];
  const { best, assigned } = attributeDetections(dets, flights, wind);
  for (const f of flights) f.attribution = best.get(f.id) ?? null;
  const correct = dets.filter(d => assigned.get(d.id) === d.source).length;
  return { total: dets.length, matched: assigned.size, correct, matchedFlights: best.size };
}
