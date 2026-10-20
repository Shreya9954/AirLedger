// The decision sections: what to change tonight (ranked), how sure we are, and who benefits or pays.
// Real-night flights carry a recommendation computed under two forecasts (ECMWF and GFS); simulated
// flights have one model, so their recommendation comes from opts.best with the same range rule.
import { C0, C1, N, CO2_PER_FUEL, typeName } from '../config.js';
import { LAND } from '../geo.js';
import { fmt, hhmm } from '../util.js';

const LOW = 0.5, HIGH = 1.8; // contrail-term uncertainty, as in backend scoring.py
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const ll = ([lon, lat]) => `${Math.abs(lat).toFixed(1)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(1)}°${lon >= 0 ? 'E' : 'W'}`;
const ftChange = d => `${d > 0 ? 'Climb' : 'Descend'} ${fmt(Math.abs(d) * 100)} ft`;
const range = ([a, b], d = 0) => `${fmt(a, d)} to ${fmt(b, d)}`;

function isNight(lon, t, startHour) {
  const h = ((startHour + t + lon / 15) % 24 + 24) % 24;
  return h < 6 || h >= 18;
}

// One recommendation per flight, or null. Same shape for real and simulated data.
export function recommendationFor(f, sc) {
  if (f.recommendation !== undefined) return f.recommendation; // real night: computed in the backend
  const b = f.opts?.best;
  if (!b || b.d === 0 || !(b.net > 0)) return null;
  const iss = [];
  for (let i = C0; i < C1; i++) if (f.base.iss[i]) iss.push(i);
  const pad = Math.ceil(100 / (f.dist / N)), i0 = Math.max(0, iss[0] - pad), i1 = Math.min(N - 1, iss[iss.length - 1] + pad);
  const night = iss.filter(i => isNight(f.pts[i][0], f.pts[i][2], sc.startHour)).length;
  return {
    d: b.d, new_fl: b.fl, extraCO2: b.extraCO2, net_mean: b.net, agree: null,
    net_range: [b.avoided * LOW - b.extraCO2, b.avoided * HIGH - b.extraCO2],
    avoided_by_model: { model: b.avoided }, from: f.pts[i0], to: f.pts[i1],
    reasons: [`${fmt(f.base.km)} km of predicted persistent contrail`,
      night / iss.length > 0.5 ? 'mostly at night, when contrails only trap heat' : null].filter(Boolean)
  };
}

export function rankedPlan(sc) {
  return sc.flights.map(f => ({ f, r: recommendationFor(f, sc) })).filter(x => x.r)
    .sort((a, b) => (b.r.agree === true) - (a.r.agree === true) || b.r.net_mean - a.r.net_mean);
}

function confidence(r, sc) {
  if (r.agree === null) return '<span class="conf one">One simulated forecast</span>';
  return r.agree ? '<span class="conf both">Both forecasts agree</span>' : '<span class="conf split">Forecasts disagree</span>';
}

function avoidedRange(r) {
  const vals = Object.values(r.avoided_by_model);
  const lo = Math.min(...vals.map(a => a * (a > 0 ? LOW : HIGH))), hi = Math.max(...vals.map(a => a * (a > 0 ? HIGH : LOW)));
  return [lo, hi];
}

// ---------------------------------------------------------------- What to change tonight

export function renderPlan(el, sc, onSelect) {
  const plan = rankedPlan(sc);
  const total = plan.reduce((a, x) => a + x.r.net_mean, 0), fuel = plan.reduce((a, x) => a + x.r.extraCO2, 0);
  if (!plan.length) { el.innerHTML = '<p class="muted">No altitude change has a positive net climate benefit in this window.</p>'; return; }
  const rows = plan.map(({ f, r }, k) => `
    <tr data-id="${f.id}" tabindex="0">
      <td class="rank">${k + 1}</td>
      <td><b>${esc(f.cs)}</b><small>${esc(f.carrier.name)} · ${esc(f.type_known === false ? 'type unknown' : typeName(f.type))}</small></td>
      <td><b>${ftChange(r.d)}</b><small>FL${f.fl} → FL${r.new_fl}</small></td>
      <td class="segcell">${ll(r.from)} → ${ll(r.to)}<small>${hhmm(r.from[2], sc.startHour)}–${hhmm(r.to[2], sc.startHour)}</small></td>
      <td class="why">${r.reasons.map(esc).join('; ')}</td>
      <td class="num">${range(avoidedRange(r))}</td>
      <td class="num">${fmt(r.extraCO2, 2)}</td>
      <td class="num"><b>${fmt(r.net_mean, 1)}</b><small>${range(r.net_range, 1)}</small></td>
      <td>${confidence(r, sc)}</td>
    </tr>`).join('');
  el.innerHTML = `
    <p class="plan-sum"><b>${plan.length}</b> flights should change altitude. Together, the modeled net benefit is <b>${fmt(total, 0)} tCO₂e</b>
      (range ${range([plan.reduce((a, x) => a + x.r.net_range[0], 0), plan.reduce((a, x) => a + x.r.net_range[1], 0)], 0)}) for
      <b>${fmt(fuel, 1)} t</b> of extra fuel CO₂. These are model estimates, not measured reductions.</p>
    <div class="tablebox"><table class="plan">
      <thead><tr><th>#</th><th>Flight</th><th>Change</th><th>Segment</th><th>Why it's prioritised</th>
        <th>Contrail warming avoided, tCO₂e</th><th>Extra fuel CO₂, t</th><th>Net benefit, tCO₂e</th><th>Confidence</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <p class="note">Ranked first by whether both forecasts favour the change, then by net benefit (warming avoided minus extra fuel CO₂).
      Ranges multiply the contrail term by 0.5 and 1.8${sc.source === 'real' ? ' and span both forecasts' : ''}. Click a row to see the flight on the map.</p>`;
  el.querySelectorAll('tr[data-id]').forEach(tr => {
    const go = () => onSelect(sc.flights.find(f => f.id === +tr.dataset.id));
    tr.addEventListener('click', go);
    tr.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
  });
}

// ---------------------------------------------------------------- How sure are we?

export function renderCheck(el, sc) {
  const plan = rankedPlan(sc), v = sc.validation;
  const items = [];
  if (sc.source === 'real' && v) {
    items.push(['Do the two forecasts agree on where contrails persist?',
      `Of the ${fmt(v.contrail_points_either)} flown cruise points where either ECMWF or GFS predicts a persistent contrail, both do at only <b>${Math.round(100 * v.contrail_overlap)}%</b>.
       ECMWF predicts one on ${v.contrail_flights.ecmwf} of ${v.flights} flights, GFS on ${v.contrail_flights.gfs}, and both on ${v.both_models}.
       This disagreement is the real forecast uncertainty, measured on tonight's flights, and it is why every number below is a range.`, 'measured']);
    items.push(['How robust are the recommendations?',
      `${v.recommended_agree} of the ${v.recommended} recommended changes help under both forecasts. The other ${v.recommended - v.recommended_agree} help under one and are marked "Forecasts disagree".`, 'model']);
  } else {
    items.push(['Do forecasts agree?', 'The simulated feed has a single forecast, so there is nothing to compare. Switch to the real tracks to see ECMWF against GFS.', 'model']);
  }
  const net = plan.reduce((a, x) => a + x.r.net_mean, 0), fuel = plan.reduce((a, x) => a + x.r.extraCO2, 0);
  const lo = plan.reduce((a, x) => a + x.r.net_range[0], 0), hi = plan.reduce((a, x) => a + x.r.net_range[1], 0);
  items.push(['Estimated net warming avoided',
    `<b>${fmt(net, 0)} tCO₂e</b> over 100 years (range ${range([lo, hi], 0)}), after subtracting <b>${fmt(fuel, 1)} t</b> of extra fuel CO₂. This is a model estimate for changes nobody has made. It has not been measured.`, 'model']);
  const sat = sc.provenance?.satellite;
  if (sc.source === 'real') {
    items.push(['Were the predicted contrails seen by satellite?',
      sat?.status === 'connected'
        ? `${sat.detections} GOES detections from Contrails.org were matched to flights by wind advection; ${sat.matched_flights} flights matched at least one.`
        : `Not checked in this build. ${esc(sat?.reason ?? '')} With a key, the same build fetches GOES-East contrail detections every 30 minutes and matches each to the flight whose wind-drifted track lines up with it, so predictions can be scored against what was seen.`,
      sat?.status === 'connected' ? 'measured' : 'missing']);
  } else if (sc.detections) {
    items.push(['Were the predicted contrails seen by satellite?',
      `In the simulation, detections are generated from the model's own contrails, so this only tests the matching method: it assigned ${sc.detections.correct} of ${sc.detections.total} to the flight that made them.`, 'model']);
  }
  items.push(['What has been measured elsewhere',
    `In a 2023 trial, Google Research, Breakthrough Energy and American Airlines flew 70 flights over six months with contrail predictions. Satellite imagery showed 54% less contrail length than comparison flights, for about 2% more fuel on the flights that moved. Small sample: it shows avoidance can work, not how well it scales.`, 'measured']);
  el.innerHTML = items.map(([h, body, tag]) => `
    <div class="check"><span class="tag ${tag}">${{ measured: 'Measured', model: 'Model estimate', missing: 'Not available' }[tag]}</span>
      <h3>${h}</h3><p>${body}</p></div>`).join('');
}

// ---------------------------------------------------------------- Who benefits, who pays

function inPoly([x, y], poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
const overLand = p => LAND.some(poly => inPoly(p, poly));

export function renderFair(el, sc) {
  const plan = rankedPlan(sc);
  if (!plan.length) { el.innerHTML = '<p class="muted">No recommendations in this window.</p>'; return; }
  let land = 0, all = 0;
  for (const { f, r } of plan) for (const p of f.pts) if (p[2] >= r.from[2] && p[2] <= r.to[2]) { all++; if (overLand(p)) land++; }
  const minFl = Math.min(...plan.map(x => x.r.new_fl));
  const down = plan.filter(x => x.r.d < 0).length;
  const byOp = new Map();
  for (const { f, r } of plan) {
    const o = byOp.get(f.carrier.name) ?? { n: 0, co2: 0 };
    o.n++; o.co2 += r.extraCO2; byOp.set(f.carrier.name, o);
  }
  const ops = [...byOp].sort((a, b) => b[1].co2 - a[1].co2).slice(0, 6);
  const cargoAll = sc.flights.filter(f => f.cargo).length, cargoRec = plan.filter(x => x.f.cargo).length;
  const unknown = sc.flights.filter(f => f.type_known === false).length;
  const real = sc.source === 'real', pv = sc.provenance;
  el.innerHTML = `
    <div class="fair-grid">
      <div>
        <h3>Who benefits</h3>
        <p>Avoided contrail warming is a <b>global, shared</b> benefit: it lowers radiative forcing everywhere, not under the route. No community gets a local gain, and none is singled out.</p>
        <h3>Who pays</h3>
        <p>Operators burn the extra fuel and pay for it: <b>${fmt(plan.reduce((a, x) => a + x.r.extraCO2, 0), 1)} t CO₂</b> across ${plan.length} flights, and that CO₂ is a long-lived global cost already subtracted from the benefit.</p>
        <table class="opts fair-ops"><thead><tr><th>Operator</th><th>Flights asked</th><th>Extra fuel CO₂, t</th></tr></thead>
          <tbody>${ops.map(([n, o]) => `<tr><td>${esc(n)}</td><td>${o.n}</td><td>${fmt(o.co2, 2)}</td></tr>`).join('')}</tbody></table>
      </div>
      <div>
        <h3>Does it move noise or pollution onto someone else?</h3>
        <p>Every recommended change happens at <b>FL${minFl} or higher</b> (about ${fmt(minFl * 30.48 / 1000, 1)} km up). Aircraft noise and local air quality matter mostly below about 3 km, around airports, so a cruise altitude change does not move noise onto communities on the ground.
          ${fmt(100 * land / Math.max(1, all))}% of the recommended segments are over land and the rest over ocean.</p>
        <p>Burdens it can shift: <b>${down} of ${plan.length}</b> changes are descents, which cost more fuel than climbs; heavy or older aircraft often cannot climb, so they carry more of the cost. Moving a flight to a new level takes air-traffic-control capacity that other flights may then not get.
          ${cargoAll ? `Cargo operators fly ${cargoAll} of the ${sc.flights.length} flights here and ${cargoRec} of the ${plan.length} recommendations; night flying, where contrails warm most, is common for cargo.` : ''}</p>
      </div>
    </div>
    <h3>Limits of the data</h3>
    <ul class="limits">
      ${real ? `<li><b>Tracks are incomplete over the ocean.</b> OpenSky's ADS-B receivers are on land, so mid-Atlantic stretches are missing. Flights near the coasts are overrepresented, which biases who gets recommendations.</li>
      <li><b>${unknown} of ${sc.flights.length} aircraft types are unknown</b> in OpenSky's database; their fuel burn uses a default of 4 t/h.</li>
      <li><b>Origin and destination are not available</b> from the anonymous API, and tracks cover only the last ${fmt(sc.hours)} hours.</li>` : '<li><b>Flights, carriers and humidity are simulated.</b> Switch to the real tracks for observed data.</li>'}
      <li><b>Humidity at cruise is the weakest part of any forecast.</b> Models report at most 100% and under-predict supersaturation; we count 95% or more as ice-saturated. Forecast levels are about 4,000 ft apart (FL300, FL340, FL390), coarser than the 2,000 ft changes being priced.</li>
      <li><b>The contrail model is a screening model, not CoCiP.</b> It checks the Schmidt–Appleman criterion and ice saturation, and attaches an illustrative warming per km. Use it to rank options, not to report tonnes.</li>
      <li><b>Satellite verification ${real && pv?.satellite?.status === 'connected' ? 'covers GOES-East only' : 'was not run'}.</b> Without it, nothing here confirms that a predicted contrail formed.</li>
    </ul>`;
}
