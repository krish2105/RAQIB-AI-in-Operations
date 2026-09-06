from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..kpis import summary
from ..models import Event, Site, Zone
from ..tz import ensure_utc
from .sites import ensure_bundled_sites


def shelf_ids(session: Session, site: str) -> list[str]:
    zones = session.exec(select(Zone).where(Zone.site == site, Zone.kind == "shelf")).all()
    return [str(z.meta.get("shelf_id", z.name)) for z in zones]

router = APIRouter(tags=["kpis"])


@router.get("/kpis")
def kpis(site: str, window_h: float = 24.0, session: Session = Depends(get_session)) -> dict:
    ensure_bundled_sites(session)
    s = session.get(Site, site)
    if s is None:
        raise HTTPException(404, "site not found")
    now = datetime.now(UTC)
    # Bound the scan to the window this call actually needs (plus a small margin for slot
    # edges) instead of loading the site's entire history: on a demo with tens of thousands
    # of events, materialising every row on every /kpis call is the difference between an
    # 8 ms query and an 8 s one, and it is the single worker the free-tier deploy has.
    since = now - timedelta(hours=window_h + 1)
    events = ensure_utc(
        session.exec(select(Event).where(Event.site == site, Event.ts >= since).order_by(Event.ts)).all()
    )
    # v2: POS transactions in the window give the service rate and label it "pos" (Phase B video estimate otherwise)
    from ..integrations.pos import transactions

    pos = [type("T", (), {"ts": t.ts.replace(tzinfo=UTC) if t.ts.tzinfo is None else t.ts, "till": t.till})() for t in transactions(site, session, since=now - timedelta(hours=window_h))]
    return {"site": site, "as_of": now.isoformat(), **summary(events, s.profile, s.tills, now, window_h, shelves=shelf_ids(session, site), pos=pos or None)}
