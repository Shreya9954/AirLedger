// Entry point: load the scenario, then wire the map, rail, score chart, ledger and lab together.
import { FLS, N } from './config.js';
import { clamp, hhmm } from './util.js';
import { loadScenario } from './data.js';
import { readTokens, onThemeChange } from './ui/theme.js';
import { createMap } from './ui/map.js';
import { createRail } from './ui/rail.js';
import { renderScore } from './ui/score.js';
import { initLedger } from './ui/ledger.js';
import { initLab } from './ui/lab.js';

const $ = id => document.getElementById(id);
const sc = await loadScenario();

$('feed').innerHTML = (sc.source === 'live' ? '<b>●</b> LIVE · ' : '<b>●</b> SIMULATED FEED · ') + sc.label;

// Open on the flight with the most contrail warming, at the middle of its humid stretch.
const worst = sc.flights.reduce((a, b) => (b.base.ef > a.base.ef ? b : a));
const state = {
  T: 5, FL: worst.fl, sel: worst, selDelta: worst.opts.best.d,
  playing: !matchMedia('(prefers-reduced-motion: reduce)').matches,
  layers: { issr: true, con: true, space: true }
};
{
  let fi = -1, li = -1;
  for (let i = 0; i < N; i++) if (worst.base.iss[i]) { if (fi < 0) fi = i; li = i; }
  if (fi >= 0) state.T = clamp(worst.pts[Math.round((fi + li) / 2)][2], 0, sc.hours);
}

readTokens();
const rail = createRail($('rail'), sc, state);
const map = createMap($('map'), $('cwrap'), sc, state, select);
onThemeChange(() => { map.invalidate(); map.draw(); });

function select(f) { state.sel = f; state.selDelta = f.opts.best.d; setFL(f.fl); rail.render(); map.draw(); }

// Flight-level buttons
const flBox = $('fls');
for (const fl of FLS) {
  const b = document.createElement('button');
  b.type = 'button'; b.textContent = fl; b.dataset.fl = fl;
  b.addEventListener('click', () => { setFL(fl); map.draw(); });
  flBox.appendChild(b);
}
function setFL(fl) { state.FL = fl; flBox.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.fl === fl))); }

// Layer toggles
for (const k of ['issr', 'con', 'space']) $('L-' + k).addEventListener('change', e => { state.layers[k] = e.target.checked; map.draw(); });

// Time and playback: one simulated hour every 5 seconds.
const timeEl = $('time'), clockEl = $('clock'), playBtn = $('play');
timeEl.max = sc.hours;
timeEl.setAttribute('aria-label', `Scenario time, ${hhmm(0, sc.startHour)} to ${hhmm(sc.hours, sc.startHour)}`);
let last = performance.now();
function tick() { clockEl.textContent = hhmm(state.T, sc.startHour); timeEl.value = state.T; map.draw(); rail.updateStatus(); }
function loop(now) {
  if (!state.playing) return;
  const dt = Math.min(0.1, (now - last) / 1000); last = now;
  state.T += dt / 5; if (state.T > sc.hours) state.T = 0;
  tick(); requestAnimationFrame(loop);
}
timeEl.addEventListener('input', () => { state.T = +timeEl.value; tick(); });
playBtn.addEventListener('click', () => {
  state.playing = !state.playing;
  playBtn.textContent = state.playing ? 'Pause' : 'Play';
  if (state.playing) { last = performance.now(); requestAnimationFrame(loop); }
});
playBtn.textContent = state.playing ? 'Pause' : 'Play';

setFL(state.FL);
rail.render();
renderScore($('scorechart'), $('readout'), sc);
initLedger({ table: $('ledgertable'), carrierBtn: $('g-carrier'), typeBtn: $('g-type'), copyBtn: $('copycsv'), copyMsg: $('copymsg') }, sc);
initLab($('tiles'), $('resample'));
tick();
if (document.fonts) document.fonts.ready.then(map.draw);
if (state.playing) requestAnimationFrame(loop);
