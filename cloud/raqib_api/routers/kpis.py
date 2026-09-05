from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..kpis import summary
from ..models import Event, Site
from .sites import ensure_bundled_sites

router = APIRouter(tags=["kpis"])


@router.get("/kpis")
def kpis(site: str, window_h: float = 24.0, session: Session = Depends(get_session)) -> dict:
    ensure_bundled_sites(session)
    s = session.get(Site, site)
    if s is None:
        raise HTTPException(404, "site not found")
    now = datetime.now(UTC)
    events = session.exec(select(Event).where(Event.site == site).order_by(Event.ts)).all()
    for e in events:
        if e.ts.tzinfo is None:
            e.ts = e.ts.replace(tzinfo=UTC)
    return {"site": site, "as_of": now.isoformat(), **summary(events, s.profile, s.tills, now, window_h)}
