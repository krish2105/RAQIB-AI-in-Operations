"""In-process pub/sub for Server-Sent Events. One process on Render, so this is enough."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, site: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs[site].add(q)
        return q

    def unsubscribe(self, site: str, q: asyncio.Queue) -> None:
        self._subs[site].discard(q)

    def publish(self, site: str, channel: str, data: dict[str, Any]) -> None:
        """Thread-safe: may be called from sync request handlers."""
        msg = {"channel": channel, "data": data}
        for q in list(self._subs.get(site, ())) + list(self._subs.get("*", ())):
            loop = self._loop
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(_put_nowait, q, msg)
            else:
                _put_nowait(q, msg)


def _put_nowait(q: asyncio.Queue, msg: dict) -> None:
    try:
        q.put_nowait(msg)
    except asyncio.QueueFull:
        pass


def sse_format(msg: dict[str, Any]) -> str:
    return f"event: {msg['channel']}\ndata: {json.dumps(msg['data'], default=str)}\n\n"


bus = EventBus()
