"""Score the rule-based classifier on real OpenContrails records.

For each record: the human-labelled contrail mask gives regions that should be called contrails;
thin ice cloud found by the split-window test (BT11 − BT12 > 1 K, i.e. dark blue in ash false
colour) outside those labels gives regions that should not. Each region goes through
shape_features() and classify(); OpenContrails has no flight tracks, so only the shape cue applies.

    python -m ml.evaluate /path/to/opencontrails/validation [--limit 200]

Prints how many labelled contrails the rule recognises and how many other ice-cloud regions it
wrongly calls contrails.
"""
from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

import numpy as np

from ml.opencontrails import LABELED_FRAME, ash_rgb, mask, records
from ml.shape_features import classify, shape_features

MIN_REGION_PX = 10
ICE_RED_MAX = 0.5  # ash red = norm(BT12 − BT11, −4, 2): below 0.5 means BT11 − BT12 > 1 K


def regions(m: np.ndarray, min_px: int = MIN_REGION_PX) -> list[np.ndarray]:
    """8-connected regions of a boolean mask, as boolean masks, smallest dropped."""
    seen = np.zeros_like(m, dtype=bool)
    h, w = m.shape
    out = []
    for y0, x0 in zip(*np.nonzero(m)):
        if seen[y0, x0]:
            continue
        comp, q = [], deque([(y0, x0)])
        seen[y0, x0] = True
        while q:
            y, x = q.popleft()
            comp.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
        if len(comp) >= min_px:
            r = np.zeros_like(m, dtype=bool)
            ys, xs = zip(*comp)
            r[list(ys), list(xs)] = True
            out.append(r)
    return out


def _grow(m: np.ndarray, px: int = 2) -> np.ndarray:
    g = m.copy()
    for _ in range(px):
        g[1:] |= g[:-1].copy(); g[:-1] |= g[1:].copy(); g[:, 1:] |= g[:, :-1].copy(); g[:, :-1] |= g[:, 1:].copy()
    return g


def evaluate_record(record: Path, frame: int = LABELED_FRAME) -> dict[str, int]:
    labels = mask(record)
    ice = ash_rgb(record, frame)[..., 0] < ICE_RED_MAX
    is_contrail = lambda r: classify(shape_features(r).linearity, None).startswith("Contrail")  # noqa: E731
    contrails = regions(labels)
    others = regions(ice & ~_grow(labels))
    return {
        "contrails": len(contrails),
        "contrails_recognised": sum(is_contrail(r) for r in contrails),
        "other_ice": len(others),
        "other_ice_called_contrail": sum(is_contrail(r) for r in others),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", type=Path, help="folder of OpenContrails records (one subfolder per record)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N records")
    args = ap.parse_args(argv)
    recs = records(args.root)[: args.limit or None]
    if not recs:
        print(f"no OpenContrails records found in {args.root}")
        return 1
    total = {"contrails": 0, "contrails_recognised": 0, "other_ice": 0, "other_ice_called_contrail": 0}
    for rec in recs:
        for k, v in evaluate_record(rec).items():
            total[k] += v
    rec_pct = 100 * total["contrails_recognised"] / max(1, total["contrails"])
    fp_pct = 100 * total["other_ice_called_contrail"] / max(1, total["other_ice"])
    print(f"{len(recs)} records")
    print(f"labelled contrails recognised:   {total['contrails_recognised']} of {total['contrails']} ({rec_pct:.0f}%)")
    print(f"other ice cloud called contrail: {total['other_ice_called_contrail']} of {total['other_ice']} ({fp_pct:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
