"""Pydantic request/response shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

EVENT_KINDS = (
    "ppe_violation", "zone_breach", "machine_stopped", "queue_over", "shelf_gap", "footfall_tick", "checkout_served",
    "price_mismatch", "planogram_drift",  # v2 shelf intelligence (rules R14, R15)
    "model_drift", "edge_offline",  # v2 fleet health (cloud-emitted)
)


class EventIn(BaseModel):
    id: str = Field(min_length=26, max_length=26)
    site: str
    camera: str
    ts: datetime
    kind: str = Field(pattern="^(" + "|".join(EVENT_KINDS) + ")$")
    severity: int = Field(ge=1, le=3)
    payload: dict[str, Any] = Field(default_factory=dict)
    clip_path: str | None = None
    rule_id: str = ""


class EventBatch(BaseModel):
    events: list[EventIn] = Field(max_length=500)


class BatchResult(BaseModel):
    inserted: int
    duplicates: int
    actions_created: int = 0


class EventOut(EventIn):
    received_at: datetime
    handled: bool
    has_clip: bool = False


class ActionOut(BaseModel):
    id: int
    site: str
    event_id: str | None
    tool: str
    args: dict[str, Any]
    status: str
    autonomous: bool
    reasoning: str
    confidence: float
    backend: str
    result: dict[str, Any] | None
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    agent: str | None = None  # v2 crew attribution
    run_id: str | None = None


class Decide(BaseModel):
    by: str = "operator"
    note: str | None = None


class ToolCallOut(BaseModel):
    id: int
    site: str
    action_id: int | None
    tool: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    ok: bool
    error: str | None
    latency_ms: float
    cost_usd: float
    backend: str
    created_at: datetime


class SiteOut(BaseModel):
    name: str
    profile: str
    tills: int
    thresholds: dict[str, Any]
    floor: dict[str, Any]
    machines: list[dict[str, Any]]
    zones: list[dict[str, Any]]
    cameras: list[dict[str, Any]]
