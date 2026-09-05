from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..db import get_session
from ..forecast import fit_predict, hourly_counts
from ..models import Event, Site
from ..tz import ensure_utc
from ..ops_theory import slot_rates, tills_for_target_rho
from ..workforce import staffing_plan
from .sites import ensure_bundled_sites

router = APIRouter(tags=["forecast"])

TARGET_KIND = {"queue": "footfall_tick", "shelf": "shelf_gap", "machine": "machine_stopped", "footfall": "footfall_tick"}


def _events(session: Session, site: str) -> list[Event]:
    return ensure_utc(session.exec(select(Event).where(Event.site == site).order_by(Event.ts)).all())


@router.get("/forecast")
def forecast(site: str, target: str = Query("queue", pattern="^(queue|shelf|machine|footfall)$"), horizon: int = Query(24, ge=1, le=168),
             session: Session = Depends(get_session)) -> dict:
    ensure_bundled_sites(session)
    if session.get(Site, site) is None:
        raise HTTPException(404, "site not found")
    events = _events(session, site)
    series = hourly_counts(events, TARGET_KIND[target], end=datetime.now(UTC))
    res = fit_predict(series, horizon=horizon)
    return {"site": site, "target": target, "kind": TARGET_KIND[target], "horizon_h": horizon,
            "simulated_share": round(sum(1 for e in events if e.payload.get("simulated")) / len(events), 3) if events else 0.0,
            **res.as_dict()}


@router.get("/workforce")
def workforce(site: str, max_rho: float = Query(0.85, gt=0, lt=1), max_tills: int | None = None, day: str | None = None,
              session: Session = Depends(get_session)) -> dict:
    ensure_bundled_sites(session)
    s = session.get(Site, site)
    if s is None:
        raise HTTPException(404, "site not found")
    events = _events(session, site)
    if day:
        events = [e for e in events if e.ts.date().isoformat() == day]
    else:
        last = max((e.ts for e in events), default=None)
        if last is not None:
            events = [e for e in events if e.ts.date() == last.date()]
    slots = slot_rates(events, tills_open=s.tills)
    if not slots:
        return {"site": site, "sufficient": False, "reason": "no events for that day"}
    lam = [x.lam_per_h for x in slots]
    mus = [x.mu_per_h for x in slots if x.served > 0]
    mu = sum(mus) / len(mus) if mus else 30.0
    ceiling = max_tills or max(s.tills, 3, tills_for_target_rho(max(lam), mu, max_rho))
    try:
        plan = staffing_plan(lam, mu, max_rho=max_rho, max_tills=ceiling, baseline_tills=s.tills)
    except RuntimeError as exc:
        return {"site": site, "sufficient": False, "reason": str(exc)}
    return {"site": site, "sufficient": True, "day": slots[0].slot_start.date().isoformat(), "slots": [x.slot_start.isoformat() for x in slots],
            "observed_tills": s.tills, "mu_source": "estimated_from_video", **plan.as_dict()}
