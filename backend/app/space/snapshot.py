"""Write the offline snapshot the frontend falls back to (commit the output for the demo).

Run from backend/:  .venv/Scripts/python -m app.space.snapshot [--days 90] [--limit 3000]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ..config import settings
from . import build
from .cache import Cache
from .contract import validate_orbits, validate_summary

OUT = Path(__file__).resolve().parents[3] / "frontend" / "data"
BUDGET = {"space-snapshot.json": 1_000_000, "space-orbits.json": 2_000_000}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--limit", type=int, default=3000)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    cache = Cache(settings.cache_dir / "space")
    docs = {"space-snapshot.json": (build.summary(cache, args.days), validate_summary),
            "space-orbits.json": (build.orbits(cache, args.limit), validate_orbits)}
    for name, (doc, validate) in docs.items():
        errs = validate(doc)
        if errs:
            print(f"{name}: does not match the contract, not written:", *errs[:20], sep="\n  ", file=sys.stderr)
            return 1
    args.out.mkdir(parents=True, exist_ok=True)
    for name, (doc, _) in docs.items():
        text = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
        (args.out / name).write_text(text, encoding="utf-8")
        over = " OVER BUDGET" if len(text.encode()) > BUDGET[name] else ""
        print(f"wrote {args.out / name} ({len(text.encode()) / 1e6:.2f} MB){over}")
    print("coverage:", json.dumps(docs["space-snapshot.json"][0]["coverage"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
