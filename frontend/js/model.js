// Contrail model used by the simulated feed. In live mode the backend runs pycontrails CoCiP
// and sends `base` and `opts` precomputed in the same shape, so the UI never calls these.
import { AGWP_CO2, CO2_PER_FUEL, N, C0, C1, DELTAS, MIN_FL, TYPES } from './config.js';
import { clamp } from './util.js';

// Energy forcing per km of persistent contrail (J). Night contrails only trap heat;
// midday contrails can net-cool by reflecting sunlight.
export function efPerKm(lon, t, rhi, type, startHour) {
  const h = ((startHour + t + lon / 15) % 24 + 24) % 24;
  const night = h < 6 || h >= 18;
  const base = night ? 1.6e11 : (h >= 10 && h < 15 ? -0.3e11 : 0.45e11);
  return base * clamp(0.6 + (rhi - 1) * 4, 0.6, 1.6) * (TYPES[type]?.f ?? 1);
}

// Walk the cruise waypoints at the flight level given by flAt(i) and total up contrail km and EF.
export function evalTrack(atmos, f, flAt, startHour) {
  let km = 0, ef = 0;
  const iss = new Uint8Array(N);
  for (let i = C0; i < C1; i++) {
    const p = f.pts[i], r = atmos.rhi(p[0], p[1], flAt(i), p[2]);
    if (r > 1) { iss[i] = 1; km += f.seg[i]; ef += f.seg[i] * efPerKm(p[0], p[2], r, f.type, startHour); }
  }
  return { iss, km, ef };
}

// Fuel penalty of flying off the optimum level over part of the route.
export function extraFuelT(delta, fuelT, windowKm, distKm) {
  if (!delta) return 0;
  const pct = delta < 0 ? 0.011 * (-delta / 20) : 0.007 * (delta / 20);
  return fuelT * (windowKm / distKm) * pct + 0.04; // + level-change cost
}

// Altitude options applied over the humid stretch plus 100 km either side.
export function rerouteOptions(atmos, f, startHour) {
  const out = {};
  let first = -1, last = -1;
  for (let i = C0; i < C1; i++) if (f.base.iss[i]) { if (first < 0) first = i; last = i; }
  const pad = Math.ceil(100 / (f.dist / N));
  const w0 = first < 0 ? -1 : Math.max(C0, first - pad), w1 = first < 0 ? -2 : Math.min(C1, last + pad);
  let wkm = 0;
  for (let i = Math.max(0, w0); i <= w1 && i < N; i++) wkm += f.seg[i];
  for (const d of DELTAS) {
    const nf = f.fl + d;
    if (nf > (TYPES[f.type]?.ceil ?? 410) || nf < MIN_FL) { out[d] = null; continue; }
    if (d === 0 || first < 0) { out[d] = { d, fl: nf, km: f.base.km, ef: f.base.ef, avoided: 0, extraCO2: 0, net: 0 }; continue; }
    const r = evalTrack(atmos, f, i => (i >= w0 && i <= w1 ? nf : f.fl), startHour);
    const extraCO2 = extraFuelT(d, f.fuel, wkm, f.dist) * CO2_PER_FUEL;
    const avoided = (f.base.ef - r.ef) / AGWP_CO2;
    out[d] = { d, fl: nf, km: r.km, ef: r.ef, avoided, extraCO2, net: avoided - extraCO2 };
  }
  let best = out[0];
  for (const d of DELTAS) if (out[d] && out[d].net > best.net) best = out[d];
  out.best = best; out.wkm = wkm;
  return out;
}

// Interpolated position at time t, or null if not airborne. i is the waypoint index just behind.
export function flightPos(f, t) {
  const t0 = f.pts[0][2], t1 = f.pts[N - 1][2];
  if (t < t0 || t > t1) return null;
  const u = (t - t0) / (t1 - t0) * (N - 1), i = Math.min(N - 2, Math.floor(u)), k = u - i;
  const a = f.pts[i], b = f.pts[i + 1];
  return { lon: a[0] + (b[0] - a[0]) * k, lat: a[1] + (b[1] - a[1]) * k, i };
}

export const inIssrAt = (f, p) => !!p && p.i >= C0 && p.i < C1 && !!f.base.iss[p.i];
