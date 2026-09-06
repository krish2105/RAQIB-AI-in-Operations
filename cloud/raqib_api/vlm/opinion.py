"""VLM second opinion. Hard policy, enforced in code and tested:

  * an opinion may RAISE attention: disagreement with confidence >= VLM_REVIEW_CONFIDENCE creates
    `request_human_review` through the existing tool runner (validated, logged, policy-gated);
  * an opinion may NEVER lower severity or cancel an action. A suggested severity below the rule's
    severity is stored as `disagreement=True` (a metric for the Auditor and the Watch tab) and nothing else.

Frames come from the stored clip, which the edge blurred before upload; at most VLM frames per event.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlmodel import Session, select

from ..agent.tools import Call, ToolRunner
from ..config import settings
from ..llm import ProviderChain, Quota, get_provider, try_complete
from ..models import Action, Clip, Event, Opinion
from ..rag.captions import extract_keyframes, frames_to_jpeg
from .budget import can_spend, opinion_quota, spend

log = logging.getLogger(__name__)
PROMPT = (__import__("pathlib").Path(__file__).resolve().parents[1] / "prompts" / "vlm_opinion.md").read_text()

OPINION_SCHEMA = {
    "type": "object",
    "properties": {
        "agrees": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "observed": {"type": "string", "maxLength": 500},
        "disagreement_reason": {"type": ["string", "null"], "maxLength": 300},
        "suggested_severity": {"type": ["integer", "null"], "minimum": 1, "maximum": 3},
    },
    "required": ["agrees", "confidence", "observed", "disagreement_reason", "suggested_severity"],
    "additionalProperties": False,
}


@dataclass
class OpinionResult:
    agrees: bool | None
    confidence: float
    observed: str
    disagreement_reason: str | None
    suggested_severity: int | None
    cost_usd: float = 0.0
    status: str = "ok"
    model: str = "none"
    provider: str = "none"
    frames: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def second_opinion(event: Event, frames: list[np.ndarray], provider: ProviderChain | None = None, quota: Quota | None = None,
                   jpegs: list[bytes] | None = None) -> OpinionResult:
    """Pure model call: no DB side effects. Never raises; status says why an opinion is unavailable."""
    t0 = time.perf_counter()
    frames = list(frames)[: settings.caption_max_frames]
    unavailable = OpinionResult(agrees=None, confidence=0.0, observed="unavailable", disagreement_reason=None, suggested_severity=None)
    if not frames and not jpegs:
        unavailable.status = "no_frames"
        return unavailable
    q = opinion_quota(quota)
    if not can_spend(q):
        log.warning("quota_exhausted: VLM opinion for %s skipped (VLM_DAILY_REQUESTS=%s)", event.id, settings.vlm_daily_requests)
        unavailable.status = "quota_exhausted"
        return unavailable
    images = (jpegs if jpegs is not None else frames_to_jpeg(frames))[: settings.caption_max_frames]
    provider = provider or get_provider("opinion", quota=q, site=event.site)
    user = (f"<event kind={event.kind} rule={event.rule_id} severity={event.severity} camera={event.camera} "
            f"zone={event.payload.get('zone', '-')} detector_confidence={event.payload.get('confidence', '-')}>"
            f" {len(images)} blurred keyframes attached.</event>\nGive your second opinion as JSON.")
    res = try_complete(provider, PROMPT, user, json_schema=OPINION_SCHEMA, images=images, max_tokens=300)
    if res is None:
        unavailable.status = "unavailable"
        unavailable.frames = len(images)
        return unavailable
    spend(q, res.tokens_in + res.tokens_out)
    latency = (time.perf_counter() - t0) * 1000
    if res.parsed is None:
        return OpinionResult(agrees=None, confidence=0.0, observed="unavailable", disagreement_reason=None, suggested_severity=None,
                             status="invalid_json", model=res.model, provider=res.provider, frames=len(images), tokens_in=res.tokens_in,
                             tokens_out=res.tokens_out, cost_usd=res.cost_usd, latency_ms=latency)
    p = res.parsed
    return OpinionResult(agrees=bool(p["agrees"]), confidence=float(p["confidence"]), observed=str(p["observed"]),
                         disagreement_reason=p.get("disagreement_reason"), suggested_severity=p.get("suggested_severity"),
                         cost_usd=res.cost_usd, model=res.model, provider=res.provider, frames=len(images), tokens_in=res.tokens_in,
                         tokens_out=res.tokens_out, latency_ms=latency)


def record_opinion(event: Event, result: OpinionResult, session: Session, trigger: str = "on_demand",
                   runner: ToolRunner | None = None) -> Opinion:
    """Apply the policy: store the row, flag a downgrade as a metric only, raise attention when warranted."""
    severity_before = event.severity
    row = Opinion(event_id=event.id, site=event.site, rule_severity=severity_before, agrees=result.agrees, confidence=result.confidence,
                  observed=result.observed, disagreement_reason=result.disagreement_reason, suggested_severity=result.suggested_severity,
                  trigger=trigger, status=result.status, model=result.model, provider=result.provider, frames=result.frames,
                  tokens_in=result.tokens_in, tokens_out=result.tokens_out, cost_usd=result.cost_usd, latency_ms=result.latency_ms)
    if result.suggested_severity is not None and result.suggested_severity < severity_before:
        row.disagreement = True  # recorded, never applied
    if result.agrees is False and result.confidence >= settings.vlm_review_confidence:
        row.disagreement = True
        runner = runner or ToolRunner(session, event.site, "vlm")
        question = f"VLM second opinion disagrees with {event.kind} (rule {event.rule_id}): {result.disagreement_reason or result.observed}"[:400]
        call = Call("request_human_review", {"event_id": event.id, "question": question}, "vlm disagreement")
        action = Action(site=event.site, event_id=event.id, tool=call.tool, args=call.args, autonomous=True, status="proposed",
                        reasoning=f"VLM second opinion disagrees with confidence {result.confidence:.2f}; severity {severity_before} unchanged",
                        confidence=result.confidence, backend="vlm")
        session.add(action)
        session.commit()
        session.refresh(action)
        res = runner.execute(call, action_id=action.id, ctx={"lang": "en"})
        action.status = "executed" if res.ok else "failed"
        action.result = res.output if res.ok else {"error": res.error}
        action.decided_at = datetime.now(UTC)
        action.decided_by = "vlm"
        session.add(action)
        row.review_action_id = action.id
    session.add(row)
    session.commit()
    session.refresh(row)
    # invariant, checked every time: the event's severity is exactly what the rule recorded
    fresh = session.get(Event, event.id)
    assert fresh is None or fresh.severity == severity_before, "an opinion must never change severity"
    return row


def qualifies_for_auto(event: Event) -> str | None:
    if not settings.vlm_auto:
        return None
    if event.severity >= 3:
        return "auto_sev3"
    conf = event.payload.get("confidence")
    if isinstance(conf, int | float) and conf < settings.vlm_auto_max_conf:
        return "auto_low_conf"
    return None


def opine_event(event_id: str, session: Session, trigger: str = "on_demand", provider: ProviderChain | None = None,
                quota: Quota | None = None, clips_dir: str | None = None) -> Opinion | None:
    """Run and record an opinion for an event that has a stored clip. Idempotent per (event, trigger)."""
    event = session.get(Event, event_id)
    if event is None:
        return None
    existing = session.exec(select(Opinion).where(Opinion.event_id == event_id, Opinion.status == "ok")).first()
    if existing is not None and trigger != "on_demand":
        return existing
    clip = session.get(Clip, event_id)
    path = clip.path if clip else event.clip_path
    frames = extract_keyframes(path)
    result = second_opinion(event, frames, provider=provider, quota=quota)
    return record_opinion(event, result, session, trigger=trigger)
