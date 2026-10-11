"""Space ledger endpoints: /api/space/summary and /api/space/orbits (Contract 2 in docs/space-ledger.md)."""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from ..config import settings
from . import build
from .cache import Cache, UpstreamError

router = APIRouter(prefix="/api/space", tags=["space"])

MEMO_S = 600  # rebuilding means parsing ~25 MB of catalogues, so keep results for 10 minutes
_memo: dict[tuple, tuple[float, dict]] = {}
_lock = threading.Lock()


def _cache() -> Cache:
    return Cache(settings.cache_dir / "space")


def _memoised(key: tuple, make) -> dict:
    with _lock:  # one build at a time, so concurrent requests don't download twice
        hit = _memo.get(key)
        if hit and time.time() - hit[0] < MEMO_S:
            return hit[1]
        value = make()
        _memo[key] = (time.time(), value)
        return value


@router.get("/summary")
async def summary(days: int = Query(90, ge=7, le=365)) -> dict:
    try:
        return await run_in_threadpool(_memoised, ("summary", days), lambda: build.summary(_cache(), days))
    except UpstreamError as exc:
        raise HTTPException(503, f"Space data unavailable: {exc}") from exc


@router.get("/orbits")
async def orbits(limit: int = Query(3000, ge=100, le=6000)) -> dict:
    try:
        return await run_in_threadpool(_memoised, ("orbits", limit), lambda: build.orbits(_cache(), limit))
    except UpstreamError as exc:
        raise HTTPException(503, f"Orbit data unavailable: {exc}") from exc
