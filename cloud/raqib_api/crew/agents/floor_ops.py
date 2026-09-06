"""FloorOps: queue_over / footfall_surge -> propose_open_till (ρ > 0.85) and a templated alert, with precedent."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from ...agent.tools import Call
from ...models import Event
from ..identity import AgentIdentity
from ..runtime import Plan
from .base import event_evidence, precedent, rationale


class FloorOps:
    identity = AgentIdentity(name="FloorOps", role="Queues and footfall on the floor", allowed_tools=frozenset({"propose_open_till", "send_alert"}))
    triggers = ["queue_over", "footfall_surge"]

    def plan(self, event: Event | None, ctx: dict[str, Any], session: Session) -> Plan:
        if event is None:
            return Plan(calls=[], rationale="no event")
        p = event.payload
        rho = float(ctx.get("rho") or 0.0)
        wq = ctx.get("wq_min")
        zone = p.get("zone", "-")
        lang = ctx.get("lang", "en")
        calls = [Call("send_alert", {"channel": "webhook", "lang": lang, "template": "queue_over",
                                    "vars": {"zone": zone, "count": p.get("count"), "time": event.ts.strftime("%H:%M")}}, "queue over limit")]
        prec_text, prec_ids = precedent(event.site, "Biggest queue this week", session)
        facts = f"queue of {p.get('count')} in {zone} for {p.get('sustained_s')} s; rho={rho:.2f}; Wq={wq} min; precedent: {prec_text[:200]}"
        if rho > 0.85:
            calls.append(Call("propose_open_till", {"till": int(ctx.get("next_till", 2)), "window": ctx.get("window", "now+30m"), "rho": round(rho, 3)},
                              f"rho {rho:.2f} > 0.85"))
            fallback = f"Utilisation ρ={rho:.2f} exceeds 0.85 with {p.get('count')} waiting in {zone}, so FloorOps proposes opening till {ctx.get('next_till', 2)}."
        else:
            fallback = f"Utilisation ρ={rho:.2f} is at or below 0.85, so FloorOps alerts the floor manager and proposes no till change."
        if prec_text:
            fallback += " Precedent from this week's records is cited."
        return Plan(calls=calls, rationale=rationale("floor_ops", facts, fallback, lang), confidence=float(p.get("confidence", 0.8) or 0.8),
                    evidence=event_evidence(event) + prec_ids)
