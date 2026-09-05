"""Agent backends: DryRun (deterministic policy table) and Claude (Anthropic tool use).

Both return a Decision of allow-listed Calls. The Policy layer runs after either
backend, so a misbehaving model cannot bypass the rules.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ..config import settings
from ..models import Event
from .tools import Call, anthropic_tool_defs

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

# Approximate list prices per million tokens, used for cost logging only.
PRICES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-1": (15.0, 75.0),
}


@dataclass
class Decision:
    calls: list[Call]
    rationale: str
    confidence: float
    cost_usd: float = 0.0
    backend: str = "dryrun"
    raw: dict[str, Any] = field(default_factory=dict)


class AgentBackend(Protocol):
    name: str

    def decide(self, event: Event, context: dict[str, Any]) -> Decision: ...


class DryRunBackend:
    """Deterministic mapping from (kind, severity, rho) to tool calls, with a written rationale."""

    name = "dryrun"

    def decide(self, event: Event, context: dict[str, Any]) -> Decision:
        p = event.payload
        conf = float(p.get("confidence", 0.8) or 0.8)
        lang = context.get("lang", "en")
        rho = float(context.get("rho") or 0.0)
        calls: list[Call] = []
        why: list[str] = []
        zone = p.get("zone", "-")
        if event.kind == "queue_over":
            calls.append(Call("send_alert", {"channel": "webhook", "lang": lang, "template": "queue_over",
                                             "vars": {"zone": zone, "count": p.get("count"), "time": event.ts.strftime("%H:%M")}},
                              "queue over threshold: tell the floor manager"))
            why.append(f"{p.get('count')} people in {zone} for {p.get('sustained_s')} s (rule R10)")
            if rho > 0.85:
                calls.append(Call("propose_open_till", {"till": int(context.get("next_till", 2)), "window": context.get("window", "now+30m"), "rho": round(rho, 3)},
                                  f"utilisation rho={rho:.2f} > 0.85 (M/M/c)"))
                why.append(f"M/M/{context.get('tills', 1)} utilisation {rho:.2f} exceeds 0.85, so an extra till is justified")
            else:
                why.append(f"utilisation {rho:.2f} <= 0.85, so no till change; alert only")
        elif event.kind == "shelf_gap":
            shelf = str(p.get("shelf_id", zone))
            calls.append(Call("create_work_order", {"machine_id": shelf, "summary": f"Restock shelf {shelf} ({p.get('product') or 'product'}), empty ratio {p.get('empty_ratio')}", "severity": 1},
                              "restock task for the gap"))
            why.append(f"shelf {shelf} empty ratio {p.get('empty_ratio')} for {p.get('sustained_s')} s (rule R11)")
        elif event.kind == "machine_stopped":
            mid = str(p.get("machine_id", "?"))
            start = event.ts.timestamp() - float(p.get("stopped_s", 0))
            calls.append(Call("create_work_order", {"machine_id": mid, "summary": f"Machine {mid} stopped for {round(float(p.get('stopped_s', 0))/60,1)} min during scheduled run", "severity": 2},
                              "unplanned stop needs a ticket"))
            calls.append(Call("log_downtime", {"machine_id": mid, "start": datetime.fromtimestamp(start, UTC).isoformat(), "end": event.ts.isoformat(), "reason": "unplanned stop detected by camera"},
                              "record downtime for MTBF"))
            why.append(f"machine {mid} stopped {p.get('stopped_s')} s (rule R03)")
        elif event.kind in ("zone_breach", "ppe_violation"):
            calls.append(Call("escalate", {"event_id": event.id, "to_role": "safety_officer", "note": f"{event.kind} in {zone} on {event.camera}"},
                              "severity 3 safety event"))
            calls.append(Call("send_alert", {"channel": "webhook", "lang": lang, "template": event.kind, "vars": {"zone": zone, "camera": event.camera, "time": event.ts.strftime("%H:%M")}},
                              "immediate alert"))
            why.append(f"{event.kind} in {zone} (rule {event.rule_id}), severity 3")
        if conf < 0.6:
            why.append(f"confidence {conf:.2f} is low, asking for human review")
        rationale = "; ".join(why) or f"no action for {event.kind}"
        return Decision(calls=calls, rationale=rationale, confidence=conf, backend=self.name)


class ClaudeBackend:
    """Anthropic tool-use. Inputs are wrapped as untrusted data; outputs go through Policy."""

    name = "claude"

    def __init__(self, model: str | None = None, client: Any | None = None) -> None:
        self.model = model or settings.agent_model
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.client = client
        self.system = (PROMPTS / "ops_agent.md").read_text()

    def decide(self, event: Event, context: dict[str, Any]) -> Decision:
        payload = {"event": {"id": event.id, "site": event.site, "camera": event.camera, "ts": event.ts.isoformat(),
                             "kind": event.kind, "severity": event.severity, "rule_id": event.rule_id, "payload": event.payload},
                   "context": context}
        user = ("<untrusted_event_data>\n" + json.dumps(payload, default=str) + "\n</untrusted_event_data>\n"
                "Decide the tool calls. Reply with tool calls and one short rationale sentence citing the rule and confidence.")
        resp = self.client.messages.create(
            model=self.model, max_tokens=800, system=self.system, tools=anthropic_tool_defs(),
            messages=[{"role": "user", "content": user}],
        )
        calls: list[Call] = []
        text = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                calls.append(Call(block.name, dict(block.input), "model"))
            elif getattr(block, "type", None) == "text":
                text.append(block.text)
        usage = getattr(resp, "usage", None)
        cost = 0.0
        if usage is not None:
            pin, pout = PRICES.get(self.model, (3.0, 15.0))
            cost = (usage.input_tokens * pin + usage.output_tokens * pout) / 1e6
        conf = float(event.payload.get("confidence", 0.8) or 0.8)
        return Decision(calls=calls, rationale=" ".join(text).strip() or "model returned tool calls only",
                        confidence=conf, cost_usd=cost, backend=self.name,
                        raw={"stop_reason": getattr(resp, "stop_reason", None)})


def make_backend(name: str | None = None) -> AgentBackend:
    name = name or settings.agent_backend
    if name == "claude" and settings.anthropic_api_key:
        return ClaudeBackend()
    if name == "claude":
        log.warning("AGENT_BACKEND=claude but ANTHROPIC_API_KEY is empty; falling back to dryrun")
    return DryRunBackend()
