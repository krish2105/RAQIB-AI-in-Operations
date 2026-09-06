"""Crew factory and event dispatch. One Runtime, six agents, the Auditor after every run."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from ..agent.ops_agent import build_context
from ..config import settings
from ..models import Action, Event
from ..tz import ensure_utc
from .agents.analyst import Analyst
from .agents.auditor import Auditor
from .agents.floor_ops import FloorOps
from .agents.safety import Safety
from .agents.shelf_ops import ShelfOps
from .agents.workforce import Workforce
from .identity import AgentIdentity
from .killswitch import enabled
from .runtime import RunOutcome, Runtime

log = logging.getLogger(__name__)

AGENT_CLASSES = (FloorOps, ShelfOps, Workforce, Safety, Analyst, Auditor)
IDENTITIES: dict[str, AgentIdentity] = {c.identity.name: c.identity for c in AGENT_CLASSES}
KIND_TO_AGENT = {"queue_over": "FloorOps", "footfall_surge": "FloorOps", "shelf_gap": "ShelfOps"}


@dataclass
class Crew:
    runtime: Runtime
    agents: dict[str, Any]
    site: str

    def agent_for(self, event: Event) -> Any | None:
        if event.severity >= 3:
            return self.agents["Safety"]
        name = KIND_TO_AGENT.get(event.kind)
        return self.agents[name] if name else None

    def handle(self, event: Event) -> RunOutcome | None:
        agent = self.agent_for(event)
        if agent is None:
            return None
        ev = ensure_utc([event])[0]
        ctx = build_context(ev, self.runtime.session) | {"site": event.site, "max_tool_calls": agent.identity.budget.max_tool_calls}
        return self.runtime.run(agent, trigger=event.kind, ctx=ctx, event=event)


def build_crew(session: Session, site: str) -> Crew:
    agents = {c.identity.name: c() for c in AGENT_CLASSES}
    rt = Runtime(session, IDENTITIES, auditor=agents["Auditor"])
    return Crew(runtime=rt, agents=agents, site=site)


def dispatch(event: Event, session: Session) -> list[Action] | None:
    """Route an ingested event to the crew. None = not handled here (caller falls back to the Phase B path)."""
    if not settings.crew_enabled or not enabled(session):
        return None
    crew = build_crew(session, event.site)
    if crew.agent_for(event) is None:
        return None
    try:
        out = crew.handle(event)
    except Exception:  # noqa: BLE001 — the caller's deterministic path still runs
        log.exception("crew dispatch failed for %s", event.id)
        return None
    if out is None or out.run.status == "killed":
        return None
    return out.actions
