"""Shelves: per-shelf availability plus v2 planogram drift and price-tag mismatches from the edge rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..db import get_session
from ..kpis import osa, time_to_restock
from ..models import Event, Site
from ..tz import ensure_utc
from .kpis import shelf_ids
from .sites import ensure_bundled_sites

router = APIRouter(tags=["shelves"])


@router.get("/shelves")
def shelves(site: str = Query(...), window_h: float = Query(24, gt=0, le=24 * 30), session: Session = Depends(get_session)) -> dict:
    ensure_bundled_sites(session)
    s = session.get(Site, site)
    if s is None:
        raise HTTPException(404, "site not found")
    now = datetime.now(UTC)
    since = now - timedelta(hours=window_h)
    events = ensure_utc(session.exec(select(Event).where(Event.site == site, Event.ts >= since.replace(tzinfo=None),
                                                        Event.kind.in_(["shelf_gap", "planogram_drift", "price_mismatch"])).order_by(Event.ts)).all())
    ids = sorted(set(shelf_ids(session, site)) | {str(e.payload.get("shelf_id")) for e in events if e.payload.get("shelf_id")})
    avail = osa(events, now, window_h=window_h)
    ttr = time_to_restock(events)
    out = []
    for sid in ids:
        drift = [e for e in events if e.kind == "planogram_drift" and str(e.payload.get("shelf_id")) == sid]
        prices = [e for e in events if e.kind == "price_mismatch" and str(e.payload.get("shelf_id")) == sid]
        gaps = [e for e in events if e.kind == "shelf_gap" and str(e.payload.get("shelf_id")) == sid]
        last_drift = drift[-1] if drift else None
        out.append({
            "shelf_id": sid, "osa": avail.get(sid, 1.0), "time_to_restock_min": ttr.get(sid), "gaps": len(gaps),
            "planogram": {"compliance": last_drift.payload.get("compliance") if last_drift else None, "expected": last_drift.payload.get("expected") if last_drift else None,
                          "present": last_drift.payload.get("present") if last_drift else None, "missing": last_drift.payload.get("missing", []) if last_drift else [],
                          "misplaced": last_drift.payload.get("misplaced", []) if last_drift else [], "events": len(drift), "last_ts": last_drift.ts if last_drift else None,
                          "event_id": last_drift.id if last_drift else None},
            "price_tags": [{"tag": e.payload.get("tag"), "read_price": e.payload.get("read_price"), "expected_price": e.payload.get("expected_price"),
                            "delta": e.payload.get("delta"), "ts": e.ts, "event_id": e.id} for e in prices[-10:]],
        })
    return {"site": site, "window_h": window_h, "as_of": now.isoformat(), "shelves": out,
            "totals": {"drift_events": sum(1 for e in events if e.kind == "planogram_drift"), "price_mismatches": sum(1 for e in events if e.kind == "price_mismatch"),
                       "gaps": sum(1 for e in events if e.kind == "shelf_gap")}}
