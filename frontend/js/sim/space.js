// Illustrative launch and re-entry events. Scores are placeholders, not peer-reviewed factors.
// Mirrors backend/app/space_events.py.
export const SPACE_EVENTS = [
  { kind: 'launch', name: 'Falcon 9 launch', note: 'Kerosene engine, Cape Canaveral, north-east ascent', t: 3.4,
    path: [[-80.6, 28.5], [-77, 31.5], [-70, 36], [-60, 40.5]], c: 2400, lo: 700, hi: 9000,
    why: 'Fuel CO₂ is about 430 t. Most of the estimate is black carbon left in the stratosphere, where it absorbs sunlight for years. Factor not yet peer-reviewed.' },
  { kind: 'reentry', name: 'Satellite re-entry', note: 'Broadband satellite, ~800 kg, burns up', t: 1.8,
    path: [[-46, 50], [-38, 47.5], [-28, 44.5]], c: 6, lo: 1, hi: 40,
    why: 'Main concern is aluminium oxide and ozone loss, not warming. Warming term is poorly constrained.' },
  { kind: 'reentry', name: 'Upper-stage re-entry', note: 'Uncontrolled spent stage', t: 6.2,
    path: [[-34, 59], [-23, 56], [-12, 52.5]], c: 25, lo: 4, hi: 150,
    why: 'Heavier than a satellite, so more metal vapour and alumina. Ablation products are rarely measured.' },
  { kind: 'launch', name: 'Methane rocket launch', note: 'Methalox engine, Cape Canaveral', t: 9.1,
    path: [[-80.6, 28.5], [-78, 31], [-72, 34.5], [-64, 37.5]], c: 600, lo: 200, hi: 2500,
    why: 'Methane burns cleaner than kerosene, so far less soot reaches the stratosphere.' },
  { kind: 'reentry', name: 'Satellite re-entry', note: 'Broadband satellite, ~800 kg', t: 8.4,
    path: [[-58, 61], [-49, 58], [-41, 55]], c: 6, lo: 1, hi: 40,
    why: 'Same assumptions as the earlier re-entry.' }
];
