// Space ledger entry point, called once from main.js. Each part renders on its own, so a failure in one
// (or no data at all) leaves the rest of the page, and the contrail sections, working.
import { load } from './data.js';
import { el, setSources, citedSources, TIERS } from './format.js';
import { renderLayers } from './layers.js';
import { renderKpis, renderLedgers } from './ledgers.js';
import { renderTradeoff } from './tradeoff.js';

const $ = id => document.getElementById(id);
const FROM = {
  api: { badge: 'LIVE DATA', text: 'from the live API' },
  snapshot: { badge: 'OFFLINE SNAPSHOT', text: 'from the snapshot saved for offline use' },
  sample: { badge: 'SAMPLE DATA', text: 'illustrative sample values, not real data' }
};

function safe(node, what, fn) {
  if (!node) return;
  try { fn(); } catch (err) {
    console.error(`Space ledger: ${what} failed`, err);
    node.replaceChildren(el('p', { class: 'note' }, `The ${what} could not be drawn (${err.message}).`));
  }
}

function renderStatus(doc, from) {
  const f = FROM[from], sample = doc.sample || from === 'sample';
  const w = doc.window, built = doc.generated_at.slice(0, 16).replace('T', ' ');
  for (const node of document.querySelectorAll('[data-space-status]')) {
    node.replaceChildren(
      el('span', { class: `sp-badge${sample ? ' sp-badge-sample' : ''}` }, sample ? 'SAMPLE DATA' : f.badge),
      el('span', {}, ` ${w.days} days to ${w.end} · ${sample ? FROM.sample.text : f.text} · built ${built} UTC`));
  }
}

function renderTierKey(node) {
  node.replaceChildren(...Object.entries(TIERS).map(([tier, t]) =>
    el('span', { class: 'sp-key' }, el('span', { class: 'sp-tag', 'data-tier': tier, 'aria-hidden': 'true' }, t.letter), el('b', {}, t.word), ' ', el('span', { class: 'muted' }, t.what))));
}

function renderSources(node, doc) {
  const cited = citedSources(doc);
  const used = doc.sources.filter(s => cited.has(s.id) || ['ll2', 'celestrak', 'gcat'].includes(s.id));
  node.replaceChildren(el('ul', { class: 'sp-sources' }, ...used.map(s => el('li', {},
    s.url ? el('a', { href: s.url, rel: 'noopener', target: '_blank' }, s.name) : el('span', {}, s.name),
    el('span', { class: 'muted' }, [s.licence, s.retrieved_at ? `retrieved ${s.retrieved_at.slice(0, 10)}` : null].filter(Boolean).map(x => ` · ${x}`).join('')),
    s.citation ? el('div', { class: 'sp-sub' }, `Please cite: ${s.citation}`) : null))));
}

function renderSummary(doc, from) {
  setSources(doc.sources);
  renderStatus(doc, from);
  safe($('space-kpis'), 'summary figures', () => renderKpis($('space-kpis'), doc));
  safe($('sky-chart'), 'layers chart', () => renderLayers($('sky-chart'), doc));
  safe($('space-ledgers'), 'ledgers', () => renderLedgers($('space-ledgers'), doc));
  safe($('tradeoff-chart'), 'monthly chart', () => renderTradeoff($('tradeoff-chart'), doc));
  safe($('space-sources'), 'source list', () => renderSources($('space-sources'), doc));
}

export async function initSpace() {
  if (!$('space')) return;
  safe($('space-tiers'), 'tag key', () => renderTierKey($('space-tiers')));

  const summaryP = load('summary');
  const orbitsP = load('orbits');
  let summary;
  try {
    summary = await summaryP;
  } catch (err) {
    console.error('Space ledger: no data could be loaded', err);
    for (const node of document.querySelectorAll('[data-space-status]')) node.textContent = 'Space data could not be loaded.';
    return;
  }
  renderSummary(summary.doc, summary.from);

  // The globe needs the orbit file and satellite.js; load both without holding up the rest.
  const globeRoot = $('orbit-globe');
  if (globeRoot) {
    Promise.all([orbitsP, import('./globe.js')])
      .then(([orbits, mod]) => mod.renderGlobe(globeRoot, orbits.doc, summary.doc))
      .catch(err => {
        console.error('Space ledger: globe failed', err);
        globeRoot.replaceChildren(el('p', { class: 'note' }, `The globe could not be drawn (${err.message}). The falling objects are still listed in the ledgers.`));
      });
  }

  // If the API was slow rather than absent, swap in live figures when they arrive.
  summary.later?.then(live => {
    if (live?.doc) { summary = live; renderSummary(live.doc, 'api'); }
  });
}
