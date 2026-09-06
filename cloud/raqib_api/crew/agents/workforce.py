"""Workforce: daily 06:00 -> propose_staffing_plan from the MILP with rationale and last week's approval history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from ...agent.tools import Call
from ...models import Action, Event, Site
from ...ops_theory import slot_rates, tills_for_target_rho
from ...tz import ensure_utc
from ...workforce import staffing_plan
from ..identity import AgentIdentity
from ..runtime import Plan
from .base import rationale


class Workforce:
    identity = AgentIdentity(name="Workforce", role="Staffing plan", allowed_tools=frozenset({"propose_staffing_plan"}))
    triggers = ["daily_0600"]

    def plan(self, event: Event | None, ctx: dict[str, Any], session: Session) -> Plan:
        site = ctx["site"]
        s = session.get(Site, site)
        now = ctx.get("now") or datetime.now(UTC)
        since = now - timedelta(days=7)
        events = ensure_utc(session.exec(select(Event).where(Event.site == site, Event.ts >= since.replace(tzinfo=None)).order_by(Event.ts)).all())
        slots = slot_rates(events, tills_open=s.tills if s else 3)
        if not slots:
            return Plan(calls=[], rationale="Workforce: not enough history for a staffing plan (no slots in the last 7 days)")
        mus = [x.mu_per_h for x in slots if x.served > 0]
        mu = sum(mus) / len(mus) if mus else 30.0
        lam = [x.lam_per_h for x in slots][-96:]
        ceiling = max(s.tills if s else 3, 3, tills_for_target_rho(max(lam), mu))
        plan = staffing_plan(lam, mu, max_tills=ceiling, baseline_tills=s.tills if s else 3)
        hist = session.exec(select(Action).where(Action.site == site, Action.tool.in_(["propose_staffing_plan", "propose_open_till"]), Action.created_at >= since.replace(tzinfo=None))).all()
        approved = sum(1 for a in hist if a.status == "executed" and a.decided_by not in (None, "agent") and not str(a.decided_by).startswith("crew"))
        day = now.date().isoformat()
        fallback = (f"For {day} the MILP plan peaks at {max(plan.tills)} tills and uses {plan.staff_hours:.1f} staff-hours against "
                    f"{plan.baseline_staff_hours:.1f} flat, keeping ρ ≤ 0.85 in every slot. Last week {approved} of {len(hist)} staffing proposals were approved.")
        text = rationale("workforce", fallback, fallback, ctx.get("lang", "en"))
        call = Call("propose_staffing_plan", {"day": day, "tills": [int(c) for c in plan.tills], "staff_hours": round(plan.staff_hours, 2),
                                             "savings_hours": round(plan.baseline_staff_hours - plan.staff_hours, 2), "rationale": text[:600]}, "daily plan")
        return Plan(calls=[call], rationale=text, confidence=0.7, evidence=[f"slots:{len(slots)}", f"approved_last_week:{approved}/{len(hist)}"])
