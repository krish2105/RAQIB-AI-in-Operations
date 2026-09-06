"""Stores group sites. Leaderboard: service level, OSA, compliance, agent cost per store over a window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, func, select

from ..kpis import summary
from ..models import AgentRun, Event, Site, Store, ToolCall
from ..tz import ensure_utc
from .health import boxes

BUNDLED = [Store(id="demo-store", name="RAQIB demo store", site_ids=["raqib_demo_store"], region="Dubai"),
           Store(id="greenlam-unit-1", name="Greenlam Unit 1", site_ids=["greenlam_unit1"], region="Rajasthan")]
KPIS = ("service_level", "osa", "compliance", "agent_cost_usd", "events", "actions")


def ensure_bundled_stores(session: Session) -> None:
    for st in BUNDLED:
        if session.get(Store, st.id) is None:
            session.add(Store(id=st.id, name=st.name, site_ids=list(st.site_ids), region=st.region))
    session.commit()


def store_row(store: Store, session: Session, now: datetime, window_h: float) -> dict[str, Any]:
    since = now - timedelta(hours=window_h)
    sl, os_, comp, cost, n_ev, n_act, footfall = [], [], [], 0.0, 0, 0, 0
    edge = []
    for site_id in store.site_ids:
        s = session.get(Site, site_id)
        if s is None:
            continue
        events = ensure_utc(session.exec(select(Event).where(Event.site == site_id, Event.ts >= since.replace(tzinfo=None))).all())
        kp = summary(events, s.profile, s.tills, now, window_h=window_h)
        if kp.get("service_level") is not None:
            sl.append(kp["service_level"])
        if kp.get("osa_store") is not None:
            os_.append(kp["osa_store"])
        if kp.get("compliance") is not None:
            comp.append(kp["compliance"])
        footfall += kp.get("footfall", 0)
        n_ev += len(events)
        n_act += session.exec(select(func.count()).select_from(AgentRun).where(AgentRun.site == site_id, AgentRun.started >= since.replace(tzinfo=None))).one()
        cost += float(session.exec(select(func.coalesce(func.sum(ToolCall.cost_usd), 0.0)).where(ToolCall.site == site_id, ToolCall.created_at >= since.replace(tzinfo=None))).one() or 0.0)
        cost += float(session.exec(select(func.coalesce(func.sum(AgentRun.cost_usd), 0.0)).where(AgentRun.site == site_id, AgentRun.started >= since.replace(tzinfo=None))).one() or 0.0)
        edge += boxes(site_id, session, now)
    mean = lambda xs: (sum(xs) / len(xs)) if xs else None  # noqa: E731
    return {"id": store.id, "name": store.name, "region": store.region, "site_ids": store.site_ids, "service_level": mean(sl), "osa": mean(os_),
            "compliance": mean(comp), "agent_cost_usd": round(cost, 4), "events": n_ev, "actions": n_act, "footfall": footfall,
            "edge": {"boxes": len(edge), "online": sum(1 for b in edge if b["status"] == "online"), "offline": sum(1 for b in edge if b["status"] == "offline")}}


def leaderboard(session: Session, kpi: str = "service_level", window_h: float = 24.0, now: datetime | None = None) -> list[dict[str, Any]]:
    if kpi not in KPIS:
        raise ValueError(f"kpi must be one of {KPIS}")
    now = now or datetime.now(UTC)
    ensure_bundled_stores(session)
    rows = [store_row(st, session, now, window_h) for st in session.exec(select(Store)).all()]
    reverse = kpi != "agent_cost_usd"  # lower cost is better
    rows.sort(key=lambda r: (r[kpi] is None, -(r[kpi] or 0) if reverse else (r[kpi] or 0)))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows
