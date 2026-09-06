"""Policy thresholds (admin only). Stored per site in crew_flags as JSON; Policy reads them on every check."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..auth.deps import current_principal, require
from ..auth.rbac import Principal
from ..db import get_session
from ..models import CrewFlag

router = APIRouter(prefix="/policy", tags=["policy"])
DEFAULTS = {"rho_threshold": 0.85, "review_confidence": 0.6, "work_order_cooldown_h": 4.0, "vlm_review_confidence": 0.8}


def load_policy(session: Session, site: str) -> dict:
    row = session.get(CrewFlag, f"policy:{site}")
    if row is None:
        return dict(DEFAULTS)
    try:
        return {**DEFAULTS, **json.loads(row.value)}
    except json.JSONDecodeError:
        return dict(DEFAULTS)


class PolicyIn(BaseModel):
    rho_threshold: float = Field(0.85, gt=0.5, lt=1.0)
    review_confidence: float = Field(0.6, ge=0.0, le=1.0)
    work_order_cooldown_h: float = Field(4.0, ge=0.0, le=48.0)
    vlm_review_confidence: float = Field(0.8, ge=0.0, le=1.0)


@router.get("")
def get_policy(site: str = Query(...), _: Principal = Depends(current_principal), session: Session = Depends(get_session)) -> dict:
    row = session.get(CrewFlag, f"policy:{site}")
    return {"site": site, "values": load_policy(session, site), "defaults": DEFAULTS,
            "updated_by": row.updated_by if row else None, "updated_at": row.updated_at if row else None, "note": row.note if row else None}


@router.put("")
def put_policy(body: PolicyIn, site: str = Query(...), note: str = "", p: Principal = Depends(require("policy")), session: Session = Depends(get_session)) -> dict:
    before = load_policy(session, site)
    after = body.model_dump()
    row = session.get(CrewFlag, f"policy:{site}") or CrewFlag(key=f"policy:{site}")
    row.value, row.updated_by, row.note, row.updated_at = json.dumps(after), p.email, note, datetime.now(UTC)
    session.add(row)
    session.commit()
    diff = {k: {"before": before[k], "after": after[k]} for k in after if before.get(k) != after[k]}
    return {"site": site, "values": after, "diff": diff, "updated_by": p.email}
