// Match satellite-detected contrails to the flights that made them. Mirrors
// backend/app/pipeline/attribution.py and observed.py: move each candidate flight's recent track
// downwind by its age, then pick the flight whose moved track lies closest to the detected line.
import { N, C0, C1 } from './config.js';
import { rng, D2R } from './util.js';

const MAX_KM = 20, SCALE_KM = 10, MAX_AGE_H = 3, NEAR_DEG = 8;

// wind(lon, lat, tHours) -> [u, v] in m/s
export function advect(track, atH, wind) {
  const out = [];
  for (const [lon, lat, t] of track) {
    const ageS = (atH - t) * 3600;
    if (ageS < 0) continue;
    const [u, v] = wind(lon, lat, t);
    out.push([lon + u * ageS / (111320 * Math.cos(lat * D2R)), lat + v * ageS / 111320]);
  }
  return out;
}

function pointSegmentKm(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy;
  const t = L2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2)) : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

export function meanOffsetKm(line, track) {
  if (track.length < 2 || !line.length) return Infinity;
  const c = Math.cos(line[0][1] * D2R), k = 111.32;
  const loc = pts => pts.map(([lon, lat]) => [lon * k * c, lat * k]);
  const L = loc(line), T = loc(track);
  let sum = 0;
  for (const p of L) {
    let m = Infinity;
    for (let i = 0; i < T.length - 1; i++) m = Math.min(m, pointSegmentKm(p, T[i], T[i + 1]));
    sum += m;
  }
  return sum / L.length;
}

function near(track, line) {
  const lons = line.map(p => p[0]), lats = line.map(p => p[1]);
  const lo0 = Math.min(...lons) - NEAR_DEG, lo1 = Math.max(...lons) + NEAR_DEG;
  const la0 = Math.min(...lats) - NEAR_DEG / 2, la1 = Math.max(...lats) + NEAR_DEG / 2;
  return track.some(([lon, lat]) => lon >= lo0 && lon <= lo1 && lat >= la0 && lat <= la1);
}

// detections: [{ id, t, line }]. Returns Map flightId -> best match, and how each detection was matched.
export function attributeDetections(detections, flights, wind) {
  const best = new Map(), assigned = new Map();
  for (const det of detections) {
    let bestF = null, bestD = Infinity, bestPts = null;
    for (const f of flights) {
      const pts = f.pts.filter(p => det.t - p[2] >= 0 && det.t - p[2] <= MAX_AGE_H);
      if (pts.length < 2 || !near(pts, det.line)) continue;
      const d = meanOffsetKm(det.line, advect(pts, det.t, wind));
      if (d < bestD) { bestD = d; bestF = f; bestPts = pts; }
    }
    if (!bestF || bestD > MAX_KM) continue;
    assigned.set(det.id, bestF.id);
    const mid = det.line[det.line.length >> 1], moved = advect(bestPts, det.t, wind);
    let k = 0;
    moved.forEach((p, i) => { if ((p[0] - mid[0]) ** 2 + (p[1] - mid[1]) ** 2 < (moved[k][0] - mid[0]) ** 2 + (moved[k][1] - mid[1]) ** 2) k = i; });
    const m = { id: det.id, offset_km: bestD, confidence: Math.exp(-bestD / SCALE_KM), age_min: Math.round(60 * (det.t - bestPts[k][2])),
      observed_h: det.t, n_matched: (best.get(bestF.id)?.n_matched ?? 0) + 1, simulated: !!det.simulated };
    const prev = best.get(bestF.id);
    if (!prev || m.confidence > prev.confidence) best.set(bestF.id, m); else prev.n_matched = m.n_matched;
  }
  return { best, assigned };
}

// Simulated feed only: hourly "satellite detections" of the contrails the model predicts, as a
// geostationary detector would see them: 15 min to 2 h old, drifted with the wind, shifted by a few
// km of position error, ends trimmed, and some missed. `source` is kept only to score the matcher.
export function simDetections(flights, atmos, hours, seed = 4242) {
  const R = rng(seed), out = [];
  for (let t = 1; t <= hours; t += 1) {
    for (const f of flights) {
      let run = [];
      const flush = () => {
        if (run.length >= 6 && R() < 0.75) {
          const cut = Math.floor(run.length * 0.15 * R());
          const kept = run.slice(cut, run.length - Math.floor(run.length * 0.15 * R()));
          const shift = (R() - 0.5) * 2 * 6 / 111.32; // up to ±6 km north-south
          const line = kept.map(p => [p[0] + atmos.wind * (t - p[2]) + (R() - 0.5) * 0.02, p[1] + shift + (R() - 0.5) * 0.01]);
          out.push({ id: `SIM-${String(t).padStart(2, '0')}-${out.length}`, t, line, source: f.id, simulated: true });
        }
        run = [];
      };
      for (let i = C0; i < C1 && i < N; i++) {
        const age = t - f.pts[i][2];
        if (f.base.iss[i] && age >= 0.25 && age <= 2) run.push(f.pts[i]); else flush();
      }
      flush();
    }
  }
  return out;
}
