// Loads the space ledger (Contract 2 in SPACE_HANDOFF.md): the live API first, then the committed offline
// snapshot, then the illustrative sample. The API can take a while on a cold start (it parses the full
// catalogues), so if it is merely slow we show the snapshot and swap in live data when it arrives.

const SOURCES = {
  summary: { api: '/api/space/summary?days=90', snapshot: 'data/space-snapshot.json', sample: 'data/space-sample.json' },
  orbits: { api: '/api/space/orbits?limit=3000', snapshot: 'data/space-orbits.json', sample: 'data/space-orbits-sample.json' }
};
const FAST_MS = 6000, SLOW_MS = 120000;

async function fetchJSON(url, signal) {
  const res = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function check(doc, schema) {
  if (!doc || doc.schema !== schema) throw new Error(`expected ${schema}, got ${doc && doc.schema}`);
  return doc;
}

async function local(kind, schema) {
  const s = SOURCES[kind];
  try {
    return { doc: check(await fetchJSON(s.snapshot), schema), from: 'snapshot' };
  } catch (err) {
    console.info(`Space ${kind}: no snapshot (${err.message}), using the sample.`);
    return { doc: check(await fetchJSON(s.sample), schema), from: 'sample' };
  }
}

// Resolves to { doc, from: 'api'|'snapshot'|'sample', later: Promise<{doc, from}>|null }.
// `later` is set when the API was slow rather than absent; it resolves if live data arrives.
export async function load(kind) {
  const schema = kind === 'summary' ? 'space-summary/1' : 'space-orbits/1';
  const ctl = new AbortController();
  const api = fetchJSON(SOURCES[kind].api, ctl.signal).then(doc => ({ doc: check(doc, schema), from: 'api' }));
  const killer = setTimeout(() => ctl.abort(), SLOW_MS);
  api.finally(() => clearTimeout(killer)).catch(() => {});
  let slow = false;
  const first = await Promise.race([
    api.catch(err => ({ err })),
    new Promise(r => setTimeout(() => { slow = true; r({ err: new Error('slow') }); }, FAST_MS))
  ]);
  if (first.doc) return { ...first, later: null };
  if (!slow) console.info(`Space ${kind}: API unavailable (${first.err.message}), using offline data.`);
  const fallback = await local(kind, schema);
  return { ...fallback, later: slow ? api.catch(() => null) : null };
}
