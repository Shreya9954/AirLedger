// Space ledgers: who launched what (Launch Library 2 providers) and whose hardware came down (GCAT owners).
// The two are deliberately separate tables; "SpaceX" the launch provider and "SPXS" the Starlink owner are
// different rows in different catalogues. Same table pattern as the airline ledger (js/ui/ledger.js).
import { el, num, tonnes, valued } from './format.js';

const ORDER = ['fact', 'estimate', 'research'];

// Sum Values the way the backend does: ranges add end to end, the least certain tier wins, sources unite.
export function vsum(vals) {
  const vs = vals.filter(Boolean);
  if (!vs.length) return null;
  const src = new Set();
  let tier = 'fact';
  for (const v of vs) {
    v.source.split('+').forEach(s => src.add(s));
    if (ORDER.indexOf(v.tier) > ORDER.indexOf(tier)) tier = v.tier;
  }
  const notes = new Set(vs.map(v => v.note || ''));
  return {
    central: vs.reduce((a, v) => a + v.central, 0), low: vs.reduce((a, v) => a + v.low, 0),
    high: vs.reduce((a, v) => a + v.high, 0), unit: 'kg', tier, source: [...src].sort().join('+'),
    note: notes.size === 1 ? [...notes][0] : ''
  };
}

function tile(label, value, sub) {
  return el('div', { class: 'sp-tile' }, el('div', { class: 'lbl' }, label), el('div', { class: 'sp-tile-v' }, value), sub ? el('div', { class: 'sp-tile-sub' }, sub) : null);
}

export function renderKpis(root, doc) {
  const cov = doc.coverage, L = doc.ledger;
  const prop = vsum(L.launch_providers.map(r => r.propellant));
  const reMass = vsum(L.reentry_owners.map(r => r.mass));
  const burned = vsum(L.reentry_owners.map(r => r.deposits.ablated_mass));
  const landed = doc.reentries.filter(r => r.landed).length;
  root.replaceChildren(
    tile('Launches', el('span', { class: 'sp-big' }, num(cov.launches)), `propellant known for ${cov.launches_with_data} of ${cov.launches}`),
    tile('Propellant burned', valued(prop, 'propellant burned by all launches in the window'), 'all heights, all launches with data'),
    tile('Re-entries', el('span', { class: 'sp-big' }, num(cov.reentries)), `mass known for ${cov.reentries_with_mass} of ${cov.reentries}` + (landed ? `; ${landed} landed intact, not counted` : '')),
    tile('Re-entered mass', valued(reMass, 'catalogued mass of everything that re-entered'), 'catalogued mass, not all of it burns up'),
    tile('Burned up', valued(burned, 'mass that vaporised or melted on re-entry'), 'the part that stays in the atmosphere'),
    tile('Falling now', el('span', { class: 'sp-big' }, num(cov.falling)), `on CelesTrak's decaying list; mass known for ${cov.falling_with_mass}`)
  );
}

// A sortable table. cols: {k, t, sort(row) -> number|string, cell(row) -> Node, bar?}
// Long tables show the first TOP rows and a button for the rest.
const TOP = 12;
function sortable(table, rows, cols, sortKey) {
  let all = rows.length <= TOP + 3;
  const more = el('button', { type: 'button', class: 'btn ghost sp-more', onclick: () => { all = !all; render(); } });
  (table.parentElement ?? table).after(more);
  function render() {
    const c0 = cols.find(c => c.k === sortKey);
    const rs = [...rows].sort((a, b) => {
      const x = c0.sort(a), y = c0.sort(b);
      return typeof x === 'string' ? x.localeCompare(y) : (y ?? -1) - (x ?? -1);
    });
    const max = {};
    for (const c of cols) if (c.bar) max[c.k] = Math.max(1e-9, ...rows.map(r => c.sort(r) ?? 0));
    table.replaceChildren(
      el('thead', {}, el('tr', {}, ...cols.map(c => el('th', { 'aria-sort': c.k === sortKey ? (c.k === 'name' ? 'ascending' : 'descending') : null },
        el('button', { type: 'button', onclick: () => { sortKey = c.k; render(); } }, c.t))))),
      el('tbody', {}, ...(all ? rs : rs.slice(0, TOP)).map(r => el('tr', {}, ...cols.map(c => {
        const cell = c.cell(r);
        if (!c.bar) return el('td', {}, cell);
        const w = Math.max(2, 70 * (c.sort(r) ?? 0) / max[c.k]);
        return el('td', {}, el('span', { class: 'barcell' }, c.sort(r) != null ? el('span', { class: `b ${c.bar}`, style: `width:${w}px` }) : null, cell));
      }))))
    );
    more.hidden = rows.length <= TOP + 3;
    more.textContent = all ? `Show the top ${TOP} only` : `Show all ${rows.length}`;
  }
  render();
}

const name2 = (main, sub) => el('span', {}, main, sub ? el('small', { class: 'sp-sub' }, sub) : null);
const t = (v, label) => valued(v, label, x => tonnes(x));

export function renderLedgers(root, doc) {
  const L = doc.ledger, cov = doc.coverage;
  const landed = doc.reentries.filter(r => r.landed);
  const provTable = el('table', { class: 'ledger sp-ledger' });
  const ownTable = el('table', { class: 'ledger sp-ledger' });

  root.replaceChildren(
    el('h3', { class: 'sp-h3' }, 'Launch providers'),
    el('p', { class: 'note' }, `Propellant known for ${cov.launches_with_data} of ${cov.launches} launches that flew in the window. Propellant is the total burned at all heights; soot, alumina and chlorine are what is left below 120 km. Tonnes.`),
    el('div', { class: 'tablebox' }, provTable),
    el('h3', { class: 'sp-h3' }, 'Owners of re-entering hardware'),
    el('p', { class: 'note' }, `Mass known for ${cov.reentries_with_mass} of ${cov.reentries} re-entries. Re-entered mass is the catalogued mass of what came down; burned up is the part that vaporised or melted in the air. Tonnes.` +
      (landed.length ? ` ${landed.length} crew or cargo capsule${landed.length > 1 ? 's' : ''} landed intact and ${landed.length > 1 ? 'are' : 'is'} not counted here (see the full list below).` : '')),
    el('div', { class: 'tablebox' }, ownTable),
    itemLists(doc)
  );

  sortable(provTable, L.launch_providers, [
    { k: 'name', t: 'Provider', sort: r => r.provider, cell: r => name2(r.provider, r.country) },
    { k: 'n', t: 'Launches', sort: r => r.launches, cell: r => name2(num(r.launches), r.launches_with_data < r.launches ? `data for ${r.launches_with_data}` : null) },
    { k: 'prop', t: 'Propellant', bar: 'sp-launch', sort: r => r.propellant?.central, cell: r => t(r.propellant, `propellant burned by ${r.provider}`) },
    { k: 'bc', t: 'Soot', sort: r => r.deposits.black_carbon?.central, cell: r => t(r.deposits.black_carbon, `soot below 120 km from ${r.provider}`) },
    { k: 'al2o3', t: 'Alumina', sort: r => r.deposits.alumina?.central, cell: r => t(r.deposits.alumina, `alumina from ${r.provider}`) },
    { k: 'cl', t: 'Chlorine', sort: r => r.deposits.chlorine?.central, cell: r => t(r.deposits.chlorine, `chlorine from ${r.provider}`) }
  ], 'prop');

  sortable(ownTable, L.reentry_owners, [
    { k: 'name', t: 'Owner', sort: r => r.operator, cell: r => name2(r.operator, [r.operator_code, r.country].filter(Boolean).join(' · ')) },
    { k: 'n', t: 'Re-entries', sort: r => r.reentries, cell: r => name2(num(r.reentries), r.reentries_with_mass < r.reentries ? `mass known for ${r.reentries_with_mass}` : null) },
    { k: 'mass', t: 'Re-entered mass', bar: 'sp-reentry', sort: r => r.mass?.central, cell: r => t(r.mass, `re-entered mass, ${r.operator}`) },
    { k: 'abl', t: 'Burned up', sort: r => r.deposits.ablated_mass?.central, cell: r => t(r.deposits.ablated_mass, `burned-up mass, ${r.operator}`) },
    { k: 'al', t: 'Aluminium', sort: r => r.deposits.aluminium?.central, cell: r => t(r.deposits.aluminium, `aluminium in the burned-up mass, ${r.operator}`) }
  ], 'mass');
}

const STATUS = { success: 'Success', failure: 'Failure', partial: 'Partial failure', upcoming: 'Upcoming' };

function itemLists(doc) {
  const launches = el('table', { class: 'ledger sp-items' },
    el('thead', {}, el('tr', {}, ...['Date (UTC)', 'Launch', 'Provider', 'Status', 'Propellant, t', 'Pad'].map(h => el('th', {}, h)))),
    el('tbody', {}, ...doc.launches.map(x => el('tr', {},
      el('td', {}, x.net.slice(0, 10)),
      el('td', {}, name2(x.name, x.vehicle)),
      el('td', {}, x.provider),
      el('td', {}, el('span', { class: `pill sp-status-${x.status}` }, STATUS[x.status] ?? x.status)),
      el('td', {}, t(x.propellant, `propellant, ${x.name}`)),
      el('td', {}, x.pad?.location ?? '–')))));
  const reentries = el('table', { class: 'ledger sp-items' },
    el('thead', {}, el('tr', {}, ...['Re-entered (UTC)', 'Object', 'Type', 'Owner', 'Re-entered mass, t', 'Burned up, t'].map(h => el('th', {}, h)))),
    el('tbody', {}, ...doc.reentries.map(r => el('tr', { class: r.landed ? 'sp-landed' : null },
      el('td', {}, r.decay_date),
      el('td', {}, name2(el('span', {}, r.name, r.landed ? el('span', { class: 'pill sp-landed-pill' }, 'Landed') : null), r.cospar)),
      el('td', {}, r.type),
      el('td', {}, name2(r.operator, r.operator_code)),
      el('td', {}, t(r.mass, `re-entered mass, ${r.name}`)),
      el('td', {}, r.landed ? el('span', { class: 'muted' }, 'landed intact') : t(r.deposits.ablated_mass, `burned-up mass, ${r.name}`))))));
  const past = doc.launches.filter(x => x.status !== 'upcoming').length;
  return el('div', { class: 'sp-lists' },
    el('details', { class: 'sp-tableview' }, el('summary', {}, `All ${doc.launches.length} launches (${past} flown, ${doc.launches.length - past} upcoming), newest first`), el('div', { class: 'tablebox' }, launches)),
    el('details', { class: 'sp-tableview' }, el('summary', {}, `All ${doc.reentries.length} re-entries, newest first`), el('div', { class: 'tablebox' }, reentries)));
}

