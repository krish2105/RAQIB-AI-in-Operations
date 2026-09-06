"""One runtime for every agent. It enforces the envelope; agents only plan.

run(agent, trigger, ctx):
  1. kill switch checked before the run and at every tool boundary (AgentsDisabled aborts, status "killed")
  2. the agent's plan() returns Calls; tools outside its allow-list are DENIED here, before Policy, and recorded
  3. the existing Policy runs (severity-3 escalation, downgrade block, cooldowns, rho rule) — no second path
  4. every executed call goes through the existing ToolRunner (validated, logged with cost)
  5. the Budget meter counts tool calls, dollars and seconds; a breach aborts with status "budget_exceeded"
  6. an AgentRun row records everything; proposals carry agent + run_id; a run_report goes on the bus
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlmodel import Session, select
from ulid import ULID

from ..agent.policies import Policy, is_proposal
from ..agent.tools import Call, ToolRunner
from ..models import Action, AgentRun, Event
from .budget import BudgetExceeded, BudgetMeter
from .bus import Bus, Message
from .identity import AgentIdentity
from .killswitch import AgentsDisabled
from .killswitch import check as check_killswitch

log = logging.getLogger(__name__)


@dataclass
class Plan:
    calls: list[Call]
    rationale: str
    confidence: float = 0.8
    evidence: list[str] = field(default_factory=list)  # event ids, chunk ids, Ask citations
    notes: list[str] = field(default_factory=list)


class Agent(Protocol):
    identity: AgentIdentity

    def plan(self, event: Event | None, ctx: dict[str, Any], session: Session) -> Plan: ...


@dataclass
class RunOutcome:
    run: AgentRun
    actions: list[Action]
    denied: list[str]
    dropped: list[str]


class Runtime:
    def __init__(self, session: Session, identities: dict[str, AgentIdentity], bus: Bus | None = None, runner: ToolRunner | None = None,
                 auditor: Any | None = None) -> None:
        self.session = session
        self.identities = identities
        self.bus = bus or Bus(session, identities)
        self._runner = runner
        self.auditor = auditor  # runs after every other agent's run; set by the crew factory

    def run(self, agent: Agent, trigger: str, ctx: dict[str, Any], event: Event | None = None, audit: bool = True) -> RunOutcome:
        check_killswitch(self.session)
        ident = agent.identity
        site = ctx.get("site") or (event.site if event else "")
        run = AgentRun(id=str(ULID()), site=site, agent=ident.name, trigger=trigger, meta={"event_id": event.id if event else None})
        self.session.add(run)
        self.session.commit()
        meter = BudgetMeter(ident.budget)
        runner = self._runner or ToolRunner(self.session, site, f"crew:{ident.name}")
        actions: list[Action] = []
        denied: list[str] = []
        dropped: list[str] = []
        try:
            plan = agent.plan(event, ctx, self.session)
            allowed: list[Call] = []
            for call in plan.calls:
                if not ident.may_call(call.tool):
                    denied.append(call.tool)
                    log.warning("crew %s attempted %s which is not in its allow-list", ident.name, call.tool)
                    continue
                allowed.append(call)
            if event is not None:
                outcome = Policy(self.session).check(event, allowed, plan.confidence, ctx.get("lang", "en"))
                calls = outcome.calls
                dropped = [f"{c.tool}: {why}" for c, why in outcome.dropped]
            else:
                calls = allowed
            for call in calls:
                check_killswitch(self.session)  # cancel at the next tool boundary
                proposal = is_proposal(call.tool)
                a = Action(site=site, event_id=event.id if event else None, tool=call.tool, args=call.args, autonomous=not proposal,
                           status="proposed", reasoning=plan.rationale + (f" | evidence: {', '.join(plan.evidence[:6])}" if plan.evidence else ""),
                           confidence=plan.confidence, backend=f"crew:{ident.name}", agent=ident.name, run_id=run.id)
                self.session.add(a)
                self.session.commit()
                self.session.refresh(a)
                if not proposal:
                    res = runner.execute(call, action_id=a.id, ctx={"zone": (event.payload.get("zone") if event else None), "lang": ctx.get("lang", "en"),
                                                                   "clip_path": event.clip_path if event else None, "client_id": None})
                    meter.charge_call(res.cost_usd)
                    a.status = "executed" if res.ok else "failed"
                    a.result = res.output if res.ok else {"error": res.error}
                    a.decided_at, a.decided_by = datetime.now(UTC), f"crew:{ident.name}"
                    self.session.add(a)
                    self.session.commit()
                    self.session.refresh(a)
                else:
                    meter.charge_call(0.0)
                actions.append(a)
                self.bus.send(Message(run_id=run.id, from_agent=ident.name, to_agent="Auditor", schema="proposal",
                                      payload={"tool": call.tool, "args": call.args, "evidence": plan.evidence[:10], "rationale": plan.rationale[:800]}), ident)
            run.status = "ok"
        except AgentsDisabled:
            run.status = "killed"
        except BudgetExceeded as exc:
            run.status = "budget_exceeded"
            run.meta = {**(run.meta or {}), "breach": str(exc)}
        except Exception as exc:  # noqa: BLE001 — a failing agent never takes the API down
            log.exception("crew run %s failed", run.id)
            run.status = "error"
            run.meta = {**(run.meta or {}), "error": str(exc)[:300]}
        run.ended = datetime.now(UTC)
        run.tool_calls = meter.tool_calls
        run.cost_usd = round(meter.usd, 6)
        run.meta = {**(run.meta or {}), "denied": denied, "dropped": dropped, "seconds": round(meter.seconds, 3)}
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        try:  # live graph: one SSE message per finished run (never a tool call, never pixels)
            from ..bus import bus as sse_bus

            sse_bus.publish(site, "crew", {"run_id": run.id, "agent": ident.name, "trigger": trigger, "status": run.status,
                                           "tool_calls": run.tool_calls, "denied": denied, "actions": [a.id for a in actions]})
        except Exception:  # noqa: BLE001
            pass
        if run.status != "killed":
            try:
                self.bus.send(Message(run_id=run.id, from_agent=ident.name, to_agent="Auditor", schema="run_report",
                                      payload={"run_id": run.id, "agent": ident.name, "status": run.status, "tool_calls": run.tool_calls,
                                               "denied": denied, "dropped": dropped, "cost_usd": run.cost_usd}), ident)
            except Exception:  # noqa: BLE001
                log.exception("run_report could not be sent")
        outcome = RunOutcome(run=run, actions=actions, denied=denied, dropped=dropped)
        if audit and self.auditor is not None and ident.name != "Auditor":
            self.run(self.auditor, trigger=f"audit:{run.id}", ctx={**ctx, "site": site, "audited_run": run.id}, event=None, audit=False)
        return outcome

    def recent_runs(self, site: str, limit: int = 50) -> list[AgentRun]:
        return self.session.exec(select(AgentRun).where(AgentRun.site == site).order_by(AgentRun.started.desc()).limit(limit)).all()
