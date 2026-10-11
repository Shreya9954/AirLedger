// The trade-off panel: catalogued mass re-entering each month since 2015 (GCAT end-of-life masses, landed
// capsules excluded), next to why it is rising. Single series, so no legend box; the heading names it.
import { el, svg, mass, num, showTip, hideTip, valued } from './format.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const M = { l: 46, r: 10, t: 12, b: 26 }, PH = 200;
const label = m => `${MONTHS[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}`;

export function renderTradeoff(root, doc) {
  const months = doc.monthly;
  root.replaceChildren();
  if (!months.length) { root.append(el('p', { class: 'note' }, 'No monthly series in this dataset.')); return; }
  const chart = el('div', { class: 'sp-monthly' });
  const years = annual(months, doc.window.end);
  const ship = doc.reentries.filter(r => /^STARSHIP/i.test(r.name) && r.mass).sort((a, b) => b.mass.central - a.mass.central)[0];
  root.append(
    el('div', { class: 'sp-chart-title' }, el('b', {}, 'Catalogued mass re-entering per month, tonnes'),
      el('span', { class: 'muted' }, ` · ${label(months[0].month)} to ${label(months.at(-1).month)} (to date) · landed capsules excluded`)),
    chart,
    el('div', { class: 'sp-years', role: 'list', 'aria-label': 'Re-entered mass per year' },
      ...years.map(y => el('span', { role: 'listitem' }, el('span', { class: 'lbl' }, y.year + (y.partial ? ' to date' : '')), ' ', el('b', { class: 'mono' }, mass(y.mass))))),
    el('p', { class: 'note' }, `Re-entered mass is what the catalogue says came down (dry mass for spent stages), a Fact. It is not all burned up: the totals include Starship upper stages, which are built to survive${ship ? ` (${ship.name}, ${mass(ship.mass.central)}, came down on ${ship.decay_date})` : ''}, and rocket bodies that partly reach the ground. Burned-up estimates are in the ledgers above. Objects without a catalogued mass count as unknown.`),
    tableView(months)
  );
  let width = 0;
  new ResizeObserver(entries => {
    const w = Math.round(entries[0].contentRect.width);
    if (w && Math.abs(w - width) > 4) { width = w; requestAnimationFrame(() => draw(chart, months, width)); }
  }).observe(chart);
  draw(chart, months, chart.clientWidth || 640);
}

function annual(months, end) {
  const by = new Map();
  for (const m of months) {
    const y = m.month.slice(0, 4);
    by.set(y, (by.get(y) ?? 0) + (m.reentered_mass?.central ?? 0));
  }
  return [...by].map(([year, mass]) => ({ year, mass, partial: year === end.slice(0, 4) && end.slice(5) !== '12-31' }));
}

function niceStep(max, ticks = 4) {
  const raw = max / ticks, p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map(k => k * p).find(s => s >= raw);
}

function draw(node, months, W) {
  node.replaceChildren();
  const H = M.t + PH + M.b, iw = W - M.l - M.r, n = months.length;
  const vals = months.map(m => (m.reentered_mass?.central ?? 0) / 1000);
  const step = niceStep(Math.max(...vals, 1)), top = Math.ceil(Math.max(...vals, 1) / step) * step;
  const slot = iw / n, gap = slot >= 5 ? 2 : slot >= 2.5 ? 1 : 0, bw = Math.min(24, Math.max(1, slot - gap));
  const x = i => M.l + i * slot + (slot - bw) / 2, y = v => M.t + PH - (v / top) * PH;

  const s = svg('svg', { class: 'sp-svg', width: W, height: H, viewBox: `0 0 ${W} ${H}`, tabindex: '0', role: 'img',
    'aria-label': `Column chart of re-entered mass per month from ${label(months[0].month)} to ${label(months.at(-1).month)}. Focus and use the left and right arrow keys to read each month, or open the table view.` });
  for (let v = 0; v <= top + 1e-9; v += step) {
    s.append(svg('line', { x1: M.l, x2: M.l + iw, y1: y(v), y2: y(v), class: v ? 'sp-grid' : 'sp-axis' }));
    const t = svg('text', { x: M.l - 6, y: y(v) + 4, 'text-anchor': 'end', class: 'sp-tick' });
    t.textContent = v ? num(v) + ' t' : '0';
    s.append(t);
  }
  const yearEvery = slot * 12 < 34 ? 2 : 1;
  months.forEach((m, i) => {
    if (m.month.endsWith('-01') && (+m.month.slice(0, 4)) % yearEvery === 0) {
      const t = svg('text', { x: M.l + i * slot, y: M.t + PH + 17, class: 'sp-tick' });
      t.textContent = m.month.slice(0, 4);
      s.append(t);
      s.append(svg('line', { x1: M.l + i * slot, x2: M.l + i * slot, y1: M.t + PH, y2: M.t + PH + 4, class: 'sp-axis' }));
    }
  });
  const r = Math.min(4, bw / 2);
  vals.forEach((v, i) => {
    if (!v) return;
    const h = Math.max(1, y(0) - y(v)), x0 = x(i), y0 = y(0) - h, rr = Math.min(r, h);
    // rounded data end, square at the baseline
    s.append(svg('path', { class: 'sp-col sp-reentry', d: `M${x0},${y0 + h}V${y0 + rr}Q${x0},${y0} ${x0 + rr},${y0}H${x0 + bw - rr}Q${x0 + bw},${y0} ${x0 + bw},${y0 + rr}V${y0 + h}Z` }));
  });
  // label the largest month only
  const imax = vals.indexOf(Math.max(...vals));
  const lt = svg('text', { x: Math.min(x(imax) + bw / 2, M.l + iw - 2), y: y(vals[imax]) - 5, 'text-anchor': x(imax) > M.l + iw - 80 ? 'end' : 'middle', class: 'sp-dlabel' });
  lt.textContent = `${label(months[imax].month)}: ${num(vals[imax])} t`;
  s.append(lt);

  // crosshair snapping to the nearest month
  const cross = svg('line', { y1: M.t, y2: M.t + PH, class: 'sp-cross', visibility: 'hidden' });
  s.append(cross);
  const readout = i => {
    const m = months[i];
    return el('div', {},
      el('div', { class: 'sp-tip-sub' }, label(m.month) + (i === n - 1 ? ' (to date)' : '')),
      el('div', { class: 'sp-tip-row' }, el('i', { class: 'sp-linekey sp-reentry' }), el('b', {}, m.reentered_mass ? mass(m.reentered_mass.central) : 'mass unknown'), ' ', el('span', { class: 'muted' }, 're-entered (Fact, GCAT)')),
      el('div', { class: 'sp-tip-note' }, `${m.reentries} re-entries, mass known for ${m.reentries_with_mass}`),
      el('div', { class: 'sp-tip-note' }, `${m.launches} launches that reached orbit (distinct international designators)`));
  };
  const at = i => { cross.setAttribute('x1', x(i) + bw / 2); cross.setAttribute('x2', x(i) + bw / 2); cross.setAttribute('visibility', 'visible'); };
  const hit = svg('rect', { x: M.l, y: M.t, width: iw, height: PH, class: 'sp-hit' });
  const idx = e => { const b = s.getBoundingClientRect(); return Math.max(0, Math.min(n - 1, Math.floor((e.clientX - b.left - M.l) / slot))); };
  hit.addEventListener('pointermove', e => { const i = idx(e); at(i); showTip(readout(i), e.clientX, e.clientY); });
  hit.addEventListener('pointerleave', () => { cross.setAttribute('visibility', 'hidden'); hideTip(); });
  s.append(hit);
  let k = n - 1;
  const kb = () => { at(k); const b = s.getBoundingClientRect(); showTip(readout(k), b.left + x(k), b.top + M.t + 20); };
  s.addEventListener('focus', kb);
  s.addEventListener('blur', () => { cross.setAttribute('visibility', 'hidden'); hideTip(); });
  s.addEventListener('keydown', e => {
    const d = { ArrowLeft: -1, ArrowRight: 1, PageUp: -12, PageDown: 12, Home: -1e9, End: 1e9 }[e.key];
    if (d == null) return;
    e.preventDefault();
    k = Math.max(0, Math.min(n - 1, k + d));
    kb();
  });
  node.append(s);
}

function tableView(months) {
  return el('details', { class: 'sp-tableview' },
    el('summary', {}, 'Table view: every month'),
    el('div', { class: 'tablebox sp-scrollbox' }, el('table', { class: 'ledger sp-table' },
      el('thead', {}, el('tr', {}, ...['Month', 'Re-entered mass', 'Re-entries', 'Mass known', 'Launches'].map(h => el('th', {}, h)))),
      el('tbody', {}, ...[...months].reverse().map(m => el('tr', {},
        el('td', {}, label(m.month)), el('td', {}, valued(m.reentered_mass, `re-entered mass, ${label(m.month)}`)),
        el('td', {}, num(m.reentries)), el('td', {}, num(m.reentries_with_mass)), el('td', {}, num(m.launches))))))));
}
