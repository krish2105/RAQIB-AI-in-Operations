"""Auditor: after every run. Checks the run against the policies and flags it; quarantines suspicious memories.

Findings: tool_misuse (a denied tool), budget_anomaly (breach or > 80 % of the call budget), disagreement_spike
(VLM disagreement rate > 0.5 over the last 20 opinions), policy_drop (Policy dropped a call from the agent).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from ...agent.tools import Call
from ...models import AgentRun, Event, Memory, Opinion
from ..identity import AgentIdentity
from ..memory import _INJ
from ..runtime import Plan


class Auditor:
    identity = AgentIdentity(name="Auditor", role="Independent check on every run", allowed_tools=frozenset({"quarantine_memory", "flag_run"}))
    triggers = ["after_every_run"]

    def plan(self, event: Event | None, ctx: dict[str, Any], session: Session) -> Plan:
        run_id = ctx.get("audited_run")
        calls: list[Call] = []
        notes: list[str] = []
        run = session.get(AgentRun, run_id) if run_id else None
        if run is not None:
            meta = run.meta or {}
            if meta.get("denied"):
                calls.append(Call("flag_run", {"run_id": run.id, "finding": "tool_misuse", "note": f"{run.agent} attempted {', '.join(meta['denied'])}"[:400]}, "denied tool"))
            if run.status == "budget_exceeded" or run.tool_calls > 0.8 * ctx.get("max_tool_calls", 6):
                calls.append(Call("flag_run", {"run_id": run.id, "finding": "budget_anomaly", "note": f"status={run.status} tool_calls={run.tool_calls} usd={run.cost_usd}"[:400]}, "budget"))
            if meta.get("dropped"):
                notes.append(f"policy dropped: {meta['dropped']}")
            ops = session.exec(select(Opinion).where(Opinion.site == run.site, Opinion.status == "ok").order_by(Opinion.ts.desc()).limit(20)).all()
            if len(ops) >= 5 and sum(1 for o in ops if o.disagreement) / len(ops) > 0.5:
                calls.append(Call("flag_run", {"run_id": run.id, "finding": "disagreement_spike", "note": f"VLM disagreement rate {sum(1 for o in ops if o.disagreement)}/{len(ops)}"}, "vlm"))
        site = ctx.get("site")
        if site:
            for m in session.exec(select(Memory).where(Memory.site == site, Memory.quarantined.is_(False))).all():
                if any(rx.search(m.value) for rx in _INJ):
                    calls.append(Call("quarantine_memory", {"memory_id": int(m.id), "reason": "injection pattern found on audit"}, "memory"))
        text = f"Auditor checked run {run_id}: " + (", ".join(c.args.get("finding", c.tool) for c in calls) if calls else "no findings")
        return Plan(calls=calls, rationale=text, confidence=0.9, evidence=[f"run:{run_id}"] if run_id else [], notes=notes)
