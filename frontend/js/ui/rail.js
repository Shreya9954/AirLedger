// Instrument rail: selected flight details, contrail attribution and the reroute slider.
import { AGWP_CO2, CO2_PER_FUEL, DELTAS, C0, C1, typeName } from '../config.js';
import { fmt, sci, hhmm } from '../util.js';
import { flightPos, inIssrAt } from '../model.js';

const ft = d => (d > 0 ? '+' : d < 0 ? '−' : '±') + fmt(Math.abs(d) * 100) + ' ft';
const signed = (n, d = 1) => (n >= 0 ? '+' : '−') + fmt(Math.abs(n), d);

export function createRail(el, sc, state) {
  let lastStatus = '';

  function statusText(f) {
    const p = flightPos(f, state.T);
    if (!p) return state.T < f.pts[0][2]
      ? `<span class="pill calm">SCHEDULED · DEP ${hhmm(f.dep, sc.startHour)}</span>`
      : `<span class="pill calm">LANDED · ${hhmm(f.arr, sc.startHour)}</span>`;
    return inIssrAt(f, p)
      ? '<span class="pill hot">IN ICE-SUPERSATURATED AIR NOW</span>'
      : '<span class="pill calm">AIRBORNE · CLEAR AIR</span>';
  }

  // Satellite detection matched to this flight, if any (live: GOES via Contrails.org; demo: simulated).
  function attribution(f) {
    if (!f.base.km) return '<div class="attrib">No persistent contrail expected on this route tonight.</div>';
    const a = f.attribution;
    if (!a) {
      const why = sc.detections == null ? 'Satellite matching is off: no Contrails.org key is configured.'
        : `None of the ${fmt(sc.detections.total)} ${sc.source === 'demo' ? 'simulated ' : ''}satellite detections tonight matched this flight.`;
      return `<div class="attrib">Contrail predicted by the model, not confirmed by a satellite detection.<br><span class="mono">${why}</span></div>`;
    }
    const kind = a.simulated ? 'Simulated satellite detection' : 'GOES satellite detection';
    const more = a.n_matched > 1 ? ` · ${a.n_matched} detections matched` : '';
    return `<div class="attrib">${kind} <b>${a.id}</b> at ${hhmm(a.observed_h, sc.startHour)} matched to this aircraft after wind advection.<br>
      <span class="mono">offset ${a.offset_km.toFixed(1)} km · contrail age ${a.age_min} min · confidence ${a.confidence.toFixed(2)}${more}</span></div>`;
  }

  function reroute(f, co2) {
    const o = f.opts;
    if (!f.base.km) return `<p class="muted" style="font-size:.86rem">Nothing to avoid: this flight stays in dry air at FL${f.fl}. Pick a magenta aircraft on the map, or a thick red trail.</p>`;
    const opt = o[state.selDelta];
    const valid = DELTAS.map(d => o[d]).filter(Boolean);
    const maxV = Math.max(1, ...valid.map(x => Math.max(x.avoided, x.extraCO2)));
    const bars = opt ? `
      <div class="vs">
        <div class="row"><span>Extra fuel CO₂</span><span class="track"><span class="fill" style="width:${100 * opt.extraCO2 / maxV}%;background:var(--ink-2)"></span></span><span class="val">${fmt(opt.extraCO2, 1)} t</span></div>
        <div class="row"><span>Warming avoided</span><span class="track"><span class="fill" style="width:${100 * Math.max(0, opt.avoided) / maxV}%;background:var(--cool)"></span></span><span class="val">${fmt(opt.avoided, 1)} t</span></div>
      </div>
      <div class="net"><span><small>Net climate benefit at FL${opt.fl}</small><br><b>${opt.net >= 0 ? '' : '−'}${fmt(Math.abs(opt.net), 1)} tCO₂e</b></span><small>${opt.extraCO2 ? '+' + fmt(100 * opt.extraCO2 / co2, 2) + '% fuel' : 'flight plan as filed'}</small></div>`
      : `<p class="muted" style="font-size:.84rem">FL${f.fl + state.selDelta} is outside this aircraft's usable range.</p>`;
    const rows = DELTAS.map(d => {
      const x = o[d];
      if (!x) return `<tr><td>${ft(d)}</td><td colspan="3" class="muted">above ceiling / too low</td></tr>`;
      const cls = [x.d === o.best.d && d !== 0 ? 'best' : '', d === state.selDelta ? 'cur' : ''].join(' ');
      return `<tr data-d="${d}" class="${cls}"><td>${ft(d)} · FL${x.fl}</td><td>${fmt(x.km)}</td><td>${fmt(x.extraCO2, 1)}</td><td>${signed(x.net)}</td></tr>`;
    }).join('');
    return `
      <div class="muted" style="font-size:.84rem">Change altitude across the ${fmt(o.wkm)} km humid stretch only.</div>
      <input type="range" id="dslider" min="-40" max="40" step="20" value="${state.selDelta}" aria-label="Altitude change">
      <div class="ticks"><span>−4,000 ft</span><span>−2,000</span><span>0</span><span>+2,000</span><span>+4,000 ft</span></div>
      ${bars}
      <table class="opts"><thead><tr><th>Option</th><th>Contrail km</th><th>Fuel t CO₂</th><th>Net</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="muted" style="font-size:.76rem;margin-top:6px">Green row is the best option. Click a row to preview it.</div>`;
  }

  function render() {
    const f = state.sel;
    const cruiseKm = f.seg.slice(C0, C1).reduce((a, b) => a + b, 0);
    const ct = f.base.ef / AGWP_CO2, co2 = f.fuel * CO2_PER_FUEL;
    el.innerHTML = `
      <div>
        <div class="lbl">Selected flight · click any aircraft</div>
        <div class="callsign">${f.cs}</div>
        <div class="sub">${f.carrier.name} · ${typeName(f.type)}</div>
        <div class="sub mono" style="font-size:.8rem">${f.o} → ${f.d} · FL${f.fl} · ${hhmm(f.dep, sc.startHour)}–${hhmm(f.arr, sc.startHour)}</div>
        <div id="status" style="margin-top:8px">${statusText(f)}</div>
      </div>
      <dl class="kv">
        <dt>Persistent contrail</dt><dd>${fmt(f.base.km)} km · ${fmt(100 * f.base.km / cruiseKm)}% of cruise</dd>
        <dt>Energy forcing</dt><dd>${sci(f.base.ef)}</dd>
        <dt>Contrail warming</dt><dd>${fmt(ct)} tCO₂e</dd>
        <dt>Fuel CO₂</dt><dd>${fmt(co2)} t</dd>
        <dt>Total impact</dt><dd><b>${fmt(co2 + ct)} tCO₂e</b></dd>
      </dl>
      ${attribution(f)}
      <div class="reroute"><h3>Reroute this flight</h3>${reroute(f, co2)}</div>`;

    const s = el.querySelector('#dslider');
    if (s) s.addEventListener('input', () => { state.selDelta = +s.value; render(); el.querySelector('#dslider').focus(); });
    el.querySelectorAll('tr[data-d]').forEach(tr => tr.addEventListener('click', () => { state.selDelta = +tr.dataset.d; render(); }));
    lastStatus = statusText(f);
  }

  // Called every animation frame; only touches the DOM when the status pill changes.
  function updateStatus() {
    const s = statusText(state.sel);
    if (s === lastStatus) return;
    lastStatus = s;
    const node = el.querySelector('#status'); if (node) node.innerHTML = s;
  }

  return { render, updateStatus };
}
