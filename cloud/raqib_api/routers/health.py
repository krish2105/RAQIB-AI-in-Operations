from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from ..config import settings
from ..db import get_session
from ..models import Event

router = APIRouter(tags=["health"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    n = session.exec(select(func.count()).select_from(Event)).one()
    return {
        "status": "ok",
        "events": int(n),
        "agent_backend": settings.agent_backend,
        "database": settings.database_url.split("://")[0],
    }
