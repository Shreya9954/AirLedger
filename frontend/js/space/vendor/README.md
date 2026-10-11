# Vendored libraries

Kept in the repo so the space ledger works offline (the demo runs without Wi-Fi).

| File | Library | Version | From | Licence |
|---|---|---|---|---|
| `satellite.es.js` | satellite.js (SGP4 propagation; `json2satrec` reads CelesTrak OMM JSON, so 6-digit catalogue numbers work) | 6.0.1, unmodified | https://unpkg.com/satellite.js@6.0.1/dist/satellite.es.js | MIT, see `satellite.js-LICENSE.md` |

`../land-110m.json` holds the coastlines drawn on the globe: Natural Earth 1:110m land (public domain), from world-atlas 2.0.2 (`land-110m.json`), decoded from TopoJSON into plain [lon, lat] rings at 0.1° precision.
