"""ShelfOps: shelf_gap (and hourly) -> create_restock_task with OSA impact; flag_merchandising on repeats."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlmodel import Session, select

from ...agent.tools import Call
from ...models import Event
from ..identity import AgentIdentity
from ..runtime import Plan
from .base import event_evidence, rationale


class ShelfOps:
    identity = AgentIdentity(name="ShelfOps", role="On-shelf availability", allowed_tools=frozenset({"create_restock_task", "flag_merchandising"}))
    triggers = ["shelf_gap", "hourly"]

    def plan(self, event: Event | None, ctx: dict[str, Any], session: Session) -> Plan:
        if event is None:
            return Plan(calls=[], rationale="hourly sweep: nothing to restock")
        p = event.payload
        shelf = str(p.get("shelf_id", p.get("zone", "?")))
        product = str(p.get("product") or "product")
        empty = float(p.get("empty_ratio") or 0.0)
        sustained = float(p.get("sustained_s") or 300)
        osa_impact = round(min(100.0, empty * 100 * (sustained / 3600)), 1)  # % of an hour lost on this shelf
        calls = [Call("create_restock_task", {"shelf_id": shelf, "product": product, "osa_impact_pct": osa_impact,
                                              "summary": f"Restock shelf {shelf} ({product}), empty ratio {empty:.2f} for {int(sustained)} s"}, "shelf gap")]
        since = event.ts - timedelta(days=1)
        repeats = session.exec(select(Event).where(Event.site == event.site, Event.kind == "shelf_gap", Event.ts >= since.replace(tzinfo=None), Event.ts < event.ts.replace(tzinfo=None))).all()
        same = [e for e in repeats if str(e.payload.get("shelf_id")) == shelf]
        if len(same) >= 3:
            calls.append(Call("flag_merchandising", {"shelf_id": shelf, "reason": f"{len(same)} gaps on {shelf} in 24 h"}, "repeated gaps"))
        fallback = f"Shelf {shelf} ({product}) has been {empty:.0%} empty for {int(sustained)} s, about {osa_impact}% of an hour of availability lost, so ShelfOps raises a restock task."
        if len(same) >= 3:
            fallback += f" With {len(same)} gaps in 24 hours it also flags the bay for a merchandising check."
        facts = f"shelf={shelf} product={product} empty={empty:.2f} sustained={sustained:.0f}s repeats_24h={len(same)} osa_impact={osa_impact}%"
        return Plan(calls=calls, rationale=rationale("shelf_ops", facts, fallback, ctx.get("lang", "en")), confidence=float(p.get("confidence", 0.75) or 0.75),
                    evidence=event_evidence(event) + [f"event:{e.id}" for e in same[:5]])
