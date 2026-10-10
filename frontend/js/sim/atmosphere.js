// Simulated ERA5-like humidity field: relative humidity over ice built from drifting Gaussian blobs.
// Values above 1.0 are ice-supersaturated regions (ISSR), where contrails persist.
import { rng } from '../util.js';

export function simAtmosphere(seed = 1717) {
  const R = rng(seed), rr = (a, b) => a + (b - a) * R();
  const wind = 1.2; // degrees longitude per hour, eastward
  const blobs = [];
  for (let i = 0; i < 17; i++) {
    blobs.push({ lon: rr(-72, -14), lat: rr(40, 62), fl: rr(305, 400), sig: rr(18, 30), rx: rr(4, 10), ry: rr(2.5, 5.5), s: rr(0.5, 0.82), ph: rr(0, 6.28) });
  }
  function rhi(lon, lat, fl, t) {
    let v = 0.62;
    for (const b of blobs) {
      const dz = (fl - b.fl) / b.sig; if (dz > 3 || dz < -3) continue;
      const dx = (lon - b.lon - wind * t) / b.rx, dy = (lat - b.lat) / b.ry;
      const d = dx * dx + dy * dy; if (d > 9) continue;
      v += b.s * (0.75 + 0.25 * Math.sin(t * 0.45 + b.ph)) * Math.exp(-d - dz * dz);
    }
    return v;
  }
  return { wind, rhi };
}
