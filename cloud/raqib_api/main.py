"""RAQIB / MUSHRIF cloud API."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bus import bus
from .config import settings
from .db import init_db
from .routers import actions, admin, ask, auth, cameras, crew, documents, events, fleet, jobs, notify, policy, pos, shelves, twin, vlm, forecast, health, kpis, report, sites, stream

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    Path(settings.clips_dir).mkdir(parents=True, exist_ok=True)
    bus.bind_loop(asyncio.get_running_loop())
    from .telemetry import setup as otel_setup

    otel_setup()
    task = asyncio.create_task(_retention_loop()) if settings.retention_schedule else None
    yield
    if task is not None:
        task.cancel()


async def _retention_loop() -> None:
    """Once a day, in-process: fine for one Render instance; a cron hits POST /jobs/retention on bigger setups."""
    from sqlmodel import Session

    from . import db as dbmod
    from .jobs.retention import run_retention

    while True:
        await asyncio.sleep(24 * 3600)
        try:
            with Session(dbmod.engine) as s:
                run_retention(s)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception("retention job failed")


app = FastAPI(
    title="RAQIB API",
    version="0.1.0",
    description="Vision-driven operations agent for retail floors (RAQIB) and factories (MUSHRIF).",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list or ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (health, sites, events, stream, actions, kpis, forecast, report, admin, documents, ask, vlm, cameras, crew, twin, pos, shelves, notify, auth, policy, fleet, jobs):
    app.include_router(r.router)
