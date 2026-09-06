"""Free-tier enforcement as request counts per provider per UTC day, persisted in quota_counters.

Also a small in-process per-minute bucket so a burst never turns into a 429 storm.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime

from sqlmodel import Session

from ..config import settings
from ..models import QuotaCounter


_READY: set = set()


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


class Quota:
    def __init__(self, session_factory: Callable[[], Session], limits: dict[str, int] | None = None, rpm: int | None = None) -> None:
        self._sf = session_factory
        self.limits = limits or {
            "ollama": settings.ollama_daily_requests,
            "gemini": settings.gemini_daily_requests,
            "groq": settings.groq_daily_requests,
            "claude": settings.claude_daily_requests,
        }
        self.rpm = rpm if rpm is not None else settings.llm_rpm
        self._minute: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @classmethod
    def default(cls) -> Quota:
        from .. import db as dbmod

        engine = dbmod.engine
        if engine not in _READY:  # scripts and fresh deploys: make sure the counter table exists
            QuotaCounter.__table__.create(engine, checkfirst=True)
            _READY.add(engine)
        return cls(lambda: Session(engine))

    def limit(self, provider: str) -> int:
        return int(self.limits.get(provider, 0))

    def usage(self, provider: str, day: str | None = None) -> tuple[int, int]:
        with self._sf() as s:
            row = s.get(QuotaCounter, (provider, day or _today()))
            return (row.requests, row.tokens) if row else (0, 0)

    def check(self, provider: str) -> bool:
        """True when another request is allowed now (daily cap and minute bucket)."""
        lim = self.limit(provider)
        if lim <= 0:
            return False
        requests, _ = self.usage(provider)
        if requests >= lim:
            return False
        with self._lock:
            q = self._minute.setdefault(provider, deque())
            now = time.monotonic()
            while q and now - q[0] > 60:
                q.popleft()
            return len(q) < self.rpm

    def record(self, provider: str, tokens: int, requests: int = 1) -> None:
        with self._lock:
            q = self._minute.setdefault(provider, deque())
            q.extend([time.monotonic()] * requests)
        with self._sf() as s:
            key = (provider, _today())
            row = s.get(QuotaCounter, key) or QuotaCounter(provider=provider, day=key[1])
            row.requests += requests
            row.tokens += int(tokens)
            row.updated_at = datetime.now(UTC)
            s.add(row)
            s.commit()

    def exhaust(self, provider: str) -> None:
        """Mark a provider used up for today (after the provider itself returned 429)."""
        req, _ = self.usage(provider)
        self.record(provider, 0, requests=max(0, self.limit(provider) - req))

    def summary(self, day: str | None = None) -> dict[str, dict[str, int]]:
        return {p: dict(zip(("requests", "tokens"), self.usage(p, day), strict=True)) | {"limit": self.limit(p)} for p in self.limits}
