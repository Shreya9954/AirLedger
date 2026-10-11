// Watchdog ledger: contrail warming attributed to carriers or aircraft types.
import { AGWP_CO2, CO2_PER_FUEL, typeName } from '../config.js';
import { fmt } from '../util.js';

const COLS = [
  { k: 'name', t: 'Name' }, { k: 'n', t: 'Flights' }, { k: 'pct', t: 'Predicted persistent contrail' },
  { k: 'conf', t: 'Confirmed by satellite' },
  { k: 'ct', t: 'Contrail warming tCO₂e' }, { k: 'co2', t: 'Fuel CO₂ t' }, { k: 'ratio', t: 'Contrail ÷ CO₂' },
  { k: 'av', t: 'Avoidable tCO₂e (net)' }, { k: 'pen', t: 'Extra fuel CO₂ to avoid, t' }
];

export function aggregate(flights, groupBy) {
  const m = new Map();
  for (const f of flights) {
    const key = groupBy === 'carrier' ? f.carrier.name : f.type + ' · ' + typeName(f.type);
    if (!m.has(key)) m.set(key, { name: key, n: 0, cf: 0, conf: 0, ct: 0, co2: 0, av: 0, pen: 0 });
    const r = m.get(key);
    r.n++; if (f.base.km > 0) r.cf++; if (f.attribution) r.conf++;
    r.ct += f.base.ef / AGWP_CO2; r.co2 += f.fuel * CO2_PER_FUEL;
    const b = f.opts.best; if (b.net > 0) { r.av += b.net; r.pen += b.extraCO2; }
  }
  return [...m.values()].map(r => ({ ...r, pct: r.cf / r.n, ratio: r.ct / r.co2 }));
}

export function initLedger({ table, carrierBtn, typeBtn, copyBtn, copyMsg }, sc) {
  let groupBy = 'carrier', sortKey = 'ct';

  const rows = () => aggregate(sc.flights, groupBy)
    .sort((a, b) => (sortKey === 'name' ? a.name.localeCompare(b.name) : b[sortKey] - a[sortKey]));

  function render() {
    const rs = rows(), maxCt = Math.max(...rs.map(r => r.ct));
    const head = COLS.map(c => `<th ${c.k === sortKey ? 'aria-sort="descending"' : ''}><button type="button" data-k="${c.k}">${c.k === 'name' ? (groupBy === 'carrier' ? 'Carrier' : 'Aircraft type') : c.t}</button></th>`).join('');
    const body = rs.map(r => `<tr>
      <td>${r.name}</td><td>${r.n}</td><td>${fmt(100 * r.pct)}%</td><td>${r.conf} of ${r.cf}</td>
      <td><span class="barcell"><span class="b" style="width:${Math.max(2, 70 * r.ct / maxCt)}px"></span>${fmt(r.ct)}</span></td>
      <td>${fmt(r.co2)}</td><td>${fmt(100 * r.ratio)}%</td><td>${fmt(r.av)}</td><td>${fmt(r.pen, 1)}</td></tr>`).join('');
    table.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
    table.querySelectorAll('th button').forEach(b => b.addEventListener('click', () => { sortKey = b.dataset.k; render(); }));
  }

  function setGroup(g) {
    groupBy = g;
    carrierBtn.setAttribute('aria-pressed', String(g === 'carrier'));
    typeBtn.setAttribute('aria-pressed', String(g === 'type'));
    render();
  }
  carrierBtn.addEventListener('click', () => setGroup('carrier'));
  typeBtn.addEventListener('click', () => setGroup('type'));

  copyBtn.addEventListener('click', () => {
    const rs = rows();
    const csv = [
      'group,flights,predicted_contrail_flight_share,confirmed_flights,contrail_tco2e,fuel_co2_t,contrail_to_co2,avoidable_net_tco2e,extra_fuel_co2_t',
      ...rs.map(r => [`"${r.name}"`, r.n, r.pct.toFixed(3), r.conf, r.ct.toFixed(1), r.co2.toFixed(1), r.ratio.toFixed(3), r.av.toFixed(1), r.pen.toFixed(1)].join(','))
    ].join('\n');
    navigator.clipboard.writeText(csv).then(
      () => { copyMsg.textContent = `Copied ${rs.length} rows (${sc.source === 'live' ? 'live' : 'simulated'} data).`; },
      () => { copyMsg.textContent = 'Your browser blocked the clipboard. Select the table and copy it instead.'; }
    );
  });

  render();
}
