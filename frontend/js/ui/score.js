// "One score": flights, launches and re-entries on a single log-scale tCO2e axis with ranges.
import { AGWP_CO2, CO2_PER_FUEL, TYPES } from '../config.js';
import { fmt, median } from '../util.js';

const lx = v => (Math.log10(Math.max(1, v)) / 4) * 100; // 1 .. 10,000 tCO2e

export function renderScore(el, readout, sc) {
  const flights = sc.flights;
  const wide = flights.filter(f => (TYPES[f.type]?.burn ?? f.fuel / f.dur) > 5);
  const co2Med = median(wide.map(f => f.fuel * CO2_PER_FUEL));
  const contrailMed = median(flights.filter(f => f.base.ef > 0).map(f => f.base.ef / AGWP_CO2));
  const worst = flights.reduce((a, b) => (b.base.ef > a.base.ef ? b : a));
  const wc = worst.base.ef / AGWP_CO2, wco2 = worst.fuel * CO2_PER_FUEL;

  const rows = [
    { g: 'air', name: 'Wide-body transatlantic flight', note: 'Fuel CO₂ only, median tonight', c: co2Med, lo: co2Med * 0.9, hi: co2Med * 1.1,
      why: 'Fuel burned × 3.16 t CO₂ per tonne of jet fuel. Narrow uncertainty: fuel use is well measured.' },
    { g: 'air', name: 'Contrail term, typical', note: 'Median of flights that formed one', c: contrailMed, lo: contrailMed * 0.5, hi: contrailMed * 1.8,
      why: 'Energy forcing from the contrail model ÷ AGWP of CO₂. Humidity forecasts and cirrus optical properties drive a roughly twofold uncertainty.' },
    { g: 'air', name: 'Worst flight tonight', note: `${worst.cs} · ${worst.o}→${worst.d}, fuel + contrail`, c: wco2 + wc, lo: wco2 + wc * 0.5, hi: wco2 + wc * 1.8,
      why: 'The single largest contrail producer in the window. Most of its total comes from one humid stretch it could have avoided.' },
    ...sc.space.slice(0, 4).map(e => ({ g: 'space', name: e.name, note: e.note, c: e.c, lo: e.lo, hi: e.hi, why: e.why }))
  ];

  let h = `<div class="sc-axis" aria-hidden="true"><span class="lbl">Event</span><div class="ax">${[1, 10, 100, '1k', '10k'].map((v, i) => `<span style="left:${i * 25}%">${v}</span>`).join('')}</div><span class="lbl" style="text-align:right">tCO₂e</span></div>`;
  rows.forEach((r, i) => {
    const col = r.g === 'air' ? 'var(--ink)' : 'var(--orbit)';
    h += `<div class="sc-row" tabindex="0" data-i="${i}"><div class="name">${r.name}<small>${r.note}</small></div><div class="plot"><span class="whisk" style="left:${lx(r.lo)}%;width:${lx(r.hi) - lx(r.lo)}%;background:${col}"></span><span class="dot" style="left:${lx(r.c)}%;background:${col}"></span></div><div class="num">${fmt(r.c)}</div></div>`;
  });
  h += `<div class="legend" style="padding:10px 0 0"><span><i class="sw" style="background:var(--ink);width:10px;height:10px;border-radius:50%"></i>Aviation</span><span><i class="sw" style="background:var(--orbit);width:10px;height:10px;border-radius:50%"></i>Space (illustrative)</span><span>Whisker = plausible range</span></div>`;
  el.innerHTML = h;

  el.querySelectorAll('.sc-row').forEach(row => {
    const show = () => {
      const r = rows[+row.dataset.i];
      readout.innerHTML = `<b style="color:var(--ink)">${r.name}: ${fmt(r.c)} tCO₂e</b> (range ${fmt(r.lo)}–${fmt(r.hi)}). ${r.why}`;
    };
    row.addEventListener('mouseenter', show); row.addEventListener('focus', show);
  });
}
