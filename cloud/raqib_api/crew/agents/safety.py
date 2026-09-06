"""Safety (MUSHRIF): severity 3 -> escalate + alert (+ work order) with the clip and the PPE trend."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlmodel import Session, select

from ...agent.tools import Call
from ...models import Event
from ..identity import AgentIdentity
from ..runtime import Plan
from .base import event_evidence, rationale


class Safety:
    identity = AgentIdentity(name="Safety", role="Severity-3 safety events", allowed_tools=frozenset({"escalate", "send_alert", "create_work_order"}))
    triggers = ["severity_3"]

    def plan(self, event: Event | None, ctx: dict[str, Any], session: Session) -> Plan:
        if event is None:
            return Plan(calls=[], rationale="no event")
        p = event.payload
        zone = p.get("zone", "-")
        lang = ctx.get("lang", "en")
        since = event.ts - timedelta(days=7)
        week = session.exec(select(Event).where(Event.site == event.site, Event.kind.in_(["ppe_violation", "zone_breach"]), Event.ts >= since.replace(tzinfo=None))).all()
        calls = [
            Call("escalate", {"event_id": event.id, "to_role": "safety_officer", "note": f"{event.kind} in {zone} on {event.camera} (rule {event.rule_id})"}, "severity 3"),
            Call("send_alert", {"channel": "webhook", "lang": lang, "template": event.kind if event.kind in ("zone_breach", "ppe_violation", "machine_stopped") else "escalation",
                                "vars": {"zone": zone, "camera": event.camera, "time": event.ts.strftime("%H:%M")}}, "immediate alert"),
        ]
        if p.get("machine_id"):
            calls.append(Call("create_work_order", {"machine_id": str(p["machine_id"]), "summary": f"Safety stop after {event.kind} at {p['machine_id']}", "severity": 3}, "safety work order"))
        fallback = (f"Severity-3 {event.kind} in {zone} on {event.camera}; the escalation to the safety officer and the alert are mandatory and carry the clip. "
                    f"This site has had {len(week)} PPE or zone events in the last 7 days.")
        return Plan(calls=calls, rationale=rationale("safety", fallback, fallback, lang), confidence=float(p.get("confidence", 0.8) or 0.8),
                    evidence=event_evidence(event) + [f"trend_7d:{len(week)}"])
