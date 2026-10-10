// Simulated North Atlantic traffic for one night. Carriers are fictional.
import { CARRIERS, TYPES, N } from '../config.js';
import { AIRPORTS } from '../geo.js';
import { rng, hav, gc } from '../util.js';
import { evalTrack, rerouteOptions } from '../model.js';

const EAST = [['JFK','LHR'],['JFK','CDG'],['BOS','DUB'],['YUL','CDG'],['EWR','AMS'],['IAD','FRA'],['YYZ','MAD'],['PHL','MAN'],['ORD','LHR'],['BOS','KEF'],['JFK','LIS'],['MIA','LHR'],['YYZ','FRA'],['EWR','DUB']];
const WEST = [['LHR','JFK'],['CDG','YUL'],['AMS','EWR'],['FRA','IAD'],['DUB','BOS'],['MAD','YYZ'],['LHR','BOS']];

export function simFleet(atmos, startHour, seed = 20261010, count = 60) {
  const R = rng(seed), rr = (a, b) => a + (b - a) * R(), pick = a => a[Math.floor(R() * a.length)];
  const flights = [];
  for (let k = 0; k < count; k++) {
    const east = k % 3 !== 2;
    const [o, d] = east ? EAST[k % EAST.length] : WEST[k % WEST.length];
    const a = AIRPORTS[o], b = AIRPORTS[d], dist = hav(a, b);
    const cargo = R() < 0.12;
    const carrier = cargo ? CARRIERS[4] : CARRIERS[Math.floor(R() * 4)];
    const type = cargo ? 'B763F' : (dist < 5700 && R() < 0.4 ? pick(['B38M', 'A21N']) : pick(['B77W', 'A359', 'B789', 'A333', 'B77W']));
    // Semicircular rule: eastbound odd flight levels, westbound even.
    let fl = pick(east ? [310, 330, 350, 350, 370, 370, 390] : [320, 340, 360, 360, 380, 380, 400]);
    if (fl > TYPES[type].ceil) fl = TYPES[type].ceil - (east ? 20 : 10);
    const dur = dist / 870 + 0.4;
    const dep = east ? rr(-1.5, 4.5) : rr(4, 9.5);
    const pts = [], seg = [];
    for (let i = 0; i < N; i++) { const p = gc(a, b, i / (N - 1)); pts.push([p[0], p[1], dep + 0.2 + (i / (N - 1)) * (dur - 0.4)]); }
    for (let i = 0; i < N - 1; i++) seg.push(hav(pts[i], pts[i + 1]));
    seg.push(0);
    const f = {
      id: k, cs: carrier.code + (100 + Math.floor(R() * 890)), carrier, type, o, d, dist, dur, dep, arr: dep + dur,
      fl, pts, seg, fuel: TYPES[type].burn * dur
    };
    f.base = evalTrack(atmos, f, () => f.fl, startHour);
    f.opts = rerouteOptions(atmos, f, startHour);
    flights.push(f);
  }
  return flights;
}
