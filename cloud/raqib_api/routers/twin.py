"""Twin: replay a day and re-run the queue model and staffing plan under what-if changes."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import get_session
from ..twin.replay import replay
from ..twin.whatif import whatif

router = APIRouter(prefix="/twin", tags=["twin"])


def _day(v: str | None) -> date:
    if not v or v == "yesterday":
        return (datetime.now(UTC) - timedelta(days=1)).date()
    if v == "today":
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(v)
    except ValueError as exc:
        raise HTTPException(422, "date must be YYYY-MM-DD, today or yesterday") from exc


@router.get("/replay")
def get_replay(site: str = Query(...), date: str | None = None, session: Session = Depends(get_session)) -> dict:
    return replay(site, _day(date), session).as_dict()


class WhatIf(BaseModel):
    site: str
    date: str | None = None
    tills_by_slot: list[int] | None = Field(default=None, max_length=96)
    staff_delta: int = Field(0, ge=-5, le=5)
    zone_changes: dict[str, bool] | None = None
    max_rho: float = Field(0.85, gt=0, lt=1)


@router.post("/whatif")
def post_whatif(body: WhatIf, session: Session = Depends(get_session)) -> dict:
    try:
        return whatif(body.site, _day(body.date), session, tills_by_slot=body.tills_by_slot, staff_delta=body.staff_delta,
                      zone_changes=body.zone_changes, max_rho=body.max_rho)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
