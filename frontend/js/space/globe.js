// The globe: catalogued objects in low orbit, the ones about to fall highlighted, and recent launch sites.
// Drawn on a 2D canvas in an orthographic projection, in the same chart style as the contrail map, so it needs
// no WebGL and no network: orbits are propagated in the browser from CelesTrak OMM elements with a local copy
// of satellite.js (json2satrec reads OMM directly, so 6-digit catalogue numbers work).
import * as sat from './vendor/satellite.es.js';
import { el, num, valued, showTip, hideTip } from './format.js';
import { onThemeChange } from '../ui/theme.js';

const RE = 6371, MAX_ALT = 1500, SPEED = 60, KEY_S = 60, D2R = Math.PI / 180;
const TOKENS = ['paper', 'sea', 'land', 'ink', 'ink-2', 'rule', 'magenta', 'ice', 'orbit', 'sp-launch'];

export async function renderGlobe(root, orbitsDoc, summary) {
  const land = await fetch(new URL('./land-110m.json', import.meta.url)).then(r => r.json()).then(j => j.rings).catch(() => []);
  const falling = new Map(summary.falling.map(f => [f.norad, f]));

  // satellites
  const objs = [];
  let skipped = 0;
  for (const o of orbitsDoc.objects) {
    try {
      const rec = sat.json2satrec(o);
      if (rec.error) { skipped++; continue; }
      objs.push({ rec, name: o.OBJECT_NAME, norad: +o.NORAD_CAT_ID, group: o.group, cospar: o.OBJECT_ID });
    } catch { skipped++; }
  }
  const n = objs.length;
  const pos0 = new Float32Array(3 * n), pos1 = new Float32Array(3 * n), alt = new Float32Array(n), ok = new Uint8Array(n);

  // launch sites: one marker per pad, with how many launches it hosted in the window
  const pads = new Map();
  for (const L of summary.launches) {
    const p = L.pad;
    if (p?.lat == null || p?.lon == null) continue;
    const k = `${p.lat.toFixed(3)},${p.lon.toFixed(3)}`;
    const e = pads.get(k) ?? pads.set(k, { lat: p.lat, lon: p.lon, name: p.name, loc: p.location, flown: 0, upcoming: 0 }).get(k);
    L.status === 'upcoming' ? e.upcoming++ : e.flown++;
  }
  const padList = [...pads.values()];

  // time: start now if the elements are fresh, otherwise at the time they were fetched
  const gen = Date.parse(orbitsDoc.generated_at);
  const t0 = Math.abs(Date.now() - gen) < 3 * 86400e3 ? Date.now() : gen;
  let simT = t0, keyT = NaN;

  function propagateTo(t, out) {
    const d = new Date(t), g = sat.gstime(d);
    for (let i = 0; i < n; i++) {
      let pv;
      try { pv = sat.propagate(objs[i].rec, d); } catch { pv = null; }
      const p = pv && pv.position;
      if (!p || typeof p !== 'object' || !isFinite(p.x)) { ok[i] = 0; continue; }
      const geo = sat.eciToGeodetic(p, g);
      const r = RE + geo.height, cl = Math.cos(geo.latitude);
      out[3 * i] = r * cl * Math.cos(geo.longitude);
      out[3 * i + 1] = r * cl * Math.sin(geo.longitude);
      out[3 * i + 2] = r * Math.sin(geo.latitude);
      alt[i] = geo.height;
      ok[i] = geo.height > 80 ? 1 : 0;
    }
  }
  function keyframe(t) {
    keyT = Math.floor(t / (KEY_S * 1000)) * KEY_S * 1000;
    propagateTo(keyT, pos0);
    const keep = ok.slice();
    propagateTo(keyT + KEY_S * 1000, pos1);
    for (let i = 0; i < n; i++) ok[i] &= keep[i];
  }

  // ---------------------------------------------------------------- DOM
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let playing = !reduce;
  const show = { active: true, station: true, falling: true, pads: true };
  const playBtn = el('button', { class: 'btn', type: 'button' }, playing ? 'Pause' : 'Play');
  const clock = el('span', { class: 'clock sp-clock' });
  const toggles = el('div', { class: 'toggles' }, ...[
    ['active', 'Satellites (sample)'], ['station', 'Stations'], ['falling', 'Falling'], ['pads', 'Launch sites']
  ].map(([k, t]) => el('label', {}, el('input', { type: 'checkbox', checked: true, onchange: e => { show[k] = e.target.checked; draw(); } }), ' ', t)));
  const canvas = el('canvas', { class: 'sp-globe', tabindex: '0', role: 'img',
    'aria-label': 'Globe of objects in low orbit. Drag or use the arrow keys to turn it. Falling objects are listed beside it.' });
  const wrap = el('div', { class: 'sp-globe-wrap' }, canvas);
  const high = objs.length ? countHigh() : 0;
  const legend = el('div', { class: 'legend sp-globe-legend' },
    el('span', {}, el('i', { class: 'sw sp-sw-dot sp-sw-active' }), 'Active satellite (sample of the catalogue)'),
    el('span', {}, el('i', { class: 'sw sp-sw-dot sp-sw-station' }), 'Space station'),
    el('span', {}, el('i', { class: 'sw sp-sw-dot sp-sw-falling' }), 'Falling: on CelesTrak’s decaying list'),
    el('span', {}, el('i', { class: 'sw sp-sw-tri' }), 'Launch site used in the window'));
  const list = fallingList(summary, objs, focusOn);
  root.replaceChildren(
    el('div', { class: 'bar sp-globe-bar' }, playBtn, clock, toggles),
    el('div', { class: 'sp-globe-grid' }, el('div', {}, wrap, legend,
      el('p', { class: 'note' }, `${num(n - high)} objects up to ${num(MAX_ALT)} km drawn at their real height` +
        (high ? `; ${num(high)} in higher orbits, such as GPS and geostationary satellites, are left off.` : '.') +
        ` Positions are propagated in your browser from CelesTrak elements fetched ${orbitsDoc.generated_at.slice(0, 16).replace('T', ' ')} UTC; while playing, time runs ${SPEED} times faster than real time.`)), list));

  function countHigh() {
    propagateTo(t0, pos0);
    let c = 0;
    for (let i = 0; i < n; i++) if (ok[i] && alt[i] > MAX_ALT) c++;
    return c;
  }

  // ---------------------------------------------------------------- projection and drawing
  const C = {};
  const readColours = () => { const cs = getComputedStyle(document.documentElement); for (const k of TOKENS) C[k] = cs.getPropertyValue('--' + k).trim(); };
  readColours();
  onThemeChange(() => { readColours(); draw(); });

  let view = { lon: -40, lat: 22 }, size = 0, dpr = 1, k = 1, cx = 0, cy = 0;
  const ctx = canvas.getContext('2d');
  const drawn = { x: new Float32Array(n), y: new Float32Array(n), vis: new Uint8Array(n) };
  let hover = -1, selected = -1;

  function resize() {
    const w = Math.round(wrap.clientWidth);
    if (!w || w === size) return;
    size = w; dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = size * dpr; canvas.height = size * dpr;
    canvas.style.width = canvas.style.height = size + 'px';
    draw();
  }
  new ResizeObserver(resize).observe(wrap);

  function project(x, y, z) {   // ECEF (km) -> screen; returns [sx, sy, depth]
    const lo = view.lon * D2R, la = view.lat * D2R;
    const x1 = x * Math.cos(lo) + y * Math.sin(lo), y1 = -x * Math.sin(lo) + y * Math.cos(lo);
    const sx = y1, sy = -Math.sin(la) * x1 + Math.cos(la) * z, d = Math.cos(la) * x1 + Math.sin(la) * z;
    return [cx + sx * k, cy - sy * k, d, sx, sy];
  }
  const ll = (lat, lon, r = RE) => { const a = lat * D2R, b = lon * D2R; return [r * Math.cos(a) * Math.cos(b), r * Math.cos(a) * Math.sin(b), r * Math.sin(a)]; };
  const landXYZ = land.map(ring => ring.map(([lon, lat]) => ll(lat, lon)));

  function draw() {
    if (!size) return;
    const S = size;
    cx = S / 2; cy = S / 2; k = (S / 2 - 6) / (RE + MAX_ALT);
    const R = RE * k;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, S, S);
    // ocean disk
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, 2 * Math.PI); ctx.fillStyle = C.sea; ctx.fill();
    // land: points behind the horizon are pushed onto the limb so fills stay on the disk
    ctx.fillStyle = C.land; ctx.strokeStyle = C['ink-2']; ctx.lineWidth = 0.7;
    for (const ring of landXYZ) {
      ctx.beginPath();
      let front = false;
      ring.forEach(([x, y, z], i) => {
        let [px, py, d, sx, sy] = project(x, y, z);
        if (d < 0) { const h = Math.hypot(sx, sy) || 1; px = cx + sx / h * R; py = cy - sy / h * R; } else front = true;
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      });
      if (front) ctx.fill();
    }
    for (const ring of landXYZ) {   // coastlines: front-side segments only
      ctx.beginPath();
      let pen = false;
      for (const [x, y, z] of ring) {
        const [px, py, d] = project(x, y, z);
        if (d >= 0) { pen ? ctx.lineTo(px, py) : ctx.moveTo(px, py); pen = true; } else pen = false;
      }
      ctx.globalAlpha = 0.55; ctx.stroke(); ctx.globalAlpha = 1;
    }
    // graticule every 30 degrees
    ctx.strokeStyle = C.rule; ctx.lineWidth = 0.5; ctx.globalAlpha = 0.6;
    for (let lon = -180; lon < 180; lon += 30) line(lat => ll(lat, lon), -90, 90);
    for (let lat = -60; lat <= 60; lat += 30) line(lon => ll(lat, lon), -180, 180);
    ctx.globalAlpha = 1;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, 2 * Math.PI); ctx.strokeStyle = C['ink-2']; ctx.lineWidth = 1; ctx.stroke();

    // launch sites
    if (show.pads) {
      ctx.fillStyle = C['sp-launch'];
      for (const p of padList) {
        const [px, py, d] = project(...ll(p.lat, p.lon));
        p.sx = px; p.sy = py; p.vis = d >= 0;
        if (!p.vis) continue;
        ctx.beginPath(); ctx.moveTo(px, py - 6); ctx.lineTo(px + 5, py + 3.5); ctx.lineTo(px - 5, py + 3.5); ctx.closePath();
        ctx.fill(); ctx.strokeStyle = C.paper; ctx.lineWidth = 1.5; ctx.stroke();
      }
    }

    // satellites: interpolate between the two keyframes
    const f = isNaN(keyT) ? 0 : Math.max(0, Math.min(1, (simT - keyT) / (KEY_S * 1000)));
    const order = ['active', 'station', 'falling'];
    for (const g of order) {
      if (!show[g]) continue;
      for (let i = 0; i < n; i++) {
        if (objs[i].group !== g) continue;
        drawn.vis[i] = 0;
        if (!ok[i] || alt[i] > MAX_ALT) continue;
        const x = pos0[3 * i] + (pos1[3 * i] - pos0[3 * i]) * f, y = pos0[3 * i + 1] + (pos1[3 * i + 1] - pos0[3 * i + 1]) * f,
          z = pos0[3 * i + 2] + (pos1[3 * i + 2] - pos0[3 * i + 2]) * f;
        const [px, py, d, sx, sy] = project(x, y, z);
        if (d < 0 && Math.hypot(sx, sy) < RE) continue;  // behind the Earth
        drawn.x[i] = px; drawn.y[i] = py; drawn.vis[i] = 1;
        if (g === 'active') {
          ctx.globalAlpha = d < 0 ? 0.25 : 0.55; ctx.fillStyle = C['ink-2']; ctx.fillRect(px - 0.9, py - 0.9, 1.8, 1.8);
        } else {
          ctx.globalAlpha = 1;
          ctx.beginPath(); ctx.arc(px, py, g === 'falling' ? 4 : 3.5, 0, 2 * Math.PI);
          ctx.fillStyle = g === 'falling' ? C.magenta : C.ice; ctx.fill();
          ctx.strokeStyle = C.paper; ctx.lineWidth = 2; ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
    }
    for (const i of [selected, hover]) {
      if (i < 0 || !drawn.vis[i]) continue;
      ctx.beginPath(); ctx.arc(drawn.x[i], drawn.y[i], 8, 0, 2 * Math.PI); ctx.strokeStyle = C.ink; ctx.lineWidth = 1.5; ctx.stroke();
    }
    if (selected >= 0 && drawn.vis[selected]) {
      ctx.font = '500 11px ' + getComputedStyle(document.body).getPropertyValue('--mono');
      ctx.fillStyle = C.ink; ctx.textAlign = drawn.x[selected] > S - 140 ? 'right' : 'left';
      ctx.fillText(objs[selected].name, drawn.x[selected] + (ctx.textAlign === 'right' ? -12 : 12), drawn.y[selected] - 8);
    }
    clock.textContent = new Date(simT).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' + (playing ? ` · ×${SPEED}` : '');
  }
  function line(at, a, b) {
    ctx.beginPath();
    let pen = false;
    for (let v = a; v <= b; v += 3) {
      const [px, py, d] = project(...at(v));
      if (d >= 0) { pen ? ctx.lineTo(px, py) : ctx.moveTo(px, py); pen = true; } else pen = false;
    }
    ctx.stroke();
  }

  // ---------------------------------------------------------------- interaction
  function nearest(mx, my) {
    let best = -1, bd = 14 * 14;
    for (let i = 0; i < n; i++) {
      if (!drawn.vis[i] || !show[objs[i].group]) continue;
      const dx = drawn.x[i] - mx, dy = drawn.y[i] - my, dd = dx * dx + dy * dy;
      const bias = objs[i].group === 'active' ? 30 : 0;   // prefer highlighted objects when close
      if (dd + bias < bd) { bd = dd + bias; best = i; }
    }
    return best;
  }
  function nearestPad(mx, my) {
    if (!show.pads) return null;
    return padList.find(p => p.vis && Math.hypot(p.sx - mx, p.sy - my) < 9) ?? null;
  }
  function objTip(i) {
    const o = objs[i], f = falling.get(o.norad);
    return el('div', {},
      el('div', { class: 'sp-tip-h' }, el('b', {}, o.name)),
      el('div', { class: 'sp-tip-sub' }, `NORAD ${o.norad} · ${o.cospar} · ${{ active: 'active satellite', station: 'space station', falling: 'falling' }[o.group]}`),
      el('div', {}, `Now about ${num(alt[i])} km up`),
      f ? el('div', {}, `Perigee ${num(f.perigee_km)} km, apogee ${num(f.apogee_km)} km · ${f.operator}`) : null,
      f ? el('div', {}, 'Catalogued mass ', valued(f.mass, `mass of ${f.name}`)) : null);
  }
  let drag = null;
  canvas.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, lon: view.lon, lat: view.lat, moved: false }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointerup', e => {
    if (drag && !drag.moved) {
      const b = canvas.getBoundingClientRect(), i = nearest(e.clientX - b.left, e.clientY - b.top);
      selected = i === selected ? -1 : i; draw();
    }
    drag = null;
  });
  canvas.addEventListener('pointermove', e => {
    const b = canvas.getBoundingClientRect(), mx = e.clientX - b.left, my = e.clientY - b.top;
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      view.lon = drag.lon - dx * 180 / (Math.PI * RE * k);
      view.lat = Math.max(-80, Math.min(80, drag.lat + dy * 180 / (Math.PI * RE * k)));
      hideTip(); draw(); return;
    }
    const i = nearest(mx, my), p = i < 0 ? nearestPad(mx, my) : null;
    if (i !== hover) { hover = i; draw(); }
    if (i >= 0) showTip(objTip(i), e.clientX, e.clientY);
    else if (p) showTip(el('div', {}, el('div', { class: 'sp-tip-h' }, el('b', {}, p.name ?? 'Launch site')), el('div', { class: 'sp-tip-sub' }, p.loc ?? ''),
      el('div', {}, `${p.flown} launch${p.flown === 1 ? '' : 'es'} in the window` + (p.upcoming ? `, ${p.upcoming} upcoming` : ''))), e.clientX, e.clientY);
    else hideTip();
  });
  canvas.addEventListener('pointerleave', () => { hover = -1; hideTip(); draw(); });
  canvas.addEventListener('keydown', e => {
    const d = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, 10], ArrowDown: [0, -10] }[e.key];
    if (!d) return;
    e.preventDefault();
    view.lon += d[0]; view.lat = Math.max(-80, Math.min(80, view.lat + d[1])); draw();
  });

  function focusOn(norad) {
    const i = objs.findIndex(o => o.norad === norad);
    if (i < 0 || !ok[i]) return false;
    const f = isNaN(keyT) ? 0 : Math.max(0, Math.min(1, (simT - keyT) / (KEY_S * 1000)));
    const x = pos0[3 * i] + (pos1[3 * i] - pos0[3 * i]) * f, y = pos0[3 * i + 1] + (pos1[3 * i + 1] - pos0[3 * i + 1]) * f,
      z = pos0[3 * i + 2] + (pos1[3 * i + 2] - pos0[3 * i + 2]) * f;
    view = { lon: Math.atan2(y, x) / D2R, lat: Math.max(-80, Math.min(80, Math.atan2(z, Math.hypot(x, y)) / D2R)) };
    selected = i; show[objs[i].group] = true; draw();
    canvas.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' });
    return true;
  }

  // ---------------------------------------------------------------- animation (only while on screen)
  let onScreen = false, last = 0, raf = 0;
  function frame(now) {
    raf = 0;
    if (!playing || !onScreen) return;
    const dt = Math.min(0.1, (now - (last || now)) / 1000); last = now;
    simT += dt * SPEED * 1000;
    if (simT >= keyT + KEY_S * 1000 || isNaN(keyT)) keyframe(simT);
    view.lon += dt * 3;   // slow drift so the whole planet comes round
    draw();
    raf = requestAnimationFrame(frame);
  }
  const kick = () => { if (playing && onScreen && !raf) { last = 0; raf = requestAnimationFrame(frame); } };
  new IntersectionObserver(es => { onScreen = es[0].isIntersecting; kick(); }).observe(canvas);
  playBtn.addEventListener('click', () => { playing = !playing; playBtn.textContent = playing ? 'Pause' : 'Play'; kick(); draw(); });

  keyframe(simT);
  resize();
  if (skipped) console.info(`Globe: ${skipped} objects had elements satellite.js could not use.`);
}

function fallingList(summary, objs, focusOn) {
  const inOrbitDoc = new Set(objs.map(o => o.norad));
  const items = summary.falling.slice(0, 12);
  return el('div', { class: 'sp-falling' },
    el('h3', { class: 'sp-h3' }, 'Lowest falling objects'),
    el('p', { class: 'note' }, `${summary.falling.length} catalogued object${summary.falling.length === 1 ? ' is' : 's are'} on CelesTrak’s decaying list; mass known for ${summary.coverage.falling_with_mass}. Lowest perigee first.`),
    el('ol', { class: 'sp-fall-list' }, ...items.map(f => el('li', {},
      el('button', { type: 'button', class: 'sp-linkbtn', disabled: !inOrbitDoc.has(f.norad), onclick: () => focusOn(f.norad),
        title: inOrbitDoc.has(f.norad) ? 'Show on the globe' : 'Not in the orbit file' }, f.name),
      el('span', { class: 'sp-sub' }, `${f.type} · ${f.operator}`),
      el('span', { class: 'sp-fall-nums' }, el('span', { class: 'mono' }, `${num(f.perigee_km)}–${num(f.apogee_km)} km`), ' ', valued(f.mass, `catalogued mass of ${f.name}`))))));
}

