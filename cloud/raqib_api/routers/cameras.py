"""Watch tab feeds.

POST /detections           boxes-only frames from the edge (never pixels) -> SSE channel "detections"
GET  /detections/latest    last boxes per camera for a site (cold start for the wall)
GET  /cameras/{site}/{camera}/stream   proxy of the edge's blurred MJPEG stream (token stays server-side)
GET  /captions             recent VLM captions for the ticker
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..bus import bus
from ..config import settings
from ..db import get_session
from ..models import Caption

router = APIRouter(tags=["watch"])

_LATEST: dict[tuple[str, str], dict[str, Any]] = {}
_RECENT: deque = deque(maxlen=2000)


class Box(BaseModel):
    id: int
    cls: str
    conf: float = Field(ge=0, le=1)
    box: list[float] = Field(min_length=4, max_length=4)


class DetectionsIn(BaseModel):
    site: str
    camera: str
    ts: datetime
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    boxes: list[Box] = Field(max_length=200)


@router.post("/detections", status_code=202)
def post_detections(d: DetectionsIn) -> dict:
    """Accept a boxes-only frame; anything that looks like image data is rejected by the schema (no such field)."""
    payload = d.model_dump(mode="json")
    payload["received"] = time.time()
    _LATEST[(d.site, d.camera)] = payload
    _RECENT.append(payload)
    bus.publish(d.site, "detections", payload)
    return {"accepted": len(d.boxes)}


@router.get("/detections/latest")
def latest(site: str = Query(...)) -> list[dict]:
    return [v for (s, _c), v in _LATEST.items() if s == site]


@router.get("/cameras/{site}/{camera}/stream")
async def stream_proxy(site: str, camera: str):
    """Proxy the edge box's blurred MJPEG stream. The edge token never reaches the browser."""
    if not settings.stream_upstream:
        raise HTTPException(503, "camera stream not configured (STREAM_UPSTREAM)")
    url = f"{settings.stream_upstream.rstrip('/')}/stream/{camera}"
    params = {"token": settings.stream_token} if settings.stream_token else None
    client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=None))
    try:
        req = client.build_request("GET", url, params=params)
        resp = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(502, f"edge stream unreachable: {exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        await resp.aclose()
        await client.aclose()
        raise HTTPException(502, f"edge stream returned {resp.status_code}")

    async def gen():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(gen(), media_type=resp.headers.get("content-type", "multipart/x-mixed-replace; boundary=frame"),
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/captions")
def captions(site: str = Query(...), limit: int = Query(30, ge=1, le=200), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(select(Caption).where(Caption.site == site, Caption.model != "none").order_by(Caption.ts.desc()).limit(limit)).all()
    return [{"id": c.id, "event_id": c.event_id, "camera": c.camera, "ts": c.ts, "text": c.text, "parsed": c.parsed, "model": c.model} for c in rows]
