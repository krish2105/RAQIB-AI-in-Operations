"""VLM second opinions: on demand per event, list per site, disagreement metric."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, func, select

from ..auth.deps import VLM_LIMIT, rate_limited, require
from ..auth.rbac import Principal
from ..db import get_session
from ..models import Event, Opinion
from ..vlm.opinion import opine_event

router = APIRouter(tags=["vlm"])


def _out(o: Opinion) -> dict:
    return {"id": o.id, "event_id": o.event_id, "site": o.site, "rule_severity": o.rule_severity, "agrees": o.agrees,
            "confidence": o.confidence, "observed": o.observed, "disagreement_reason": o.disagreement_reason,
            "suggested_severity": o.suggested_severity, "disagreement": o.disagreement, "review_action_id": o.review_action_id,
            "trigger": o.trigger, "status": o.status, "model": o.model, "provider": o.provider, "frames": o.frames,
            "tokens": o.tokens_in + o.tokens_out, "cost_usd": o.cost_usd, "latency_ms": o.latency_ms, "ts": o.ts}


@router.post("/vlm/opinion/{event_id}", status_code=201)
def request_opinion(event_id: str, p: Principal = Depends(require("approve")), _: Principal = Depends(rate_limited(VLM_LIMIT, "vlm")), session: Session = Depends(get_session)) -> dict:
    if session.get(Event, event_id) is None:
        raise HTTPException(404, "event not found")
    o = opine_event(event_id, session, trigger="on_demand")
    return _out(o)


@router.get("/vlm/opinions")
def list_opinions(site: str = Query(...), event_id: str | None = None, limit: int = Query(50, ge=1, le=500),
                  session: Session = Depends(get_session)) -> list[dict]:
    q = select(Opinion).where(Opinion.site == site)
    if event_id:
        q = q.where(Opinion.event_id == event_id)
    return [_out(o) for o in session.exec(q.order_by(Opinion.ts.desc()).limit(limit)).all()]


@router.get("/vlm/summary")
def summary(site: str = Query(...), session: Session = Depends(get_session)) -> dict:
    total = session.exec(select(func.count()).select_from(Opinion).where(Opinion.site == site)).one()
    ok = session.exec(select(func.count()).select_from(Opinion).where(Opinion.site == site, Opinion.status == "ok")).one()
    dis = session.exec(select(func.count()).select_from(Opinion).where(Opinion.site == site, Opinion.disagreement.is_(True))).one()
    agree = session.exec(select(func.count()).select_from(Opinion).where(Opinion.site == site, Opinion.agrees.is_(True))).one()
    tokens = session.exec(select(func.coalesce(func.sum(Opinion.tokens_in + Opinion.tokens_out), 0)).where(Opinion.site == site)).one()
    return {"site": site, "opinions": int(total), "available": int(ok), "agree": int(agree), "disagreements": int(dis),
            "disagreement_rate": round(int(dis) / int(ok), 3) if ok else None, "tokens": int(tokens), "cost_usd": 0.0}
