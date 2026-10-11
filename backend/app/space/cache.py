"""Disk cache for upstream downloads: a time-to-live per source, and a polite back-off.

CelesTrak asks clients to download each dataset once per update and to stop at the first non-200
response; Launch Library 2 allows 15 anonymous requests an hour. So every download goes through here:
fresh copies are reused, any error makes us leave that host alone for an hour, and a stale copy is
served rather than retrying.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

USER_AGENT = "UpperAirLedger/0.1 (hackathon prototype)"
BACKOFF_S = 3600


class UpstreamError(RuntimeError):
    """An upstream source failed and there is no cached copy to fall back on."""


class Cache:
    def __init__(self, root: Path, client: httpx.Client | None = None, clock: Callable[[], float] = time.time):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._client = client
        self._clock = clock

    def get(self, key: str, url: str, ttl_s: float, params: dict | None = None) -> bytes:
        """Body of url (with params), from cache if younger than ttl_s, else downloaded."""
        data_p, meta_p = self._paths(key)
        meta = _read_json(meta_p)
        now = self._clock()
        if data_p.exists() and meta and now - meta.get("fetched_at", 0) < ttl_s:
            return data_p.read_bytes()

        host = urlsplit(url).netloc
        if self._backing_off(host, now):
            return self._stale(key, data_p, f"{host} returned an error recently; not asking again for up to an hour")
        try:
            r = self._http().get(url, params=params)
        except httpx.HTTPError as exc:
            self._back_off(host, now, str(exc))
            return self._stale(key, data_p, f"{host} unreachable: {exc}")
        if r.status_code != 200:
            self._back_off(host, now, f"HTTP {r.status_code}")
            return self._stale(key, data_p, f"{host} returned HTTP {r.status_code} for {url}")

        tmp = data_p.with_suffix(".tmp")
        tmp.write_bytes(r.content)
        tmp.replace(data_p)
        meta_p.write_text(json.dumps({"fetched_at": now, "url": str(r.url)}))
        return r.content

    def fetched_at(self, key: str) -> float | None:
        meta = _read_json(self._paths(key)[1])
        return meta.get("fetched_at") if meta else None

    def _paths(self, key: str) -> tuple[Path, Path]:
        return self.root / f"{key}.data", self.root / f"{key}.meta.json"

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120.0, follow_redirects=False)
        return self._client

    def _stale(self, key: str, data_p: Path, reason: str) -> bytes:
        if data_p.exists():
            log.warning("%s: %s; serving the cached copy", key, reason)
            return data_p.read_bytes()
        raise UpstreamError(reason)

    def _backoff_path(self) -> Path:
        return self.root / "_backoff.json"

    def _backing_off(self, host: str, now: float) -> bool:
        return now < (_read_json(self._backoff_path()) or {}).get(host, {}).get("until", 0)

    def _back_off(self, host: str, now: float, why: str) -> None:
        log.error("%s failed (%s); backing off for %d s", host, why, BACKOFF_S)
        state = _read_json(self._backoff_path()) or {}
        state[host] = {"until": now + BACKOFF_S, "why": why}
        self._backoff_path().write_text(json.dumps(state))


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return None
