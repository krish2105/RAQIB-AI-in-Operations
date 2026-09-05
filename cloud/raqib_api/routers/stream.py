"""Server-Sent Events: `event`, `action`, `clip` channels per site."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ..bus import bus, sse_format

router = APIRouter(tags=["stream"])


@router.get("/stream")
async def stream(request: Request, site: str = "*"):
    q = bus.subscribe(site)

    async def gen():
        try:
            yield {"event": "hello", "data": '{"site": "%s"}' % site}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                except TimeoutError:
                    yield {"comment": "keepalive"}
                    continue
                yield {"event": msg["channel"], "data": sse_format(msg).split("data: ", 1)[1].strip()}
        finally:
            bus.unsubscribe(site, q)

    return EventSourceResponse(gen(), ping=20)
