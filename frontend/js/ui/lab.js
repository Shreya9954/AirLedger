// Stretch goal: cloud vs. contrail. Draws ash false-colour patches, then measures them from the
// pixels with the same method as backend/ml/shape_features.py (thin-ice mask -> largest region ->
// principal axes) and applies the same shape + track rule. A trained model would replace the rule.
import { rng } from '../util.js';

const S = 220;
const KM_PER_PX = 20 / 44; // the 20 km scale bar is 44 px long
const MIN_REGION_PX = 30;
const TRUTH = { fresh: 'Contrail', aged: 'Aged contrail', cirrus: 'Natural cirrus', mixed: 'Contrail over cirrus' };

export function classify(f) {
  if (f.lin == null) return 'No ice cloud found';
  const straight = f.lin > 0.7, matched = f.track != null && f.track < 10;
  if (straight && matched) return f.kind === 'mixed' ? 'Contrail over cirrus' : 'Contrail, attributed';
  if (straight) return 'Contrail, unattributed';
  return 'Natural cirrus';
}

function makePatch(kind, r) {
  const c = document.createElement('canvas'); c.width = S; c.height = S;
  const g = c.getContext('2d');
  // Ash false colour: clear ocean is mauve, low cloud ochre, thin ice cloud dark blue.
  // These are fixed imagery colours, so they do not follow the page theme.
  g.fillStyle = '#B98AA1'; g.fillRect(0, 0, S, S);
  for (let i = 0; i < 900; i++) { g.fillStyle = r() < 0.5 ? 'rgba(160,110,140,.35)' : 'rgba(205,160,170,.3)'; g.fillRect(r() * S, r() * S, 4 + r() * 8, 4 + r() * 8); }
  for (let i = 0; i < 4; i++) { g.fillStyle = 'rgba(196,150,90,.35)'; g.beginPath(); g.ellipse(r() * S, r() * S, 20 + r() * 30, 12 + r() * 20, r() * 3, 0, 6.28); g.fill(); }

  const cirrus = () => {
    let x = r() * S, y = r() * S, a = r() * 6.28;
    for (let i = 0; i < 70; i++) {
      a += (r() - 0.5) * 0.5; x += Math.cos(a) * 3; y += Math.sin(a) * 3;
      g.fillStyle = 'rgba(30,38,90,.10)'; g.beginPath(); g.ellipse(x, y, 10 + r() * 14, 5 + r() * 8, a, 0, 6.28); g.fill();
    }
  };
  const line = aged => {
    const a = r() * 3.14, cx = S * (0.3 + r() * 0.4), cy = S * (0.3 + r() * 0.4), L = S * 0.8;
    const x0 = cx - Math.cos(a) * L / 2, y0 = cy - Math.sin(a) * L / 2, x1 = cx + Math.cos(a) * L / 2, y1 = cy + Math.sin(a) * L / 2;
    g.strokeStyle = aged ? 'rgba(30,38,95,.45)' : 'rgba(22,28,80,.85)'; g.lineWidth = aged ? 7 : 2; g.lineCap = 'round';
    g.beginPath(); g.moveTo(x0, y0);
    const bend = aged ? 26 : 0;
    g.quadraticCurveTo(cx + bend * Math.sin(a) * (r() > 0.5 ? 1 : -1), cy - bend * Math.cos(a), x1, y1); g.stroke();
    return { a, x0, y0, x1, y1 };
  };

  // Draw the scene. Only the advected flight track's true offset is chosen here; every feature
  // shown under the tile is measured from the pixels below.
  let l = null, trackKm = null;
  if (kind === 'cirrus') { cirrus(); cirrus(); }
  if (kind === 'fresh') { l = line(false); trackKm = 1 + r() * 6; }
  if (kind === 'aged') { l = line(true); trackKm = 9 + r() * 10; }
  if (kind === 'mixed') { cirrus(); l = line(false); trackKm = 2 + r() * 5; }
  const feat = measure(g.getImageData(0, 0, S, S).data);
  feat.kind = kind;

  let track = null;
  if (l) { // advected flight track, drawn offset from the contrail
    const o = trackKm / KM_PER_PX, nx = -Math.sin(l.a) * o, ny = Math.cos(l.a) * o;
    track = [l.x0 + nx, l.y0 + ny, l.x1 + nx, l.y1 + ny];
    g.strokeStyle = 'rgba(255,255,255,.9)'; g.lineWidth = 1; g.setLineDash([5, 4]);
    g.beginPath(); g.moveTo(track[0], track[1]); g.lineTo(track[2], track[3]); g.stroke(); g.setLineDash([]);
  }
  feat.track = track && feat.c ? distToLine(feat.c, track) * KM_PER_PX : null;
  if (feat.track != null && feat.track > 20) feat.track = null;
  g.fillStyle = 'rgba(255,255,255,.9)'; g.fillRect(10, S - 14, 44, 3);
  g.font = '10px Menlo, monospace'; g.fillText('20 km', 10, S - 18);
  return { c, feat };
}

export function initLab(box, button) {
  const r = rng(77);
  function render() {
    box.innerHTML = '';
    const kinds = ['fresh', 'cirrus', 'aged', 'mixed'].sort(() => r() - 0.5);
    for (const k of kinds) {
      const { c, feat } = makePatch(k, r), verdict = classify(feat);
      const correct = (k === 'cirrus') === (verdict === 'Natural cirrus');
      const tile = document.createElement('div'); tile.className = 'tile';
      c.setAttribute('role', 'img'); c.setAttribute('aria-label', 'Simulated satellite patch: ' + TRUTH[k]);
      tile.appendChild(c);
      const m = document.createElement('div'); m.className = 'meta';
      m.innerHTML = `<span class="lbl">Rule says</span><span class="verdict">${verdict}</span>
        <span class="mono">${feat.lin == null ? 'no region of thin ice cloud' : `linearity ${feat.lin.toFixed(2)} · width ${feat.w.toFixed(1)} km`}</span>
        <span class="mono">${feat.track != null ? 'track offset ' + feat.track.toFixed(1) + ' km' : 'no track within 20 km'}</span>
        <span class="${correct ? 'ok' : 'miss'}" style="font-size:.8rem">Label: ${TRUTH[k]} · ${correct ? 'correct' : 'missed'}</span>`;
      tile.appendChild(m); box.appendChild(tile);
    }
  }
  button.addEventListener('click', render);
  render();
}

// Thin ice cloud in ash false colour is dark blue: blue clearly above red.
const isIce = (d, i) => d[i + 2] - d[i] > 8;

function distToLine([px, py], [x0, y0, x1, y1]) {
  const dx = x1 - x0, dy = y1 - y0;
  return Math.abs(dy * (px - x0) - dx * (py - y0)) / Math.hypot(dx, dy);
}

// Largest 8-connected region of thin-ice pixels, then shape_features(): linearity from the
// principal axes of its pixel cloud, length ≈ 4·major axis, width = area / length.
function measure(data) {
  const seen = new Uint8Array(S * S), stack = new Int32Array(S * S);
  let biggest = null;
  for (let start = 0; start < S * S; start++) {
    if (seen[start] || !isIce(data, start * 4)) continue;
    const px = [];
    let top = 0; stack[top++] = start; seen[start] = 1;
    while (top) {
      const p = stack[--top], x = p % S, y = (p / S) | 0;
      px.push(p);
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const nx = x + dx, ny = y + dy, q = ny * S + nx;
        if (nx < 0 || ny < 0 || nx >= S || ny >= S || seen[q] || !isIce(data, q * 4)) continue;
        seen[q] = 1; stack[top++] = q;
      }
    }
    if (!biggest || px.length > biggest.length) biggest = px;
  }
  if (!biggest || biggest.length < MIN_REGION_PX) return { lin: null, w: 0, c: null };
  const n = biggest.length;
  let mx = 0, my = 0;
  for (const p of biggest) { mx += p % S; my += (p / S) | 0; }
  mx /= n; my /= n;
  let sxx = 0, syy = 0, sxy = 0;
  for (const p of biggest) { const dx = p % S - mx, dy = ((p / S) | 0) - my; sxx += dx * dx; syy += dy * dy; sxy += dx * dy; }
  sxx /= n - 1; syy /= n - 1; sxy /= n - 1;
  const tr = sxx + syy, det = sxx * syy - sxy * sxy, disc = Math.sqrt(Math.max(0, tr * tr / 4 - det));
  const major = Math.sqrt(Math.max(0, tr / 2 + disc)), minor = Math.sqrt(Math.max(0, tr / 2 - disc));
  const lin = major > 0 ? 1 - minor / major : 0;
  const length = 4 * major * KM_PER_PX;
  return { lin, w: n * KM_PER_PX * KM_PER_PX / Math.max(length, KM_PER_PX), c: [mx, my] };
}
