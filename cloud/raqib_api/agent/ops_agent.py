"""Per-event reasoning loop: backend -> policy -> (execute | propose) -> Action rows."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from ..config import settings
from ..models import Action, Event, Site
from ..ops_theory import slot_rates
from .backends import AgentBackend, make_backend
from .policies import Policy, is_proposal
from .tools import Call, ToolRunner

log = logging.getLogger(__name__)


def build_context(event: Event, session: Session) -> dict[str, Any]:
    site = session.get(Site, event.site)
    tills = site.tills if site else 1
    since = event.ts - timedelta(minutes=60)
    recent = session.exec(select(Event).where(Event.site == event.site, Event.ts >= since, Event.ts <= event.ts)).all()
    for e in recent:
        if e.ts.tzinfo is None:
            e.ts = e.ts.replace(tzinfo=UTC)
    slots = slot_rates(recent, tills_open=tills)
    rho = slots[-1].rho if slots else 0.0
    open_tills = tills
    return {
        "profile": site.profile if site else "retail",
        "tills": tills,
        "next_till": min(open_tills + 1, 20),
        "rho": round(rho, 3),
        "window": f"{event.ts.strftime('%H:%M')}-{(event.ts + timedelta(minutes=30)).strftime('%H:%M')}",
        "recent_counts": {k: sum(1 for e in recent if e.kind == k) for k in {e.kind for e in recent}},
        "lang": "en",
    }


def handle_event(event: Event, session: Session, backend: AgentBackend | None = None, runner: ToolRunner | None = None) -> list[Action]:
    backend = backend or make_backend()
    runner = runner or ToolRunner(session, event.site, backend.name)
    ctx = build_context(event, session)
    decision = backend.decide(event, ctx)
    outcome = Policy(session).check(event, decision.calls, decision.confidence, ctx["lang"])
    for call, reason in outcome.dropped:
        log.info("policy dropped %s: %s", call.tool, reason)
    actions: list[Action] = []
    exec_ctx = {"zone": event.payload.get("zone"), "clip_path": event.clip_path, "lang": ctx["lang"], "client_id": None}
    for call in outcome.calls:
        proposal = is_proposal(call.tool)
        rationale = decision.rationale if call.rationale in ("", "model") else f"{decision.rationale} | {call.rationale}"
        if outcome.notes:
            rationale += " | " + "; ".join(outcome.notes)
        action = Action(site=event.site, event_id=event.id, tool=call.tool, args=call.args, autonomous=not proposal,
                        status="proposed", reasoning=rationale, confidence=decision.confidence, backend=decision.backend)
        session.add(action)
        session.commit()
        session.refresh(action)
        if not proposal:
            res = runner.execute(call, action_id=action.id, ctx=exec_ctx)
            action.status = "executed" if res.ok else "failed"
            action.result = res.output if res.ok else {"error": res.error}
            action.decided_at = datetime.now(UTC)
            action.decided_by = "agent"
            session.add(action)
            session.commit()
            session.refresh(action)
        actions.append(action)
    if decision.cost_usd and actions:
        # attribute model cost to the first action's tool call row for the ledger
        from ..models import ToolCall

        tc = session.exec(select(ToolCall).where(ToolCall.action_id == actions[0].id)).first()
        if tc:
            tc.cost_usd += decision.cost_usd
            session.add(tc)
            session.commit()
    return actions


def approve_action(action: Action, session: Session, by: str, note: str | None = None) -> Action:
    runner = ToolRunner(session, action.site, action.backend)
    res = runner.execute(Call(action.tool, dict(action.args)), action_id=action.id,
                         ctx={"human_override": True, "client_id": None})
    action.status = "executed" if res.ok else "failed"
    action.result = {**(res.output or {}), "approved_by": by, "note": note} if res.ok else {"error": res.error}
    action.decided_at = datetime.now(UTC)
    action.decided_by = by
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


def reject_action(action: Action, session: Session, by: str, note: str | None = None) -> Action:
    action.status = "rejected"
    action.decided_at = datetime.now(UTC)
    action.decided_by = by
    action.result = {"note": note} if note else None
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


__all__ = ["handle_event", "approve_action", "reject_action", "build_context", "settings"]
