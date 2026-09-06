"""Bounded autonomy. The Policy sits between the backend's decision and execution.

Rules (spec Section 5), each enforced here and tested:
  P1 severity-3 events always escalate AND alert, regardless of what the backend said.
  P2 the agent cannot suppress or downgrade severity 3 (any call whose args carry a lower
     severity for a sev-3 event is rewritten to 3; "no action" is overruled by P1).
  P3 at most one work order per machine/shelf per 4 hours unless a human overrides.
  P4 propose_open_till must cite rho > 0.85 or it is dropped.
  P5 confidence < 0.6 adds request_human_review instead of autonomous side effects
     (escalation for sev 3 still happens).
  P6 anything not in the allow-list is dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from ..models import Action, Event
from .tools import (
    AUTONOMOUS_TOOLS,
    PROPOSAL_TOOLS,
    TOOL_SCHEMAS,
    Call,
    ToolValidationError,
    validate_call,
)

WORK_ORDER_COOLDOWN = timedelta(hours=4)
TICKET_TOOLS = ("create_work_order", "create_restock_task")  # both raise one tracker ticket
RHO_THRESHOLD = 0.85
REVIEW_CONFIDENCE = 0.6

ROLE_FOR_KIND = {
    "zone_breach": "safety_officer",
    "ppe_violation": "safety_officer",
    "machine_stopped": "maintenance",
    "queue_over": "floor_manager",
    "shelf_gap": "floor_manager",
}


@dataclass
class PolicyOutcome:
    calls: list[Call]
    dropped: list[tuple[Call, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Policy:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session
        self._site_policy: dict[str, dict] = {}

    def _p(self, site: str) -> dict:
        """v2: admin-edited thresholds per site (routers/policy.py); defaults when unset or no session."""
        if site not in self._site_policy:
            vals = {"rho_threshold": RHO_THRESHOLD, "review_confidence": REVIEW_CONFIDENCE, "work_order_cooldown_h": WORK_ORDER_COOLDOWN.total_seconds() / 3600}
            if self.session is not None:
                try:
                    from ..routers.policy import load_policy

                    vals.update(load_policy(self.session, site))
                except Exception:  # noqa: BLE001 — never let a policy read break a decision
                    pass
            self._site_policy[site] = vals
        return self._site_policy[site]

    def check(self, event: Event, proposed: list[Call], confidence: float, lang: str = "en") -> PolicyOutcome:
        out = PolicyOutcome(calls=[])
        seen_tools: set[str] = set()
        review_conf = float(self._p(event.site)["review_confidence"])
        for call in proposed:
            reason = self._reject_reason(event, call)
            if reason:
                out.dropped.append((call, reason))
                continue
            if event.severity == 3 and "severity" in call.args and int(call.args["severity"]) < 3:
                call.args["severity"] = 3
                out.notes.append("P2: severity restored to 3")
            if confidence < review_conf and call.tool in AUTONOMOUS_TOOLS - {"escalate", "send_alert", "request_human_review"}:
                out.dropped.append((call, f"P5: confidence {confidence:.2f} < {review_conf}"))
                continue
            out.calls.append(call)
            seen_tools.add(call.tool)

        if event.severity == 3:
            role = ROLE_FOR_KIND.get(event.kind, "shift_supervisor")
            if "escalate" not in seen_tools:
                out.calls.insert(0, Call("escalate", {"event_id": event.id, "to_role": role,
                                                       "note": f"{event.kind} on {event.camera} (rule {event.rule_id})"},
                                         "P1: severity 3 always escalates"))
                out.notes.append("P1: escalation added")
            if "send_alert" not in seen_tools:
                out.calls.insert(1, Call("send_alert", {"channel": "webhook", "lang": lang, "template": event.kind if event.kind in TOOL_SCHEMAS["send_alert"]["input_schema"]["properties"]["template"]["enum"] else "escalation",
                                                         "vars": _alert_vars(event)}, "P1: severity 3 always alerts"))
                out.notes.append("P1: alert added")
        if confidence < review_conf and "request_human_review" not in seen_tools:
            out.calls.append(Call("request_human_review", {"event_id": event.id,
                                                            "question": f"Confirm {event.kind} (model confidence {confidence:.2f})"},
                                  "P5: low confidence"))
        return out

    def _reject_reason(self, event: Event, call: Call) -> str | None:
        if call.tool not in TOOL_SCHEMAS:
            return "P6: tool not allow-listed"
        try:
            call.args = validate_call(call.tool, call.args)
        except ToolValidationError as exc:
            return f"schema: {exc}"
        rho_thr = float(self._p(event.site)["rho_threshold"])
        if call.tool == "propose_open_till" and float(call.args.get("rho", 0)) <= rho_thr:
            return f"P4: rho {call.args.get('rho')} <= {rho_thr}"
        if call.tool in TICKET_TOOLS and self.session is not None:
            # P3 covers every ticket tool (a restock task is a work order in the tracker), keyed by machine/shelf id.
            # Compare on the *event* clock, not wall-clock: replayed history and live events must behave the same.
            target = _ticket_target(call.tool, call.args)
            cooldown = timedelta(hours=float(self._p(event.site)["work_order_cooldown_h"]))
            ev_ts = _naive(event.ts)
            since = ev_ts - cooldown
            q = (select(Action, Event.ts).join(Event, Event.id == Action.event_id, isouter=True)
                 .where(Action.site == event.site, Action.tool.in_(list(TICKET_TOOLS)),
                        Action.status.in_(["executed", "approved", "proposed"])))
            for a, ts in self.session.exec(q).all():
                when = _naive(ts or a.created_at)
                if since <= when <= ev_ts + cooldown and _ticket_target(a.tool, a.args) == target \
                        and not (a.result or {}).get("human_override") and a.event_id != event.id:
                    return f"P3: work order for {target} already raised at {when.isoformat()}"
        return None


def _ticket_target(tool: str, args: dict[str, Any]) -> str:
    return str(args.get("shelf_id") if tool == "create_restock_task" else args.get("machine_id"))


def _naive(ts: datetime) -> datetime:
    return ts.astimezone(UTC).replace(tzinfo=None) if ts.tzinfo else ts


def is_proposal(tool: str) -> bool:
    return tool in PROPOSAL_TOOLS


def _alert_vars(event: Event) -> dict[str, Any]:
    p = event.payload
    return {
        "camera": event.camera,
        "zone": p.get("zone", "-"),
        "count": p.get("count", "-"),
        "shelf_id": p.get("shelf_id", "-"),
        "machine_id": p.get("machine_id", "-"),
        "minutes": round(float(p.get("stopped_s", p.get("sustained_s", 0))) / 60, 1),
        "time": event.ts.strftime("%H:%M") if isinstance(event.ts, datetime) else str(event.ts),
    }
