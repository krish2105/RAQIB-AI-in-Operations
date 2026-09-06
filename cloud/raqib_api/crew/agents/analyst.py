"""Analyst: weekly and on demand from Ask. Read-only: no tools, ever. Produces cited narrative notes."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from ...models import Event
from ..identity import AgentIdentity
from ..runtime import Plan


class Analyst:
    identity = AgentIdentity(name="Analyst", role="Narrative and anomalies (read-only)", allowed_tools=frozenset())
    triggers = ["weekly", "ask"]

    def plan(self, event: Event | None, ctx: dict[str, Any], session: Session) -> Plan:
        from ...agent.weekly_agent import narrative_sections

        sections = narrative_sections(ctx["site"], session, ctx.get("lang", "en"), ctx.get("now"))
        notes = [f"{s['title']}: {s['answer'][:200]}" for s in sections]
        evidence = [c["chunk_id"] for s in sections for c in s["citations"]][:20]
        text = " ".join(s["answer"] for s in sections) or "Analyst: nothing indexed yet, no narrative."
        return Plan(calls=[], rationale=text[:2000], confidence=0.6, evidence=[f"chunk:{c}" for c in evidence], notes=notes)
