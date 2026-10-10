// The North Atlantic plotting table: coastlines, ISSR raster, contrails, flights, space events.
import { N, C0, C1 } from '../config.js';
import { LON0, LON1, LAT0, LAT1, ASPECT, LAND, AIRPORTS } from '../geo.js';
import { efPerKm, flightPos, inIssrAt } from '../model.js';
import { C } from './theme.js';

const GW = 132, GH = 84; // ISSR raster resolution, upscaled with smoothing
const CONTRAIL_LIFE_H = 6, SPACE_LIFE_H = 4;

export function createMap(canvas, wrap, sc, state, onSelect) {
  const ctx = canvas.getContext('2d');
  const off = document.createElement('canvas'); off.width = GW; off.height = GH;
  const octx = off.getContext('2d');
  let W = 800, H = 500, issrKey = '';

  const px = lon => ((lon - LON0) / (LON1 - LON0)) * W;
  const py = lat => ((LAT1 - lat) / (LAT1 - LAT0)) * H;

  function size() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    W = wrap.clientWidth; H = Math.round(W / ASPECT);
    canvas.style.height = H + 'px'; canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); issrKey = ''; draw();
  }

  function buildIssr() {
    const key = state.FL + '|' + state.T.toFixed(2) + '|' + C.ice;
    if (key === issrKey) return; issrKey = key;
    const img = octx.createImageData(GW, GH), [r, g, b] = C.iceRGB;
    for (let j = 0; j < GH; j++) for (let i = 0; i < GW; i++) {
      const lon = LON0 + (i + 0.5) / GW * (LON1 - LON0), lat = LAT1 - (j + 0.5) / GH * (LAT1 - LAT0);
      const v = sc.atmos.rhi(lon, lat, state.FL, state.T);
      const a = v > 1 ? 0.32 + Math.min(0.38, (v - 1) * 2.5) : Math.max(0, (v - 0.9) / 0.1) * 0.1;
      const o = (j * GW + i) * 4;
      img.data[o] = r; img.data[o + 1] = g; img.data[o + 2] = b; img.data[o + 3] = a * 255;
    }
    octx.putImageData(img, 0, 0);
  }

  const path = pts => { ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(px(p[0]), py(p[1])) : ctx.moveTo(px(p[0]), py(p[1])))); };

  function drawBase() {
    ctx.fillStyle = C.sea; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = C.rule; ctx.lineWidth = 0.6; ctx.setLineDash([2, 4]);
    ctx.font = '10px "IBM Plex Mono", Menlo, monospace'; ctx.fillStyle = C['ink-2'];
    for (let lon = -80; lon <= 10; lon += 10) {
      ctx.beginPath(); ctx.moveTo(px(lon), 0); ctx.lineTo(px(lon), H); ctx.stroke();
      if (W > 500 || lon % 20 === 0) ctx.fillText(Math.abs(lon) + '°' + (lon < 0 ? 'W' : lon > 0 ? 'E' : ''), px(lon) + 3, H - 5);
    }
    for (let lat = 30; lat <= 65; lat += 5) {
      ctx.beginPath(); ctx.moveTo(0, py(lat)); ctx.lineTo(W, py(lat)); ctx.stroke();
      if (lat % 10 === 0) ctx.fillText(lat + '°N', 4, py(lat) - 3);
    }
    ctx.setLineDash([]);
    ctx.fillStyle = C.land; ctx.strokeStyle = C['ink-2']; ctx.lineWidth = 0.8;
    for (const p of LAND) { path(p); ctx.closePath(); ctx.fill(); ctx.stroke(); }
  }

  function drawAirports() {
    ctx.fillStyle = C.ink; ctx.font = '500 10px "IBM Plex Mono", Menlo, monospace';
    for (const [k, p] of Object.entries(AIRPORTS)) {
      if (p[0] < LON0 || p[1] < LAT0) continue;
      ctx.fillRect(px(p[0]) - 2, py(p[1]) - 2, 4, 4);
      if (W > 560) ctx.fillText(k, px(p[0]) + 5, py(p[1]) + 3);
    }
  }

  // Contrails drift east with the wind and widen as they age.
  function drawContrails() {
    const T = state.T, wind = sc.atmos.wind;
    ctx.lineCap = 'round';
    for (const f of sc.flights) {
      if (!f.base.km || f.pts[C0][2] > T) continue;
      for (let i = C0; i < C1; i++) {
        if (!f.base.iss[i]) continue;
        const a = f.pts[i], b = f.pts[i + 1], age = T - a[2];
        if (age < 0 || age > CONTRAIL_LIFE_H) continue;
        const drift = wind * age;
        ctx.strokeStyle = efPerKm(a[0], a[2], 1.1, f.type, sc.startHour) >= 0 ? C.heat : C.cool;
        ctx.globalAlpha = (1 - age / CONTRAIL_LIFE_H) * (f === state.sel ? 0.95 : 0.6);
        ctx.lineWidth = 1 + age * 0.9;
        ctx.beginPath(); ctx.moveTo(px(a[0] + drift), py(a[1])); ctx.lineTo(px(b[0] + drift), py(b[1])); ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }

  function drawSelectedTrack() {
    const s = state.sel; if (!s) return;
    ctx.strokeStyle = C.ink; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
    path(s.pts); ctx.stroke(); ctx.setLineDash([]);
    ctx.strokeStyle = C.magenta; ctx.lineWidth = 3;
    for (let i = C0; i < C1; i++) {
      if (!s.base.iss[i]) continue;
      ctx.beginPath(); ctx.moveTo(px(s.pts[i][0]), py(s.pts[i][1])); ctx.lineTo(px(s.pts[i + 1][0]), py(s.pts[i + 1][1])); ctx.stroke();
    }
  }

  function drawSpace() {
    for (const e of sc.space) {
      const age = state.T - e.t; if (age < 0 || age > SPACE_LIFE_H) continue;
      const fade = 1 - age / SPACE_LIFE_H;
      ctx.strokeStyle = C.orbit; ctx.fillStyle = C.orbit; ctx.globalAlpha = 0.35 + 0.65 * fade;
      ctx.lineWidth = e.kind === 'launch' ? 2 : 1.5; ctx.setLineDash(e.kind === 'launch' ? [] : [6, 3]);
      path(e.path); ctx.stroke(); ctx.setLineDash([]);
      const end = e.path[e.path.length - 1], x = px(end[0] + sc.atmos.wind * age), y = py(end[1]);
      ctx.globalAlpha = 0.18 * fade + 0.05; ctx.beginPath(); ctx.arc(x, y, 8 + age * 9, 0, 6.283); ctx.fill();
      ctx.globalAlpha = 1; ctx.beginPath(); ctx.arc(x, y, 4, 0, 6.283); ctx.fill();
      ctx.fillStyle = C.ink; ctx.font = 'italic 13px "Instrument Serif", Georgia, serif';
      ctx.fillText(e.name, x + 8, y - 6);
    }
    ctx.globalAlpha = 1;
  }

  function drawFlights() {
    for (const f of sc.flights) {
      const p = flightPos(f, state.T); if (!p) continue;
      const x = px(p.lon), y = py(p.lat);
      const nxt = f.pts[p.i + 1], hd = Math.atan2(-(py(nxt[1]) - py(f.pts[p.i][1])), px(nxt[0]) - px(f.pts[p.i][0]));
      ctx.globalAlpha = f.fl === state.FL || f === state.sel ? 1 : 0.4;
      ctx.save(); ctx.translate(x, y); ctx.rotate(-hd);
      ctx.fillStyle = inIssrAt(f, p) ? C.magenta : C.ink;
      ctx.beginPath(); ctx.moveTo(6, 0); ctx.lineTo(-4, -4); ctx.lineTo(-2, 0); ctx.lineTo(-4, 4); ctx.closePath(); ctx.fill();
      ctx.restore();
      if (f === state.sel) {
        ctx.globalAlpha = 1; ctx.strokeStyle = C.magenta; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(x, y, 11, 0, 6.283); ctx.stroke();
        ctx.fillStyle = C.ink; ctx.font = '500 11px "IBM Plex Mono", Menlo, monospace';
        ctx.fillText(f.cs + ' FL' + f.fl, x + 14, y - 8);
      }
    }
    ctx.globalAlpha = 1;
  }

  function draw() {
    if (!C.ink) return;
    ctx.clearRect(0, 0, W, H);
    drawBase();
    if (state.layers.issr) { buildIssr(); ctx.imageSmoothingEnabled = true; ctx.drawImage(off, 0, 0, W, H); }
    drawAirports();
    if (state.layers.con) drawContrails();
    drawSelectedTrack();
    if (state.layers.space) drawSpace();
    drawFlights();
  }

  canvas.addEventListener('click', ev => {
    const r = canvas.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
    let best = null, bd = 18;
    for (const f of sc.flights) {
      const p = flightPos(f, state.T); if (!p) continue;
      const d = Math.hypot(px(p.lon) - mx, py(p.lat) - my);
      if (d < bd) { bd = d; best = f; }
    }
    if (best) onSelect(best);
  });

  new ResizeObserver(size).observe(wrap);
  size();
  return { draw, invalidate: () => { issrKey = ''; } };
}
