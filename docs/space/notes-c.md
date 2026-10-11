# Role C notes

Status, decisions, open questions and cross-role requests (`REQUEST(owner): ...`). See SPACE_HANDOFF.md.

## Status (2026-10-11)

**Done.** All five parts render from the live API, the offline snapshot and the sample:
- the layers of the sky chart
- the globe
- the two ledgers
- the trade-off panel
- Fact/Estimate/Research tags on every number

**Checked in headless Chrome:**
- Light and dark themes at 1280 px; dark at 390 px phone width.
- No horizontal page scroll and no console errors in any of the three data modes.
- Tooltips work on hover and on keyboard focus.

**Real backend:** run with `uvicorn app.main:app`, the page shows "LIVE DATA" with 73 of 75 launches covered, and both API responses pass `validate_summary` / `validate_orbits`.

**Files**
- `frontend/js/space/`:
  - `index.js`: entry point; renders each part in isolation.
  - `data.js`: loads API → snapshot → sample.
  - `format.js`: DOM builder, units, tags, tooltip.
  - `layers.js`, `globe.js`, `ledgers.js`, `tradeoff.js`.
  - `land-110m.json`: coastlines.
  - `vendor/`: satellite.js 6.0.1 with its licence and a README.
- `frontend/css/space.css`.
- **`frontend/index.html`:** stylesheet link, one nav link ("Space ledger"), five new sections between "Cloud or contrail" and "Data", and a sub-nav inside the first one.
- **`frontend/js/main.js`:** one line, a dynamic `import('./space/index.js')`. It runs before the scenario loads, and any failure is caught, so the contrail sections can't be broken by the space code.

## Decisions

- **Globe is drawn on a 2D canvas (orthographic projection), not globe.gl/three.js.**
  - The demo must work offline: a CDN library or Earth texture would vanish without Wi-Fi.
  - It also matches the canvas look and theme tokens of the contrail map.
  - satellite.js 6.0.1 is vendored, not loaded from a CDN, for the same reason. `json2satrec` exists in that version and reads CelesTrak OMM directly, so 6-digit catalogue numbers work. Pinned version and source URL are in `vendor/README.md`.
  - Coastlines are Natural Earth 1:110m (public domain) from world-atlas 2.0.2, decoded to plain rings.
- **What the globe draws and how it runs:**
  - Objects up to 1,500 km are drawn at their true height; higher orbits (GPS, geostationary) are left off and counted in a note.
  - While playing, time runs 60 times faster than real time. Each object is propagated once per simulated minute and interpolated in between.
  - It animates only while on screen, and starts paused if the viewer prefers reduced motion.
- **Layers chart:**
  - Mass axis is logarithmic, because aviation and a single re-entry differ by six or more orders of magnitude.
  - Each value is a dot (central estimate) on a line (low to high range), not a bar, since bar length on a log axis misleads.
  - One substance at a time, as the handoff asks.
  - Each 5-km row is the hover target, and its readout lists every source at that height. Arrow keys step through rows when the chart is focused.
  - A table view sits underneath.
- **Series colours** are dataviz palette slots 1–3 (aviation blue, launch orange, re-entry aqua), validated as a set against this page's `--paper` in both themes. They pass every check. The light-mode contrast warning is covered by direct labels, legend totals and table views.
- **Tags:** F, E or R, told apart by fill and border style, not colour alone. Each tag is focusable and has an aria-label giving the range and source.
- **Ledgers:** both tables follow `js/ui/ledger.js` (sortable header buttons, `aria-sort`, bar cell). Each long table shows its top 12 rows with a "Show all" button, and full launch and re-entry lists sit in collapsible sections. Landed capsules are labelled "Landed" and shown as "landed intact" in the burned-up column. Coverage is stated as "mass known for N of M".
- **Data loading:** if the API is slow rather than absent (a cold build parses about 25 MB), the snapshot shows after 6 s and live data replaces it when it arrives, within 120 s.
- **Sources list:** shows only the sources the data actually cites (B's `references()` lists every vehicle article in the table), plus GCAT's requested citation.
- **Requests from A's notes, all done:**
  - "re-entered mass" wording, with burned-up taken from `deposits.ablated_mass`
  - the landed label
  - "mass known for N of M"
  - the launch definition in the monthly tooltip ("launches that reached orbit, distinct international designators")

## Open points for integration

- **The snapshot still has the stub numbers.** Until A reruns `python -m app.space.snapshot`, the offline page shows "–" for propellant and burn-up, and "No altitude data in this dataset yet" for the layers chart. Everything works; the numbers just aren't there.
- **The caveat at the top of the Data section is now wrong for the space sections.** It says "Everything on this page is simulated." That section isn't mine to edit. Suggested wording for whoever updates it at integration: "The contrail map, flights and carriers are simulated. The space ledger uses real catalogue data (see its sources)."
- **The header nav had room for only one new link** without scrolling on desktop Windows. The four space sub-sections are linked from inside the "Space ledger" section instead.
- **The monthly re-entered mass includes Starship upper stages** (STARSHIP-14, 120 t, in September 2026), so that month spikes. The panel says so in the note under the chart. If A wants, a future optional `monthly[].starship_mass` key would let the chart show it separately. Not requested; it's a contract change.
