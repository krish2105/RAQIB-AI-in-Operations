"""Allow-listed agent tools with strict JSON schemas, validation, and execution.

The agent may only emit calls to the tools in TOOL_SCHEMAS. Every call is
validated with `validate_call` before anything happens, and every execution
is written to `tool_calls` with latency and cost. Side effects go through
`ToolRunner`, which is the single place that talks to the outside world.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
from sqlmodel import Session, select

from .. import greenlam
from ..config import settings
from ..models import ToolCall
from ..notify import render_alert

log = logging.getLogger(__name__)

LANGS = ("en", "hi", "ar")
CHANNELS = ("console", "webhook", "whatsapp", "push")
ROLES = ("floor_manager", "store_manager", "safety_officer", "maintenance", "shift_supervisor")

# Tools that may run without a human (subject to Policy). Others are proposals.
AUTONOMOUS_TOOLS = {"create_work_order", "send_alert", "log_downtime", "escalate", "request_human_review",
                    # v2 crew tools
                    "create_restock_task", "flag_merchandising", "quarantine_memory", "flag_run"}
PROPOSAL_TOOLS = {"propose_staffing_change", "propose_open_till", "propose_maintenance_window",
                  # v2 crew tools
                  "propose_staffing_plan"}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "create_work_order": {
        "description": "Raise a work order / restock task in the tracker. Autonomous for severity <= 2.",
        "input_schema": {
            "type": "object",
            "properties": {
                "machine_id": {"type": "string", "description": "machine id (factory) or shelf id (retail)"},
                "summary": {"type": "string", "minLength": 5, "maxLength": 240},
                "severity": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "required": ["machine_id", "summary", "severity"],
            "additionalProperties": False,
        },
    },
    "send_alert": {
        "description": "Send a templated alert. Templates only; no free text reaches WhatsApp.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "enum": list(CHANNELS)},
                "lang": {"type": "string", "enum": list(LANGS)},
                "template": {"type": "string", "enum": ["queue_over", "shelf_gap", "zone_breach", "ppe_violation", "machine_stopped", "escalation"]},
                "vars": {"type": "object"},
            },
            "required": ["channel", "lang", "template", "vars"],
            "additionalProperties": False,
        },
    },
    "log_downtime": {
        "description": "Record a downtime interval for a machine.",
        "input_schema": {
            "type": "object",
            "properties": {
                "machine_id": {"type": "string"},
                "start": {"type": "string", "format": "date-time"},
                "end": {"type": "string", "format": "date-time"},
                "reason": {"type": "string", "maxLength": 240},
            },
            "required": ["machine_id", "start", "end", "reason"],
            "additionalProperties": False,
        },
    },
    "propose_staffing_change": {
        "description": "Proposal only. Suggest moving staff to/from a zone for a window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zone": {"type": "string"},
                "delta": {"type": "integer", "minimum": -5, "maximum": 5},
                "window": {"type": "string", "description": "e.g. 17:00-19:00"},
            },
            "required": ["zone", "delta", "window"],
            "additionalProperties": False,
        },
    },
    "propose_open_till": {
        "description": "Proposal only. Open an additional till; must cite utilisation rho > 0.85.",
        "input_schema": {
            "type": "object",
            "properties": {
                "till": {"type": "integer", "minimum": 1, "maximum": 20},
                "window": {"type": "string"},
                "rho": {"type": "number", "minimum": 0},
            },
            "required": ["till", "window", "rho"],
            "additionalProperties": False,
        },
    },
    "propose_maintenance_window": {
        "description": "Proposal only. Suggest a maintenance window for a machine.",
        "input_schema": {
            "type": "object",
            "properties": {"machine_id": {"type": "string"}, "window": {"type": "string"}},
            "required": ["machine_id", "window"],
            "additionalProperties": False,
        },
    },
    "escalate": {
        "description": "Escalate an event to a human role. Always attaches the clip. Mandatory for severity 3.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "to_role": {"type": "string", "enum": list(ROLES)},
                "note": {"type": "string", "maxLength": 400},
            },
            "required": ["event_id", "to_role", "note"],
            "additionalProperties": False,
        },
    },
    "request_human_review": {
        "description": "Ask a human to confirm an uncertain detection (confidence < 0.6).",
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}, "question": {"type": "string", "maxLength": 400}},
            "required": ["event_id", "question"],
            "additionalProperties": False,
        },
    },
    # ---- v2 crew tools (Phase G). Same validation, same runner, same policy. ----
    "create_restock_task": {
        "description": "ShelfOps: raise a restock task for a shelf with its on-shelf-availability impact. Autonomous.",
        "input_schema": {
            "type": "object",
            "properties": {
                "shelf_id": {"type": "string"},
                "product": {"type": "string", "maxLength": 120},
                "osa_impact_pct": {"type": "number", "minimum": 0, "maximum": 100},
                "summary": {"type": "string", "minLength": 5, "maxLength": 240},
            },
            "required": ["shelf_id", "summary"],
            "additionalProperties": False,
        },
    },
    "flag_merchandising": {
        "description": "ShelfOps: flag a shelf for a merchandising check (repeated gaps, planogram drift). Autonomous, no side effect beyond a record.",
        "input_schema": {
            "type": "object",
            "properties": {"shelf_id": {"type": "string"}, "reason": {"type": "string", "maxLength": 240}},
            "required": ["shelf_id", "reason"],
            "additionalProperties": False,
        },
    },
    "propose_staffing_plan": {
        "description": "Workforce: proposal only. A per-slot till plan from the MILP with its rationale and history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "day": {"type": "string"},
                "tills": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 20}, "maxItems": 200},
                "staff_hours": {"type": "number", "minimum": 0},
                "savings_hours": {"type": "number"},
                "rationale": {"type": "string", "maxLength": 600},
            },
            "required": ["day", "tills", "staff_hours", "rationale"],
            "additionalProperties": False,
        },
    },
    "quarantine_memory": {
        "description": "Auditor: quarantine an agent memory entry (it stops entering prompts until a human clears it).",
        "input_schema": {
            "type": "object",
            "properties": {"memory_id": {"type": "integer", "minimum": 1}, "reason": {"type": "string", "maxLength": 240}},
            "required": ["memory_id", "reason"],
            "additionalProperties": False,
        },
    },
    "flag_run": {
        "description": "Auditor: flag an agent run for review (tool misuse, budget anomaly, disagreement spike).",
        "input_schema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}, "finding": {"type": "string", "enum": ["tool_misuse", "budget_anomaly", "disagreement_spike", "policy_drop", "other"]},
                           "note": {"type": "string", "maxLength": 400}},
            "required": ["run_id", "finding", "note"],
            "additionalProperties": False,
        },
    },
}


class ToolValidationError(ValueError):
    pass


@dataclass
class Call:
    tool: str
    args: dict[str, Any]
    rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "args": self.args, "rationale": self.rationale}


@dataclass
class ToolResult:
    ok: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0


_JSON_TO_PY = {"string": str, "integer": int, "number": float, "boolean": bool, "object": dict, "array": list}


def _pydantic_model(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    props = schema["properties"]
    required = set(schema.get("required", []))
    for key, spec in props.items():
        typ = _JSON_TO_PY.get(spec.get("type", "string"), Any)
        kwargs: dict[str, Any] = {}
        if "minimum" in spec:
            kwargs["ge"] = spec["minimum"]
        if "maximum" in spec:
            kwargs["le"] = spec["maximum"]
        if "minLength" in spec:
            kwargs["min_length"] = spec["minLength"]
        if "maxLength" in spec:
            kwargs["max_length"] = spec["maxLength"]
        if "enum" in spec:
            kwargs["pattern"] = "^(" + "|".join(spec["enum"]) + ")$"
        default = ... if key in required else None
        fields[key] = (typ if key in required else typ | None, Field(default, **kwargs))
    return create_model(f"{name}_args", __config__=ConfigDict(extra="forbid"), **fields)  # type: ignore[call-overload]


_MODELS = {name: _pydantic_model(name, s["input_schema"]) for name, s in TOOL_SCHEMAS.items()}


def validate_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Return normalised args or raise ToolValidationError. Unknown tool = error."""
    if name not in TOOL_SCHEMAS:
        raise ToolValidationError(f"tool {name!r} is not allow-listed")
    try:
        m = _MODELS[name].model_validate(args)
    except ValidationError as exc:
        raise ToolValidationError(f"{name}: {exc.errors()[0]['msg']} at {list(exc.errors()[0]['loc'])}") from exc
    return {k: v for k, v in m.model_dump().items() if v is not None}


def anthropic_tool_defs() -> list[dict[str, Any]]:
    return [{"name": n, "description": s["description"], "input_schema": s["input_schema"]} for n, s in TOOL_SCHEMAS.items()]


class ToolRunner:
    """Executes validated calls with side effects and logs them."""

    def __init__(self, session: Session, site: str, backend: str, http: httpx.Client | None = None) -> None:
        self.session = session
        self.site = site
        self.backend = backend
        self.http = http or httpx.Client(timeout=10.0)

    def execute(self, call: Call, action_id: int | None = None, ctx: dict[str, Any] | None = None) -> ToolResult:
        t0 = time.perf_counter()
        try:
            args = validate_call(call.tool, call.args)
            handler = getattr(self, f"_do_{call.tool}")
            out = handler(args, ctx or {})
            res = ToolResult(ok=True, output=out)
        except Exception as exc:  # noqa: BLE001 — recorded, never raised into the request
            log.warning("tool %s failed: %s", call.tool, exc)
            res = ToolResult(ok=False, error=str(exc))
        res.latency_ms = (time.perf_counter() - t0) * 1000
        self.session.add(ToolCall(site=self.site, action_id=action_id, tool=call.tool, input=call.args,
                                  output=res.output or None, ok=res.ok, error=res.error, latency_ms=res.latency_ms,
                                  cost_usd=res.cost_usd, backend=self.backend))
        self.session.commit()
        return res

    # ---- handlers -----------------------------------------------------------------

    def _do_create_work_order(self, a: dict, ctx: dict) -> dict:
        client = greenlam.client_from_settings(self.http)
        if client is None:
            return {"recorded": "local", "machine_id": a["machine_id"], "summary": a["summary"], "severity": a["severity"],
                    "note": "GREENLAM_URL not configured; work order stored locally"}
        try:
            machine_id = int(a["machine_id"])
        except ValueError:
            machine_id = greenlam.machine_id_for_shelf(a["machine_id"])
        return client.raise_ticket(
            machine_id=machine_id,
            description=a["summary"],
            priority=greenlam.priority_for_severity(a["severity"]),
            location=ctx.get("zone"),
            client_id=ctx.get("client_id"),
        )

    def _do_send_alert(self, a: dict, ctx: dict) -> dict:
        text = render_alert(a["template"], a["lang"], a["vars"])
        delivered = ["console"]
        log.info("ALERT[%s/%s] %s", a["channel"], a["lang"], text)
        if a["channel"] in ("webhook", "whatsapp", "push") and settings.alert_webhook_url:
            r = self.http.post(settings.alert_webhook_url, json={"text": text, "channel": a["channel"], "lang": a["lang"], "site": self.site})
            r.raise_for_status()
            delivered.append(a["channel"])
        out: dict[str, Any] = {"text": text, "delivered": delivered}
        if a["channel"] == "whatsapp":  # v2: approved templates only, to the opt-in roster (never the rendered text)
            from ..integrations.whatsapp import Recipient, WhatsAppClient, send_alert_to_roster
            from ..models import NotifyOptIn

            wa = WhatsAppClient(http=self.http)
            roster = [Recipient(r.phone, r.role, r.lang) for r in self.session.exec(
                select(NotifyOptIn).where(NotifyOptIn.site == self.site, NotifyOptIn.opted_out_at.is_(None))).all()]
            if wa.enabled and roster:
                out["whatsapp"] = send_alert_to_roster(wa, roster, a["template"], a["lang"], a["vars"], role=ctx.get("role"))
                if any("message_id" in x for x in out["whatsapp"]):
                    delivered.append("whatsapp_template")
            else:
                out["whatsapp"] = {"skipped": "not configured" if not wa.enabled else "no opt-ins"}
        return out

    def _do_log_downtime(self, a: dict, ctx: dict) -> dict:
        start = datetime.fromisoformat(a["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(a["end"].replace("Z", "+00:00"))
        return {"machine_id": a["machine_id"], "minutes": round((end - start).total_seconds() / 60, 1), "reason": a["reason"]}

    def _do_escalate(self, a: dict, ctx: dict) -> dict:
        clip = ctx.get("clip_path")
        text = render_alert("escalation", ctx.get("lang", "en"), {"role": a["to_role"], "note": a["note"], "event_id": a["event_id"]})
        log.warning("ESCALATE -> %s: %s (clip=%s)", a["to_role"], a["note"], clip)
        if settings.alert_webhook_url:
            self.http.post(settings.alert_webhook_url, json={"text": text, "clip": clip, "role": a["to_role"], "site": self.site}).raise_for_status()
        return {"to_role": a["to_role"], "clip_attached": bool(clip), "text": text, "at": datetime.now(UTC).isoformat()}

    def _do_request_human_review(self, a: dict, ctx: dict) -> dict:
        return {"event_id": a["event_id"], "question": a["question"], "queued": True}

    # proposals never execute through the agent; a human approval re-enters via execute()
    def _do_propose_staffing_change(self, a: dict, ctx: dict) -> dict:
        return {"applied": True, **a}

    def _do_propose_open_till(self, a: dict, ctx: dict) -> dict:
        return {"applied": True, **a}

    def _do_propose_maintenance_window(self, a: dict, ctx: dict) -> dict:
        return {"applied": True, **a}

    # ---- v2 crew tools --------------------------------------------------------------

    def _do_create_restock_task(self, a: dict, ctx: dict) -> dict:
        # the same tracker path as create_work_order, so a restock task is one ticket kind, not a second integration
        return self._do_create_work_order({"machine_id": a["shelf_id"], "summary": a["summary"], "severity": 1}, ctx) | {
            "shelf_id": a["shelf_id"], "product": a.get("product"), "osa_impact_pct": a.get("osa_impact_pct")}

    def _do_flag_merchandising(self, a: dict, ctx: dict) -> dict:
        return {"flagged": True, **a}

    def _do_propose_staffing_plan(self, a: dict, ctx: dict) -> dict:
        return {"applied": True, "day": a["day"], "slots": len(a["tills"]), "staff_hours": a["staff_hours"]}

    def _do_quarantine_memory(self, a: dict, ctx: dict) -> dict:
        from ..models import Memory

        m = self.session.get(Memory, a["memory_id"])
        if m is None:
            raise ValueError(f"memory {a['memory_id']} not found")
        m.quarantined, m.quarantine_reason = True, a["reason"]
        self.session.add(m)
        self.session.commit()
        return {"memory_id": m.id, "quarantined": True}

    def _do_flag_run(self, a: dict, ctx: dict) -> dict:
        from ..models import AgentRun

        r = self.session.get(AgentRun, a["run_id"])
        if r is None:
            raise ValueError(f"run {a['run_id']} not found")
        r.status = "flagged"
        r.meta = {**(r.meta or {}), "flag": {"finding": a["finding"], "note": a["note"]}}
        self.session.add(r)
        self.session.commit()
        return {"run_id": r.id, "flagged": a["finding"]}
