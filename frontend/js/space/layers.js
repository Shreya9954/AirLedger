// "Layers of the sky": what each source leaves in every 5-km slice from the ground to 120 km.
// One species at a time (soot and propellant can't be added together). Mass spans six or more orders of
// magnitude between aviation and a single re-entry, so the mass axis is logarithmic and each value is drawn
// as a dot (central estimate) on a line (plausible range) rather than as a bar.
import { el, svg, mass, num, valued, showTip, hideTip } from './format.js';

const SOURCES = [
  { id: 'launch', label: 'Rocket launches', cls: 'sp-launch' },
  { id: 'reentry', label: 'Re-entering spacecraft', cls: 'sp-reentry' },
  { id: 'aviation', label: 'Global aviation, for scale', cls: 'sp-aviation' }
];
const SPECIES = {
  black_carbon: { label: 'Soot', long: 'Soot (black carbon)' },
  propellant: { label: 'Fuel burned', long: 'Rocket propellant and jet fuel burned' },
  alumina: { label: 'Alumina', long: 'Alumina particles from solid rocket motors' },
  chlorine: { label: 'Chlorine', long: 'Chlorine from solid rocket motors' },
  ablated_mass: { label: 'Burned-up metal', long: 'Spacecraft mass burned up on re-entry' },
  aluminium: { label: 'Aluminium', long: 'Aluminium in the burned-up mass' }
};
const ROW = 18, M0 = { l: 54, r: 14, t: 6, b: 34 }, LABEL_W = 96;

export function renderLayers(root, doc) {
  const cells = doc.layers;
  const present = Object.keys(SPECIES).filter(sp => cells.some(c => c.species === sp));
  root.replaceChildren();
  if (!present.length) {
    root.append(el('p', { class: 'note' }, 'No altitude data in this dataset yet.'));
    return;
  }
  let species = present.includes('black_carbon') ? 'black_carbon' : present[0];

  const seg = el('div', { class: 'seg', role: 'group', 'aria-label': 'Which substance to show' });
  const legend = el('div', { class: 'sp-legend', 'aria-live': 'polite' });
  const story = el('p', { class: 'sp-story' });
  const chart = el('div', { class: 'sp-layers-chart' });
  const table = el('details', { class: 'sp-tableview' });
  root.append(el('div', { class: 'ledger-tools' }, el('span', { class: 'lbl' }, 'Show'), seg), legend, chart, story, table);

  for (const sp of present) {
    seg.append(el('button', {
      type: 'button', 'data-sp': sp, 'aria-pressed': String(sp === species),
      onclick: () => { species = sp; seg.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.sp === sp))); draw(); }
    }, SPECIES[sp].label));
  }

  let width = 0;
  function draw() {
    const rows = cells.filter(c => c.species === species);
    drawLegend(legend, rows, species);
    drawStory(story, rows, species);
    drawChart(chart, rows, doc, species, width || chart.clientWidth || 640);
    drawTable(table, rows, species);
  }
  new ResizeObserver(entries => {
    const w = Math.round(entries[0].contentRect.width);
    if (w && Math.abs(w - width) > 4) { width = w; requestAnimationFrame(draw); }
  }).observe(chart);
  draw();
}

function totals(rows) {
  const t = {};
  for (const c of rows) {
    const v = c.value, o = t[c.source] ??= { central: 0, low: 0, high: 0, unit: 'kg', tier: 'fact', sources: new Set(), notes: new Set() };
    o.central += v.central; o.low += v.low; o.high += v.high;
    if (['fact', 'estimate', 'research'].indexOf(v.tier) > ['fact', 'estimate', 'research'].indexOf(o.tier)) o.tier = v.tier;
    v.source.split('+').forEach(s => o.sources.add(s));
    if (v.note) o.notes.add(v.note);
  }
  for (const o of Object.values(t)) {
    o.source = [...o.sources].sort().join('+');
    o.note = o.notes.size === 1 ? [...o.notes][0] : '';
  }
  return t;
}

function drawLegend(node, rows, species) {
  const t = totals(rows);
  node.replaceChildren(...SOURCES.filter(s => t[s.id]).map(s =>
    el('span', { class: 'sp-key' },
      el('i', { class: `sp-dotkey ${s.cls}`, 'aria-hidden': 'true' }),
      el('span', {}, s.id === 'aviation' && species === 'propellant' ? 'Global aviation (jet fuel), for scale' : s.label),
      el('span', { class: 'muted' }, ' · total '),
      valued(t[s.id], `${SPECIES[species].long}, ${s.label.toLowerCase()}, all heights`))));
  node.append(el('span', { class: 'sp-key muted' }, el('i', { class: 'sp-rangekey', 'aria-hidden': 'true' }), 'dot = central estimate, line = plausible range'));
}

function drawStory(node, rows, species) {
  const share = (src, minKm) => {
    const all = rows.filter(c => c.source === src).reduce((a, c) => a + c.value.central, 0);
    const hi = rows.filter(c => c.source === src && c.lo_km >= minKm).reduce((a, c) => a + c.value.central, 0);
    return all ? hi / all : null;
  };
  const rocket = share('launch', 15), air = share('aviation', 15);
  const bits = [];
  if (rocket != null) bits.push(`Rockets leave ${num(100 * rocket)}% of it above 15 km, in the stratosphere and higher, where particles can stay for years.`);
  if (air != null) bits.push(`Aviation leaves ${num(100 * air)}% above 15 km.`);
  if (species === 'ablated_mass' || species === 'aluminium') bits.push('Re-entering spacecraft break up and vaporise between about 80 and 60 km, in the mesosphere; the metal then drifts down into the stratosphere.');
  if (species === 'propellant') bits.push('Rocket propellant counts only the part burned below 120 km; the rest burns in space.');
  node.textContent = bits.join(' ');
}

function drawChart(node, rows, doc, species, W) {
  node.replaceChildren();
  const top = doc.bins_km[doc.bins_km.length - 1];
  // region names sit in a right-hand margin when there is room, otherwise inside the bands with a halo
  const wide = W >= 620, M = { ...M0, r: wide ? LABEL_W : M0.r };
  const H = M.t + (top / 5) * ROW + M.b, iw = W - M.l - M.r;
  const y = km => M.t + (top - km) / 5 * ROW;
  const pos = rows.flatMap(c => [c.value.low, c.value.central, c.value.high]).filter(v => v > 0);
  let lo = 10 ** Math.floor(Math.log10(Math.min(...pos))), hi = 10 ** Math.ceil(Math.log10(Math.max(...pos)));
  if (hi <= lo) hi = lo * 10;
  const L0 = Math.log10(lo), L1 = Math.log10(hi);
  const x = v => M.l + (Math.log10(Math.max(v, lo)) - L0) / (L1 - L0) * iw;

  const s = svg('svg', { class: 'sp-svg', width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `${SPECIES[species].long} by height, 0 to ${top} km, on a logarithmic mass scale. Use the table view below for the numbers.` });

  // atmosphere regions
  doc.regions.forEach((r, i) => {
    const y0 = y(Math.min(r.hi_km, top)), y1 = y(r.lo_km);
    s.append(svg('rect', { x: M.l, y: y0, width: iw, height: y1 - y0, class: i % 2 ? 'sp-band alt' : 'sp-band' }));
    const t = wide
      ? svg('text', { x: M.l + iw + 8, y: (y0 + y1) / 2 + 3, class: 'sp-region' })
      : svg('text', { x: M.l + iw - 4, y: y0 + 11, class: 'sp-region sp-halo', 'text-anchor': 'end' });
    t.textContent = r.name;
    s.append(t);
  });
  // mass grid (one line per factor of ten) and height axis
  const decades = [];
  for (let d = L0; d <= L1; d++) decades.push(10 ** d);
  const step = Math.ceil(decades.length / Math.max(2, Math.floor(iw / 70)));
  decades.forEach((v, i) => {
    s.append(svg('line', { x1: x(v), x2: x(v), y1: M.t, y2: y(0), class: 'sp-grid' }));
    if (i % step === 0) {
      const t = svg('text', { x: x(v), y: y(0) + 16, 'text-anchor': i === 0 ? 'start' : 'middle', class: 'sp-tick' });
      t.textContent = mass(v);
      s.append(t);
    }
  });
  const xl = svg('text', { x: M.l + iw, y: H - 4, 'text-anchor': 'end', class: 'sp-tick' });
  xl.textContent = 'mass per 5-km slice, log scale (each line is ×10)';
  s.append(xl);
  for (let km = 0; km <= top; km += 20) {
    const t = svg('text', { x: M.l - 8, y: y(km) + 4, 'text-anchor': 'end', class: 'sp-tick' });
    t.textContent = km === 0 ? '0 km' : String(km);
    s.append(t);
  }
  s.append(svg('line', { x1: M.l, x2: M.l + iw, y1: y(0), y2: y(0), class: 'sp-axis' }));

  // marks: one row per 5-km bin, sources offset inside the row
  const byBin = new Map();
  for (const c of rows) {
    if (!byBin.has(c.lo_km)) byBin.set(c.lo_km, {});
    byBin.get(c.lo_km)[c.source] = c.value;
  }
  const offs = { launch: -5, reentry: 0, aviation: 5 };
  const marks = svg('g');
  for (const [km, vals] of byBin) {
    const yc = y(km + 5) + ROW / 2;
    for (const src of SOURCES) {
      const v = vals[src.id];
      if (!v) continue;
      const yy = yc + offs[src.id];
      marks.append(svg('line', { x1: x(v.low || lo), x2: x(v.high), y1: yy, y2: yy, class: `sp-whisk ${src.cls}` }));
      marks.append(svg('circle', { cx: x(v.central), cy: yy, r: 4, class: `sp-dot ${src.cls}` }));
    }
  }
  s.append(marks);

  // hover rows: the whole 5-km slice is the hit target, and the readout lists every source in it
  const kms = [...byBin.keys()].sort((a, b) => b - a);
  const hl = svg('rect', { x: M.l, width: iw, height: ROW, class: 'sp-rowhl', visibility: 'hidden' });
  s.insertBefore(hl, marks);
  const readout = km => {
    const vals = byBin.get(km) ?? {};
    return el('div', {},
      el('div', { class: 'sp-tip-sub' }, `${km}–${km + 5} km · ${SPECIES[species].long}`),
      ...SOURCES.filter(src => vals[src.id]).map(src => el('div', { class: 'sp-tip-row' },
        el('i', { class: `sp-linekey ${src.cls}` }),
        el('b', {}, mass(vals[src.id].central)), ' ', el('span', { class: 'muted' }, `${src.label} (${mass(vals[src.id].low)}–${mass(vals[src.id].high)})`))),
      el('div', { class: 'sp-tip-note' }, 'Tags and sources: table view below.'));
  };
  const show = (km, cx, cy) => { hl.setAttribute('y', y(km + 5)); hl.setAttribute('visibility', 'visible'); showTip(readout(km), cx, cy); };
  const clear = () => { hl.setAttribute('visibility', 'hidden'); hideTip(); };
  for (const km of kms) {
    const r = svg('rect', { x: M.l, y: y(km + 5), width: iw, height: ROW, class: 'sp-hit' });
    r.addEventListener('pointerenter', e => show(km, e.clientX, e.clientY));
    r.addEventListener('pointermove', e => show(km, e.clientX, e.clientY));
    r.addEventListener('pointerleave', clear);
    s.append(r);
  }
  // keyboard: focus the chart, then arrow keys step through the slices
  let k = -1;
  s.setAttribute('tabindex', '0');
  s.addEventListener('keydown', e => {
    if (!['ArrowUp', 'ArrowDown'].includes(e.key) || !kms.length) return;
    e.preventDefault();
    k = Math.max(0, Math.min(kms.length - 1, k + (e.key === 'ArrowDown' ? 1 : -1)));
    const b = s.getBoundingClientRect();
    show(kms[k], b.left + M.l + iw * 0.6, b.top + y(kms[k]));
  });
  s.addEventListener('focus', () => { if (k < 0 && kms.length) { k = 0; } const b = s.getBoundingClientRect(); show(kms[k], b.left + M.l + iw * 0.6, b.top + y(kms[k])); });
  s.addEventListener('blur', clear);
  node.append(s);
}

function drawTable(node, rows, species) {
  const bins = [...new Set(rows.map(c => c.lo_km))].sort((a, b) => b - a);
  const srcs = SOURCES.filter(s => rows.some(c => c.source === s.id));
  const val = (km, src) => rows.find(c => c.lo_km === km && c.source === src)?.value;
  node.replaceChildren(
    el('summary', {}, `Table view: ${SPECIES[species].long.toLowerCase()} by height`),
    el('div', { class: 'tablebox' }, el('table', { class: 'ledger sp-table' },
      el('thead', {}, el('tr', {}, el('th', {}, 'Height'), ...srcs.map(s => el('th', {}, s.label)))),
      el('tbody', {}, ...bins.map(km => el('tr', {}, el('td', {}, `${km}–${km + 5} km`),
        ...srcs.map(s => el('td', {}, valued(val(km, s.id), `${SPECIES[species].long}, ${s.label.toLowerCase()}, ${km}–${km + 5} km`))))))
    )));
}

