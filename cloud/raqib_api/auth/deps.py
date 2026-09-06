"""FastAPI dependencies: current principal, role gates, site scoping, per-user rate limits."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from ..config import settings
from ..db import get_session
from ..models import User
from .jwt import AuthError, verify
from .rbac import DEV_ADMIN, ROLES, Principal


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    return h[7:].strip() if h.lower().startswith("bearer ") else None


def upsert_user(session: Session, sub: str, email: str) -> User:
    u = session.get(User, sub)
    if u is None:
        admins = {e.strip().lower() for e in settings.auth_admin_emails.split(",") if e.strip()}
        u = User(id=sub, email=email, role="admin" if email.lower() in admins else settings.auth_default_role, site_ids=[])
        session.add(u)
        session.commit()
        session.refresh(u)
    return u


def current_principal(request: Request, session: Session = Depends(get_session)) -> Principal:
    token = _bearer(request)
    if token is None:
        if settings.auth_required:
            raise HTTPException(401, "sign in required")
        return DEV_ADMIN
    try:
        claims = verify(token)
    except AuthError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    u = upsert_user(session, claims.sub, claims.email)
    return Principal(id=u.id, email=u.email, role=u.role if u.role in ROLES else "viewer", site_ids=tuple(u.site_ids or []))


def require(capability: str) -> Callable:
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.can(capability):
            raise HTTPException(403, f"{capability} needs role {__import__('raqib_api.auth.rbac', fromlist=['CAPABILITIES']).CAPABILITIES[capability]} or higher")
        return p

    return dep


def scope_site(p: Principal, site: str | None) -> None:
    if not p.may_see(site):
        raise HTTPException(403, "not allowed for this site")


class RateLimiter:
    def __init__(self, per_min: int) -> None:
        self.per_min = per_min
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_min:
                return False
            q.append(now)
            return True


ASK_LIMIT = RateLimiter(settings.rate_ask_per_min)
VLM_LIMIT = RateLimiter(settings.rate_vlm_per_min)


def rate_limited(limiter: RateLimiter, name: str) -> Callable:
    def dep(request: Request, p: Principal = Depends(current_principal)) -> Principal:
        key = p.id if not p.anonymous else (request.client.host if request.client else "anon")
        if not limiter.hit(key):
            raise HTTPException(429, f"{name}: rate limit {limiter.per_min}/min for this user")
        return p

    return dep
