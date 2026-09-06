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
from .routers import actions, admin, ask, auth, cameras, crew, documents, events, fleet, notify, policy, pos, shelves, twin, vlm, forecast, health, kpis, report, sites, stream

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    Path(settings.clips_dir).mkdir(parents=True, exist_ok=True)
    bus.bind_loop(asyncio.get_running_loop())
    yield


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

for r in (health, sites, events, stream, actions, kpis, forecast, report, admin, documents, ask, vlm, cameras, crew, twin, pos, shelves, notify, auth, policy, fleet):
    app.include_router(r.router)
