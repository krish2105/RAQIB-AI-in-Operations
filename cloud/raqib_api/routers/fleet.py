"""Fleet: heartbeats and drift samples from edge boxes, health, drift analysis, store leaderboard."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth.deps import current_principal, require, scope_site
from ..auth.rbac import Principal
from ..db import get_session
from ..fleet.drift import analyse, check_and_emit
from ..fleet.health import boxes, check_offline
from ..fleet.stores import KPIS, leaderboard
from ..models import DriftSample, EdgeHeartbeat, Store
from .sites import ensure_bundled_sites

router = APIRouter(prefix="/fleet", tags=["fleet"])


class HeartbeatIn(BaseModel):
    site: str
    box_id: str = Field(min_length=1, max_length=64)
    ts: datetime | None = None
    fps: float = Field(0.0, ge=0)
    temp_c: float | None = None
    queue_depth: int = Field(0, ge=0)
    model_hash: str = ""
    detector: str = ""
    version: str = ""
    cameras: list[str] = Field(default_factory=list, max_length=32)
    meta: dict = Field(default_factory=dict)


@router.post("/heartbeat", status_code=202)
def heartbeat(body: HeartbeatIn, p: Principal = Depends(require("ingest")), session: Session = Depends(get_session)) -> dict:
    scope_site(p, body.site)
    row = EdgeHeartbeat(**body.model_dump(exclude={"ts"}), ts=body.ts or datetime.now(UTC))
    session.add(row)
    session.commit()
    return {"accepted": True, "status": "online"}


class DriftIn(BaseModel):
    site: str
    camera: str
    ts: datetime
    det_count: float = Field(ge=0)
    mean_conf: float = Field(ge=0, le=1)
    brightness: float = Field(ge=0)
    blur: float = Field(ge=0)


@router.post("/drift", status_code=202)
def drift_samples(samples: list[DriftIn], p: Principal = Depends(require("ingest")), session: Session = Depends(get_session)) -> dict:
    for s in samples[:500]:
        scope_site(p, s.site)
        session.add(DriftSample(**s.model_dump()))
    session.commit()
    emitted = []
    for site in {s.site for s in samples}:
        emitted += check_and_emit(site, session)
    return {"accepted": min(len(samples), 500), "model_drift_events": [e.id for e in emitted]}


@router.get("/drift")
def drift(site: str = Query(...), camera: str | None = None, p: Principal = Depends(current_principal), session: Session = Depends(get_session)) -> dict:
    scope_site(p, site)
    cams = [camera] if camera else sorted({r for r in session.exec(select(DriftSample.camera).where(DriftSample.site == site).distinct()).all()})
    return {"site": site, "cameras": [analyse(site, c, session).as_dict() for c in cams]}


@router.get("/health")
def health(site: str = Query(...), p: Principal = Depends(current_principal), session: Session = Depends(get_session)) -> dict:
    scope_site(p, site)
    offline = check_offline(site, session)
    return {"site": site, "boxes": boxes(site, session), "edge_offline_events": [e.id for e in offline]}


@router.get("/leaderboard")
def board(kpi: str = Query("service_level"), window_h: float = Query(24, gt=0, le=24 * 30), p: Principal = Depends(current_principal),
          session: Session = Depends(get_session)) -> dict:
    ensure_bundled_sites(session)
    if kpi not in KPIS:
        raise HTTPException(422, f"kpi must be one of {KPIS}")
    rows = [r for r in leaderboard(session, kpi, window_h) if not p.site_ids or any(s in p.site_ids for s in r["site_ids"])]
    return {"kpi": kpi, "window_h": window_h, "stores": rows}


@router.get("/stores")
def stores(session: Session = Depends(get_session)) -> list[dict]:
    from ..fleet.stores import ensure_bundled_stores

    ensure_bundled_stores(session)
    return [{"id": s.id, "name": s.name, "site_ids": s.site_ids, "region": s.region} for s in session.exec(select(Store)).all()]
