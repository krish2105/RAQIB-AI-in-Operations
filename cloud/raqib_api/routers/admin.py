"""Seeding and housekeeping for demos and tests."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, delete, select

from ..agent.ops_agent import handle_event
from ..db import get_session
from ..models import Action, AskLog, Caption, Chunk, Event, Site, ToolCall
from ..simulate import generate
from .sites import ensure_bundled_sites

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/seed")
def seed(site: str = "raqib_demo_store", days: int = Query(21, ge=1, le=90), seed: int = 7, run_agent_last_hours: int = Query(6, ge=0, le=48),
         reset: bool = True, session: Session = Depends(get_session)) -> dict:
    ensure_bundled_sites(session)
    s = session.get(Site, site)
    if s is None:
        raise HTTPException(404, "site not found")
    if reset:
        _reset_site(site, session)
    now = datetime.now(UTC)
    rows = generate(site, s.profile, days=days, seed=seed, end=now.replace(minute=0, second=0, microsecond=0), tills=s.tills)
    inserted = 0
    for r in rows:
        if session.get(Event, r["id"]) is None:
            r2 = dict(r)
            r2["ts"] = datetime.fromisoformat(r2["ts"])
            session.add(Event(**r2, handled=True))
            inserted += 1
    session.commit()
    # Let the agent handle only the recent actionable events so the actions queue is realistic, not thousands deep.
    cutoff = now.timestamp() - run_agent_last_hours * 3600
    actionable = session.exec(select(Event).where(Event.site == site, Event.severity >= 1,
                                                  Event.kind.in_(["queue_over", "shelf_gap", "machine_stopped", "zone_breach", "ppe_violation"]))
                              .order_by(Event.ts)).all()
    created = 0
    for e in actionable:
        if e.ts.replace(tzinfo=UTC).timestamp() >= cutoff:
            created += len(handle_event(e, session))
    return {"site": site, "days": days, "inserted": inserted, "actions_created": created, "simulated": True}


@router.post("/index")
def index(site: str = "raqib_demo_store", days: float = Query(21, ge=0.01, le=400), embed: bool = True, captions: bool = False,
          session: Session = Depends(get_session)) -> dict:
    """Chunk (and embed when an embedder is reachable) the last `days` of events and KPIs so Ask can answer.
    Captions are off by default here: the indexer with a VLM runs on the Mac / edge box (`raqib-api index`)."""
    from datetime import timedelta

    from ..rag.indexer import index_since

    s = session.get(Site, site)
    if s is None:
        raise HTTPException(404, "site not found")
    stats = index_since(site, datetime.now(UTC) - timedelta(days=days), session, embed=embed, captions=captions, tills=s.tills)
    return stats.as_dict()


def _reset_site(site: str, session: Session) -> None:
    """Delete in FK order: v2 rows that reference events (chunks, captions, ask log) go first so Postgres never rejects it."""
    for model in (AskLog, Chunk, Caption, ToolCall, Action, Event):
        session.exec(delete(model).where(model.site == site))
    session.commit()


@router.post("/reset")
def reset(site: str, session: Session = Depends(get_session)) -> dict:
    _reset_site(site, session)
    return {"site": site, "reset": True}
