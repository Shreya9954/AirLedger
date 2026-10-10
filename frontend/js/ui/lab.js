// Stretch goal: cloud vs. contrail. Generates ash false-colour patches and applies the same
// shape + track rule as backend/ml/shape_features.py. The real model replaces this.
import { rng } from '../util.js';

const S = 220;
const TRUTH = { fresh: 'Contrail', aged: 'Aged contrail', cirrus: 'Natural cirrus', mixed: 'Contrail over cirrus' };

export function classify(f) {
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

  const feat = { kind };
  if (kind === 'cirrus') { cirrus(); cirrus(); feat.lin = 0.22 + r() * 0.3; feat.w = 18 + r() * 20; feat.track = null; }
  if (kind === 'fresh') { feat.l = line(false); feat.lin = 0.9 + r() * 0.08; feat.w = 1 + r() * 2; feat.track = 1 + r() * 6; }
  if (kind === 'aged') { feat.l = line(true); feat.lin = 0.55 + r() * 0.2; feat.w = 6 + r() * 5; feat.track = 9 + r() * 10; }
  if (kind === 'mixed') { cirrus(); feat.l = line(false); feat.lin = 0.82 + r() * 0.1; feat.w = 1.5 + r() * 2; feat.track = 2 + r() * 5; }

  if (feat.l) { // advected flight track, drawn offset from the contrail
    const o = feat.track * 1.4, nx = -Math.sin(feat.l.a) * o, ny = Math.cos(feat.l.a) * o;
    g.strokeStyle = 'rgba(255,255,255,.9)'; g.lineWidth = 1; g.setLineDash([5, 4]);
    g.beginPath(); g.moveTo(feat.l.x0 + nx, feat.l.y0 + ny); g.lineTo(feat.l.x1 + nx, feat.l.y1 + ny); g.stroke(); g.setLineDash([]);
  }
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
      m.innerHTML = `<span class="lbl">Model says</span><span class="verdict">${verdict}</span>
        <span class="mono">linearity ${feat.lin.toFixed(2)} · width ${feat.w.toFixed(1)} km</span>
        <span class="mono">${feat.track != null ? 'track offset ' + feat.track.toFixed(1) + ' km' : 'no track within 20 km'}</span>
        <span class="${correct ? 'ok' : 'miss'}" style="font-size:.8rem">Label: ${TRUTH[k]} · ${correct ? 'correct' : 'missed'}</span>`;
      tile.appendChild(m); box.appendChild(tile);
    }
  }
  button.addEventListener('click', render);
  render();
}
