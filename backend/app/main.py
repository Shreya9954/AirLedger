"""FastAPI app: serves the API under /api and the frontend at /."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles

from .config import settings
from .space.api import router as space_router
from .space_events import SPACE_EVENTS

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Upper Air Ledger API", version="0.1.0")

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@app.get("/api/health")
def health() -> dict:
    return {
        "mode": settings.mode,
        "sources": {
            "opensky": bool(settings.opensky_client_id),
            "aircraft_db": settings.opensky_aircraft_db.exists(),
            "contrails_org": bool(settings.contrails_org_url),
        },
    }


@app.get("/api/scenario")
async def scenario() -> dict:
    if not settings.live:
        raise HTTPException(404, "Demo mode: the frontend simulates the scenario. Set UAL_MODE=live to build one.")
    from .pipeline.scenario import cached_scenario  # heavy imports only in live mode

    try:
        return await run_in_threadpool(cached_scenario, settings)
    except Exception as exc:
        logging.exception("Scenario build failed")
        raise HTTPException(502, f"Could not build the live scenario: {exc}") from exc


@app.get("/api/space-events")
def space_events() -> list[dict]:
    return SPACE_EVENTS


app.include_router(space_router)  # before the static mount, which would otherwise catch /api/space/*

if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
