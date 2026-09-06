"""Retention (admin) and the cost KPI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from ..auth.deps import current_principal, require, scope_site
from ..auth.rbac import Principal
from ..db import get_session
from ..jobs.cost import daily_cost
from ..jobs.retention import retention_log, run_retention

router = APIRouter(tags=["jobs"])


@router.post("/jobs/retention")
def retention(dry_run: bool = False, p: Principal = Depends(require("policy")), session: Session = Depends(get_session)) -> dict:
    return run_retention(session, dry_run=dry_run)


@router.get("/jobs/retention/log")
def retention_history(limit: int = Query(50, ge=1, le=500), p: Principal = Depends(current_principal), session: Session = Depends(get_session)) -> list[dict]:
    return retention_log(session, limit)


@router.get("/cost")
def cost(site: str | None = None, days: int = Query(7, ge=1, le=90), p: Principal = Depends(current_principal), session: Session = Depends(get_session)) -> dict:
    scope_site(p, site)
    return daily_cost(session, site, days)
