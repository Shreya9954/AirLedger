// Entry point: load the scenario, then wire the map, rail, score chart, ledger and lab together.
import { FLS, N } from './config.js';
import { clamp, hhmm } from './util.js';
import { loadScenario, feedPreference, setFeedPreference } from './data.js';
import { renderPlan, renderCheck, renderFair, rankedPlan, recommendationFor } from './ui/plan.js';
import { readTokens, onThemeChange } from './ui/theme.js';
import { createMap } from './ui/map.js';
import { createRail } from './ui/rail.js';
import { renderScore } from './ui/score.js';
import { initLedger } from './ui/ledger.js';
import { initLab } from './ui/lab.js';

const $ = id => document.getElementById(id);
// Space ledger: loaded separately so a failure there never stops the contrail sections.
import('./space/index.js').then(m => m.initSpace()).catch(err => console.error('Space ledger failed to load:', err));
const sc = await loadScenario();

$('feed').innerHTML = { live: '<b>●</b> LIVE · ', real: '<b>●</b> OBSERVED TRACKS · FORECAST HUMIDITY · ', demo: '<b>●</b> SIMULATED FEED · ' }[sc.source] + sc.label;
{
  const btn = $('feedswitch');
  btn.textContent = sc.source === 'real' ? 'Show simulation' : 'Show real tracks';
  btn.hidden = sc.source === 'live';
  btn.addEventListener('click', () => { setFeedPreference(sc.source === 'real' ? 'sim' : 'real'); location.reload(); });
}
for (const li of document.querySelectorAll('[data-mode]')) li.hidden = li.dataset.mode !== sc.source;
$('ledger-note').textContent = ledgerNote(sc);

function ledgerNote(sc) {
  const d = sc.detections;
  if (sc.source === 'real') return `Operators come from the OpenSky aircraft database. Contrail warming is predicted, not observed: satellite confirmation ${d == null ? 'is not connected in this build (needs a Contrails.org key), so "Confirmed by satellite" is 0' : `matched ${d.matchedFlights} flights to ${d.total} GOES detections`}.`;
  if (sc.source === 'demo') return `Carriers are fictional. The ${d.total} satellite detections are simulated from the model's own contrails with a few km of position error, then matched blind: ${d.correct} of ${d.total} went to the flight that made them. Mismatches happen where two flights' drifted tracks overlap.`;
  const base = 'Operators come from the OpenSky aircraft database (unknown when an aircraft is not in it).';
  return d == null ? `${base} Satellite confirmation is off: set CONTRAILS_ORG_KEY to match GOES detections from Contrails.org.`
    : `${base} ${d.total} GOES contrail detections from Contrails.org were checked; ${d.matchedFlights} flights matched at least one.`;
}

// Open on the top recommendation (or the flight with the most contrail warming), mid humid stretch.
const worst = rankedPlan(sc)[0]?.f ?? sc.flights.reduce((a, b) => (b.base.ef > a.base.ef ? b : a));
const state = {
  T: 5, FL: worst.fl, sel: worst, selDelta: recommendationFor(worst, sc)?.d ?? worst.opts.best.d,
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

function select(f, fromTable = false) {
  state.sel = f; state.selDelta = recommendationFor(f, sc)?.d ?? f.opts.best.d; setFL(f.fl);
  if (fromTable) { // jump the clock to the flight's recommended segment and show it on the map
    const r = recommendationFor(f, sc);
    if (r) { state.T = clamp((r.from[2] + r.to[2]) / 2, 0, sc.hours); tick(); }
    $('map-sec').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }
  rail.render(); map.draw();
}

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
// The launch and re-entry markers are illustrative placeholders; don't mix them into a night of real tracks.
if (sc.source === 'real') {
  state.layers.space = false;
  $('L-space').checked = false;
  $('L-space').parentElement.append(' (illustrative, off for real tracks)');
}

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
renderPlan($('plan'), sc, f => select(f, true));
renderCheck($('checks'), sc);
renderFair($('fair'), sc);
initLedger({ table: $('ledgertable'), carrierBtn: $('g-carrier'), typeBtn: $('g-type'), copyBtn: $('copycsv'), copyMsg: $('copymsg') }, sc);
initLab($('tiles'), $('resample'));
tick();
if (document.fonts) document.fonts.ready.then(map.draw);
if (state.playing) requestAnimationFrame(loop);
