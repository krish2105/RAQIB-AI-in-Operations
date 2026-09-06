from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..agent.ops_agent import approve_action, reject_action
from ..auth.deps import current_principal, require, scope_site
from ..auth.rbac import Principal
from ..bus import bus
from ..db import get_session
from ..models import Action, ToolCall
from ..schemas import ActionOut, Decide, ToolCallOut

router = APIRouter(tags=["actions"])


@router.get("/actions", response_model=list[ActionOut])
def list_actions(site: str | None = None, status: str | None = None, tool: str | None = None, p: Principal = Depends(current_principal),
                 limit: int = Query(100, ge=1, le=1000), session: Session = Depends(get_session)) -> list[Action]:
    scope_site(p, site)
    q = select(Action)
    if site:
        q = q.where(Action.site == site)
    if status:
        q = q.where(Action.status == status)
    if tool:
        q = q.where(Action.tool == tool)
    return session.exec(q.order_by(Action.created_at.desc()).limit(limit)).all()


@router.get("/actions/{action_id}", response_model=ActionOut)
def get_action(action_id: int, session: Session = Depends(get_session)) -> Action:
    a = session.get(Action, action_id)
    if a is None:
        raise HTTPException(404, "action not found")
    return a


@router.post("/actions/{action_id}/approve", response_model=ActionOut)
def approve(action_id: int, body: Decide | None = None, p: Principal = Depends(require("approve")), session: Session = Depends(get_session)) -> Action:
    a = session.get(Action, action_id)
    if a is None:
        raise HTTPException(404, "action not found")
    scope_site(p, a.site)
    if a.status != "proposed":
        raise HTTPException(409, f"action is {a.status}, only proposed actions can be approved")
    body = body or Decide()
    a = approve_action(a, session, by=body.by, note=body.note)
    bus.publish(a.site, "action", {"id": a.id, "tool": a.tool, "status": a.status, "event_id": a.event_id})
    return a


@router.post("/actions/{action_id}/reject", response_model=ActionOut)
def reject(action_id: int, body: Decide | None = None, p: Principal = Depends(require("approve")), session: Session = Depends(get_session)) -> Action:
    a = session.get(Action, action_id)
    if a is None:
        raise HTTPException(404, "action not found")
    scope_site(p, a.site)
    if a.status != "proposed":
        raise HTTPException(409, f"action is {a.status}, only proposed actions can be rejected")
    body = body or Decide()
    a = reject_action(a, session, by=body.by, note=body.note)
    bus.publish(a.site, "action", {"id": a.id, "tool": a.tool, "status": a.status, "event_id": a.event_id})
    return a


@router.get("/toolcalls", response_model=list[ToolCallOut])
def list_toolcalls(site: str | None = None, limit: int = Query(200, ge=1, le=2000), session: Session = Depends(get_session)) -> list[ToolCall]:
    q = select(ToolCall)
    if site:
        q = q.where(ToolCall.site == site)
    return session.exec(q.order_by(ToolCall.created_at.desc()).limit(limit)).all()


@router.get("/toolcalls/summary")
def toolcall_summary(site: str | None = None, session: Session = Depends(get_session)) -> dict:
    q = select(ToolCall)
    if site:
        q = q.where(ToolCall.site == site)
    rows = session.exec(q).all()
    by_tool: dict[str, dict] = {}
    for r in rows:
        d = by_tool.setdefault(r.tool, {"calls": 0, "ok": 0, "cost_usd": 0.0, "latency_ms_avg": 0.0})
        d["calls"] += 1
        d["ok"] += int(r.ok)
        d["cost_usd"] += r.cost_usd
        d["latency_ms_avg"] += r.latency_ms
    for d in by_tool.values():
        d["latency_ms_avg"] = round(d["latency_ms_avg"] / d["calls"], 1)
        d["cost_usd"] = round(d["cost_usd"], 5)
    return {"total_calls": len(rows), "total_cost_usd": round(sum(r.cost_usd for r in rows), 5), "by_tool": by_tool}
