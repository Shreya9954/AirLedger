export const D2R = Math.PI / 180;
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// Seeded PRNG (mulberry32) so the simulated night is the same on every load.
export function rng(seed) {
  return () => {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

// Great-circle distance in km between [lon, lat] points.
export function hav(a, b) {
  const dLat = (b[1] - a[1]) * D2R, dLon = (b[0] - a[0]) * D2R;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * D2R) * Math.cos(b[1] * D2R) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

// Point at fraction f along the great circle from a to b.
export function gc(a, b, f) {
  const toV = p => [Math.cos(p[1] * D2R) * Math.cos(p[0] * D2R), Math.cos(p[1] * D2R) * Math.sin(p[0] * D2R), Math.sin(p[1] * D2R)];
  const A = toV(a), B = toV(b);
  const dot = clamp(A[0] * B[0] + A[1] * B[1] + A[2] * B[2], -1, 1), om = Math.acos(dot);
  const s = Math.sin(om), k1 = Math.sin((1 - f) * om) / s, k2 = Math.sin(f * om) / s;
  const x = k1 * A[0] + k2 * B[0], y = k1 * A[1] + k2 * B[1], z = k1 * A[2] + k2 * B[2];
  return [Math.atan2(y, x) / D2R, Math.atan2(z, Math.hypot(x, y)) / D2R];
}

export const fmt = (n, d = 0) => n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

const SUP = { '-': '⁻', 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹' };
export function sci(n) {
  if (!n) return '0 J';
  const e = Math.floor(Math.log10(Math.abs(n))), m = n / 10 ** e;
  return m.toFixed(1) + ' × 10' + String(e).split('').map(c => SUP[c]).join('') + ' J';
}

// Scenario time t is hours after startHour (UTC).
export function hhmm(t, startHour) {
  const m = ((Math.round((startHour + t) * 60) % 1440) + 1440) % 1440;
  return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0') + 'Z';
}

export const median = a => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
