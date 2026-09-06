"""Notification opt-ins (WhatsApp templates only) and integration status for the Settings tab."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..integrations.whatsapp import TEMPLATES, WhatsAppClient
from ..models import NotifyOptIn

router = APIRouter(tags=["notify"])
ROLES = ("floor_manager", "store_manager", "safety_officer", "maintenance", "shift_supervisor")


class OptIn(BaseModel):
    site: str
    phone: str = Field(pattern=r"^\+?[0-9 \-]{8,20}$")
    role: str = Field("floor_manager", pattern="^(" + "|".join(ROLES) + ")$")
    lang: str = Field("en", pattern="^(en|hi|ar)$")


@router.get("/notify/optins")
def list_optins(site: str = Query(...), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(select(NotifyOptIn).where(NotifyOptIn.site == site, NotifyOptIn.opted_out_at.is_(None))).all()
    return [{"id": r.id, "phone": "…" + r.phone[-4:], "role": r.role, "lang": r.lang, "opted_in_at": r.opted_in_at} for r in rows]


@router.post("/notify/optins", status_code=201)
def opt_in(body: OptIn, session: Session = Depends(get_session)) -> dict:
    phone = re.sub(r"\D", "", body.phone)
    existing = session.exec(select(NotifyOptIn).where(NotifyOptIn.site == body.site, NotifyOptIn.phone == phone, NotifyOptIn.opted_out_at.is_(None))).first()
    if existing:
        return {"id": existing.id, "created": False}
    row = NotifyOptIn(site=body.site, phone=phone, role=body.role, lang=body.lang)
    session.add(row)
    session.commit()
    session.refresh(row)
    return {"id": row.id, "created": True}


@router.delete("/notify/optins/{optin_id}")
def opt_out(optin_id: int, session: Session = Depends(get_session)) -> dict:
    row = session.get(NotifyOptIn, optin_id)
    if row is None:
        raise HTTPException(404, "opt-in not found")
    row.opted_out_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    return {"id": optin_id, "opted_out": True}


@router.get("/integrations/status")
def status() -> dict:
    """Configured or not; never the values."""
    return {
        "whatsapp": {"configured": WhatsAppClient().enabled, "templates": sorted(TEMPLATES), "languages": ["en", "hi", "ar"], "free_text": False},
        "greenlam": {"configured": bool(settings.greenlam_url and settings.greenlam_employee_id and settings.greenlam_pin),
                     "retries": settings.greenlam_retries, "breaker": {"failures": settings.greenlam_breaker_failures, "cooldown_s": settings.greenlam_breaker_cooldown_s}},
        "webhook": {"configured": bool(settings.alert_webhook_url)},
        "pos": {"csv": True, "odoo": False, "shopify": False},
        "stream": {"configured": bool(settings.stream_upstream)},
    }
