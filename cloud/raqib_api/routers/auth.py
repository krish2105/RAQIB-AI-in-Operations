"""Who am I, and (admin) who is everyone: roles and site scoping live in the users table."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth.deps import current_principal, require
from ..auth.rbac import CAPABILITIES, ROLES, Principal
from ..config import settings
from ..db import get_session
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me(p: Principal = Depends(current_principal)) -> dict:
    return {"id": p.id, "email": p.email, "role": p.role, "site_ids": list(p.site_ids), "anonymous": p.anonymous,
            "auth_required": settings.auth_required, "capabilities": {c: p.can(c) for c in CAPABILITIES}}


@router.get("/users")
def users(_: Principal = Depends(require("policy")), session: Session = Depends(get_session)) -> list[dict]:
    return [{"id": u.id, "email": u.email, "role": u.role, "site_ids": u.site_ids, "created_at": u.created_at} for u in session.exec(select(User).order_by(User.created_at)).all()]


class UserPatch(BaseModel):
    role: str | None = Field(default=None, pattern="^(" + "|".join(ROLES) + ")$")
    site_ids: list[str] | None = None


@router.patch("/users/{user_id}")
def patch_user(user_id: str, body: UserPatch, p: Principal = Depends(require("policy")), session: Session = Depends(get_session)) -> dict:
    u = session.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    if body.role is not None:
        u.role = body.role
    if body.site_ids is not None:
        u.site_ids = body.site_ids
    session.add(u)
    session.commit()
    return {"id": u.id, "role": u.role, "site_ids": u.site_ids, "by": p.email}
