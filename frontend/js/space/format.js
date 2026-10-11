// Shared pieces for the space ledger: a tiny DOM builder (catalogue names are data, so text always goes in
// through textContent), mass formatting, the Fact / Estimate / Research tag, and one shared tooltip.

export function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) n.append(kid instanceof Node ? kid : String(kid));
  return n;
}

export const SVG_NS = 'http://www.w3.org/2000/svg';
export function svg(tag, attrs = {}) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  return n;
}

const nf = (d) => new Intl.NumberFormat('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });
const trim = s => s.replace(/\.0(?=\D*$)/, '');   // "10.0" -> "10"
export const num = (x, d = 0) => nf(d).format(x);

// A mass in kg as a short string in a sensible unit.
export function mass(kg) {
  if (kg == null) return '–';
  const a = Math.abs(kg);
  if (a >= 1e9) return trim(num(kg / 1e9, a >= 1e10 ? 0 : 1)) + ' Mt';
  if (a >= 1e6) return trim(num(kg / 1e6, a >= 1e7 ? 0 : 1)) + ' kt';
  if (a >= 1e3) return trim(num(kg / 1e3, a >= 1e5 ? 0 : 1)) + ' t';
  if (a >= 1) return num(kg, 0) + ' kg';
  return a ? num(kg, 2) + ' kg' : '0';
}
// Tonnes for table columns (one unit per column so they line up).
export const tonnes = (kg) => (kg == null ? '–' : kg === 0 ? '0' : kg < 50 ? '<0.1' : num(kg / 1000, kg >= 1e6 ? 0 : 1));

export const TIERS = {
  fact: { letter: 'F', word: 'Fact', what: 'Taken directly from a catalogue.' },
  estimate: { letter: 'E', word: 'Estimate', what: 'Arithmetic on catalogue facts plus engineering data, with stated assumptions.' },
  research: { letter: 'R', word: 'Research', what: 'Depends on emission factors that scientists are still measuring.' }
};

// Source id -> {name, url}; filled from the summary's `sources` list by setSources().
let SRC = new Map();
export function setSources(list) { SRC = new Map(list.map(s => [s.id, s])); }
export const sourceName = (id) => SRC.get(id)?.name ?? id;

// Every source id a document cites, so the credits list only shows those.
export function citedSources(doc) {
  const ids = new Set();
  const walk = (x) => {
    if (Array.isArray(x)) x.forEach(walk);
    else if (x && typeof x === 'object') {
      if (typeof x.tier === 'string' && typeof x.source === 'string') x.source.split('+').forEach(t => ids.add(t));
      else Object.values(x).forEach(walk);
    }
  };
  walk(doc);
  return ids;
}

function describe(v, label) {
  const t = TIERS[v.tier] ?? TIERS.estimate;
  const range = v.low === v.high ? mass(v.central) : `${mass(v.low)} to ${mass(v.high)} (central ${mass(v.central)})`;
  const srcs = v.source.split('+').map(sourceName);
  return { t, range, srcs, label };
}

// The small badge after a number. Focusable, so keyboard users get the same tooltip as mouse users.
export function tag(v, label = '') {
  if (!v) return null;
  const d = describe(v, label);
  const b = el('span', {
    class: 'sp-tag', 'data-tier': v.tier, tabindex: '0', role: 'img',
    'aria-label': `${d.t.word}${label ? ' for ' + label : ''}: ${d.range}. Source: ${d.srcs.join('; ')}.${v.note ? ' ' + v.note : ''}`
  }, d.t.letter);
  bindTip(b, () => tipFor(v, label));
  return b;
}

// A value with its tag: "484 t [E]".
export function valued(v, label, fmt = mass) {
  if (!v) return el('span', { class: 'sp-none', title: 'Not known' }, '–');
  return el('span', { class: 'sp-val' }, el('span', { class: 'mono' }, fmt(v.central)), tag(v, label));
}

export function tipFor(v, label) {
  const d = describe(v, label);
  return el('div', {},
    el('div', { class: 'sp-tip-h' }, el('b', {}, d.range)),
    label ? el('div', { class: 'sp-tip-sub' }, label) : null,
    el('div', { class: 'sp-tip-tier', 'data-tier': v.tier }, el('span', { class: 'sp-tag', 'data-tier': v.tier }, d.t.letter), ' ', d.t.word, ': ', d.t.what),
    v.note ? el('div', { class: 'sp-tip-note' }, v.note) : null,
    el('div', { class: 'sp-tip-src' }, 'Source: ', d.srcs.join('; '))
  );
}

// ---------------------------------------------------------------- one shared tooltip

let tipEl = null, anchor = null, anchorMake = null;   // anchor: the focused element the tip belongs to
function tipNode() {
  if (!tipEl) {
    tipEl = el('div', { class: 'sp-tip', role: 'tooltip', id: 'sp-tip', hidden: true });
    document.body.append(tipEl);
  }
  return tipEl;
}

export function showTip(content, x, y) {
  const t = tipNode();
  t.replaceChildren(content);
  t.hidden = false;
  const pad = 12, w = t.offsetWidth, h = t.offsetHeight;
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  let left = x + pad, top = y + pad;
  if (left + w > vw - 8) left = Math.max(8, x - w - pad);
  if (top + h > vh - 8) top = Math.max(8, y - h - pad);
  t.style.left = left + 'px';
  t.style.top = top + 'px';
}
export function hideTip() { if (tipEl) tipEl.hidden = true; anchor = null; }

export function bindTip(node, make) {
  node.addEventListener('pointerenter', e => showTip(make(), e.clientX, e.clientY));
  node.addEventListener('pointermove', e => { if (tipEl && !tipEl.hidden) showTip(make(), e.clientX, e.clientY); });
  node.addEventListener('pointerleave', hideTip);
  node.addEventListener('focus', () => { anchor = node; anchorMake = make; place(); });
  node.addEventListener('blur', hideTip);
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideTip(); });
function place() { const r = anchor.getBoundingClientRect(); showTip(anchorMake(), r.right, r.bottom); }
// Tabbing scrolls the page, so a keyboard tip follows its element; a pointer tip just closes.
window.addEventListener('scroll', () => { if (anchor && document.activeElement === anchor) place(); else hideTip(); }, { passive: true });
