"""Crew: roster, runs, messages, budgets, kill switch. Every route returns 503 when agents are disabled."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, func, select

from ..config import settings
from ..crew.killswitch import KEY, enabled, set_enabled
from ..db import get_session
from ..models import Action, AgentMessage, AgentRun, CrewFlag

router = APIRouter(prefix="/crew", tags=["crew"])


def _iso(dt):
    """Timestamps leave as explicit UTC (SQLite hands back naive datetimes; browsers would read those as local time)."""
    if dt is None:
        return None
    from datetime import UTC

    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def _guard(session: Session) -> None:
    if not enabled(session):
        raise HTTPException(503, "agents are disabled (kill switch)")


@router.get("/status")
def status(session: Session = Depends(get_session)) -> dict:
    row = session.get(CrewFlag, KEY)
    return {"agents_enabled": enabled(session), "env_enabled": settings.agents_enabled, "crew_enabled": settings.crew_enabled,
            "flag": {"value": row.value, "updated_by": row.updated_by, "note": row.note, "updated_at": _iso(row.updated_at)} if row else None}


class Kill(BaseModel):
    by: str = "admin"
    note: str = ""
    confirm: str  # the typed confirmation from the UI: "KILL"


@router.post("/kill")
def kill(body: Kill, session: Session = Depends(get_session)) -> dict:
    if body.confirm != "KILL":
        raise HTTPException(422, 'type KILL to confirm')
    row = set_enabled(session, False, body.by, body.note)
    return {"agents_enabled": False, "updated_by": row.updated_by, "updated_at": _iso(row.updated_at)}


class Resume(BaseModel):
    by: str = "admin"
    note: str = ""


@router.post("/resume")
def resume(body: Resume, session: Session = Depends(get_session)) -> dict:
    if not settings.agents_enabled:
        raise HTTPException(409, "AGENTS_ENABLED=false in the environment; the flag cannot override it")
    row = set_enabled(session, True, body.by, body.note)
    return {"agents_enabled": True, "updated_by": row.updated_by, "updated_at": _iso(row.updated_at)}


@router.get("/roster")
def roster(site: str = Query(...), session: Session = Depends(get_session)) -> list[dict]:
    _guard(session)
    from ..crew.crew import build_crew

    crew = build_crew(session, site)
    out = []
    for name, agent in crew.agents.items():
        ident = agent.identity
        last = session.exec(select(AgentRun).where(AgentRun.site == site, AgentRun.agent == name).order_by(AgentRun.started.desc())).first()
        runs = session.exec(select(func.count()).select_from(AgentRun).where(AgentRun.site == site, AgentRun.agent == name)).one()
        flagged = session.exec(select(func.count()).select_from(AgentRun).where(AgentRun.site == site, AgentRun.agent == name, AgentRun.status == "flagged")).one()
        out.append({"name": name, "role": ident.role, "allowed_tools": sorted(ident.allowed_tools), "triggers": agent.triggers,
                    "budget": {"max_tool_calls": ident.budget.max_tool_calls, "max_usd": ident.budget.max_usd, "max_seconds": ident.budget.max_seconds},
                    "runs": int(runs), "flagged": int(flagged), "mandatory": name == "Auditor",
                    "last_run": {"id": last.id, "status": last.status, "started": _iso(last.started), "tool_calls": last.tool_calls, "cost_usd": last.cost_usd,
                                 "seconds": (last.meta or {}).get("seconds")} if last else None})
    return out


@router.get("/runs")
def runs(site: str = Query(...), limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)) -> list[dict]:
    _guard(session)
    rows = session.exec(select(AgentRun).where(AgentRun.site == site).order_by(AgentRun.started.desc()).limit(limit)).all()
    return [{"id": r.id, "agent": r.agent, "trigger": r.trigger, "status": r.status, "started": _iso(r.started), "ended": _iso(r.ended), "tool_calls": r.tool_calls,
             "tokens": r.tokens, "cost_usd": r.cost_usd, "meta": r.meta} for r in rows]


@router.get("/messages")
def messages(site: str = Query(...), limit: int = Query(100, ge=1, le=1000), run_id: str | None = None, session: Session = Depends(get_session)) -> list[dict]:
    _guard(session)
    from ..crew.bus import Bus
    from ..crew.crew import IDENTITIES

    bus = Bus(session, IDENTITIES)
    q = select(AgentMessage).join(AgentRun, AgentRun.id == AgentMessage.run_id).where(AgentRun.site == site)
    if run_id:
        q = q.where(AgentMessage.run_id == run_id)
    rows = session.exec(q.order_by(AgentMessage.ts.desc()).limit(limit)).all()
    return [{"id": m.id, "run_id": m.run_id, "from": m.from_agent, "to": m.to_agent, "schema": m.schema_name, "payload": m.payload,
             "hmac": m.hmac[:16] + "…", "verified": bus.verify_row(m), "ts": _iso(m.ts)} for m in rows]


@router.get("/actions")
def crew_actions(site: str = Query(...), limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)) -> list[dict]:
    _guard(session)
    rows = session.exec(select(Action).where(Action.site == site, Action.agent.is_not(None)).order_by(Action.created_at.desc()).limit(limit)).all()
    return [{"id": a.id, "agent": a.agent, "run_id": a.run_id, "tool": a.tool, "status": a.status, "event_id": a.event_id, "created_at": _iso(a.created_at)} for a in rows]


# ---- guarded memory ----------------------------------------------------------------------

class MemoryIn(BaseModel):
    site: str
    agent: str
    key: str
    value: str
    source: str = "api"
    written_by: str = "human"
    event_id: str | None = None
    pinned: bool = False


@router.get("/memory")
def list_memory(site: str = Query(...), agent: str | None = None, include_quarantined: bool = True, limit: int = Query(100, ge=1, le=1000),
                session: Session = Depends(get_session)) -> list[dict]:
    from ..models import Memory

    q = select(Memory).where(Memory.site == site)
    if agent:
        q = q.where(Memory.agent == agent)
    if not include_quarantined:
        q = q.where(Memory.quarantined.is_(False))
    rows = session.exec(q.order_by(Memory.ts.desc()).limit(limit)).all()
    return [{"id": m.id, "agent": m.agent, "key": m.key, "value": m.value, "source": m.source, "event_id": m.event_id, "written_by": m.written_by,
             "ts": m.ts, "pinned": m.pinned, "quarantined": m.quarantined, "quarantine_reason": m.quarantine_reason, "sha256": m.sha256[:12]} for m in rows]


@router.post("/memory", status_code=201)
def write_memory(body: MemoryIn, session: Session = Depends(get_session)) -> dict:
    from ..crew.memory import remember

    row, s = remember(body.site, body.agent, body.key, body.value, source=body.source, written_by=body.written_by, session=session,
                      event_id=body.event_id, pinned=body.pinned)
    return {"decision": s.decision, "reason": s.reason, "id": row.id if row else None, "quarantined": bool(row and row.quarantined)}


@router.post("/memory/snapshot", status_code=201)
def take_snapshot(site: str = Query(...), by: str = "admin", session: Session = Depends(get_session)) -> dict:
    from ..crew.memory import snapshot

    s = snapshot(site, session, by=by)
    return {"id": s.id, "site": s.site, "entries": s.entries, "taken_at": s.taken_at}


@router.get("/memory/snapshots")
def list_snapshots(site: str = Query(...), session: Session = Depends(get_session)) -> list[dict]:
    from ..models import MemorySnapshot

    rows = session.exec(select(MemorySnapshot).where(MemorySnapshot.site == site).order_by(MemorySnapshot.taken_at.desc()).limit(50)).all()
    return [{"id": s.id, "entries": s.entries, "taken_at": s.taken_at, "taken_by": s.taken_by} for s in rows]


@router.post("/memory/rollback")
def rollback_memory(site: str = Query(...), snapshot: int = Query(...), by: str = "admin", session: Session = Depends(get_session)) -> dict:
    from ..crew.memory import rollback

    try:
        return rollback(site, snapshot, session, by=by)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
