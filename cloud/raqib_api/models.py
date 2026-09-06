"""SQLModel tables. `Event` mirrors edge/raqib_edge/events.py field for field."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Site(SQLModel, table=True):
    __tablename__ = "sites"
    name: str = Field(primary_key=True)
    profile: str = Field(index=True)  # retail | factory
    tills: int = 1
    thresholds: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    floor: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    machines: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Camera(SQLModel, table=True):
    __tablename__ = "cameras"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(foreign_key="sites.name", index=True)
    name: str
    source: str = "file"
    fps: float = 25.0


class Zone(SQLModel, table=True):
    __tablename__ = "zones"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(foreign_key="sites.name", index=True)
    name: str
    kind: str
    camera: str
    polygon: list[list[float]] = Field(default_factory=list, sa_column=Column(JSON))
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Event(SQLModel, table=True):
    __tablename__ = "events"
    id: str = Field(primary_key=True)  # ULID from the edge
    site: str = Field(index=True)
    camera: str
    ts: datetime = Field(index=True)
    kind: str = Field(index=True)
    severity: int = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    clip_path: str | None = None
    rule_id: str = ""
    received_at: datetime = Field(default_factory=utcnow)
    handled: bool = Field(default=False, index=True)  # agent has looked at it


class Clip(SQLModel, table=True):
    __tablename__ = "clips"
    event_id: str = Field(primary_key=True, foreign_key="events.id")
    path: str
    bytes: int = 0
    uploaded_at: datetime = Field(default_factory=utcnow)


class Action(SQLModel, table=True):
    """An agent decision: executed autonomously or proposed for a human."""

    __tablename__ = "actions"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(index=True)
    event_id: str | None = Field(default=None, foreign_key="events.id", index=True)
    tool: str = Field(index=True)
    args: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="proposed", index=True)  # proposed | approved | rejected | executed | failed
    autonomous: bool = False
    reasoning: str = ""
    confidence: float = 0.0
    backend: str = "dryrun"
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    decided_at: datetime | None = None
    decided_by: str | None = None
    # v2 crew attribution (additive, nullable): which agent and run produced this action
    agent: str | None = Field(default=None, index=True)
    run_id: str | None = Field(default=None, index=True)


class ToolCall(SQLModel, table=True):
    """Audit log: every tool execution, with cost."""

    __tablename__ = "tool_calls"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(index=True)
    action_id: int | None = Field(default=None, foreign_key="actions.id")
    tool: str
    input: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    output: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    ok: bool = True
    error: str | None = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    backend: str = "dryrun"
    created_at: datetime = Field(default_factory=utcnow)


class Forecast(SQLModel, table=True):
    __tablename__ = "forecasts"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(index=True)
    target: str = Field(index=True)  # queue | shelf | machine
    key: str = ""  # zone / shelf / machine id
    ts: datetime
    value: float
    baseline_value: float
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------------------
# v2 tables (Phases E–K). Additive only; nothing above changes.
# ---------------------------------------------------------------------------------------

from pgvector.sqlalchemy import Vector  # noqa: E402

from .config import settings  # noqa: E402


def _embedding_column() -> Column:
    """pgvector on Postgres, a JSON float list on SQLite (dev/tests)."""
    return Column(Vector(settings.embed_dim).with_variant(JSON(), "sqlite"), nullable=True)


class Caption(SQLModel, table=True):
    """VLM caption of ≤3 blurred keyframes. model="none" records a skipped caption and why."""

    __tablename__ = "captions"
    id: int | None = Field(default=None, primary_key=True)
    event_id: str = Field(foreign_key="events.id", index=True)
    site: str = Field(index=True)
    camera: str = ""
    ts: datetime = Field(default_factory=utcnow)
    text: str = ""
    parsed: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    model: str = "none"
    provider: str = "none"
    frames: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)


class Document(SQLModel, table=True):
    __tablename__ = "documents"
    id: str = Field(primary_key=True)  # ULID
    site: str = Field(index=True)
    title: str
    kind: str = Field(index=True)  # sop | policy | planogram | pos_import | manual | scenario
    path: str = ""
    sha256: str = ""
    lang: str = "en"
    ts: datetime = Field(default_factory=utcnow)
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Chunk(SQLModel, table=True):
    """One retrievable unit: an event (rule + payload + caption + KPIs) or a document span."""

    __tablename__ = "chunks"
    id: str = Field(primary_key=True)  # ULID
    site: str = Field(index=True)
    doc_id: str | None = Field(default=None, foreign_key="documents.id", index=True)
    event_id: str | None = Field(default=None, foreign_key="events.id", index=True)
    kind: str = Field(index=True)  # event | document
    ts: datetime = Field(default_factory=utcnow, index=True)
    text: str
    embedding: list[float] | None = Field(default=None, sa_column=_embedding_column())
    model: str = ""  # embedder that produced `embedding`; ANN only compares equal models
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Memory(SQLModel, table=True):
    """Per-site, per-agent key/value with provenance. Read into prompts as data only."""

    __tablename__ = "memories"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(index=True)
    agent: str = Field(index=True)
    key: str = Field(index=True)
    value: str
    source: str = ""
    event_id: str | None = Field(default=None, index=True)
    written_by: str = ""
    ts: datetime = Field(default_factory=utcnow)
    pinned: bool = False
    quarantined: bool = Field(default=False, index=True)
    quarantine_reason: str | None = None
    sha256: str = ""


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"
    id: str = Field(primary_key=True)  # ULID
    site: str = Field(index=True)
    agent: str = Field(index=True)
    trigger: str = ""
    started: datetime = Field(default_factory=utcnow)
    ended: datetime | None = None
    tool_calls: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    status: str = Field(default="running", index=True)  # running | ok | budget_exceeded | killed | error | flagged
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class AgentMessage(SQLModel, table=True):
    __tablename__ = "agent_messages"
    id: str = Field(primary_key=True)  # ULID
    run_id: str = Field(foreign_key="agent_runs.id", index=True)
    from_agent: str
    to_agent: str
    schema_name: str = Field(default="", sa_column_kwargs={"name": "schema"})
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    hmac: str = ""
    nonce: str = ""
    ts: datetime = Field(default_factory=utcnow)
    verified: bool = True


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: str = Field(primary_key=True)  # Supabase auth uid
    email: str = Field(index=True, unique=True)
    role: str = "viewer"  # viewer | operator | manager | admin
    site_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Store(SQLModel, table=True):
    __tablename__ = "stores"
    id: str = Field(primary_key=True)
    name: str
    site_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    region: str = ""


class DriftSample(SQLModel, table=True):
    __tablename__ = "drift_samples"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(index=True)
    camera: str = Field(index=True)
    ts: datetime = Field(index=True)
    det_count: float = 0.0
    mean_conf: float = 0.0
    brightness: float = 0.0
    blur: float = 0.0


class QuotaCounter(SQLModel, table=True):
    """Daily request/token counters per provider, the enforcement record for free tiers."""

    __tablename__ = "quota_counters"
    provider: str = Field(primary_key=True)
    day: str = Field(primary_key=True)  # YYYY-MM-DD UTC
    requests: int = 0
    tokens: int = 0
    updated_at: datetime = Field(default_factory=utcnow)


class AskLog(SQLModel, table=True):
    """Every /ask call: question, plan, answer, citations, provider and cost. Feeds /ask/history and evals."""

    __tablename__ = "ask_log"
    id: str = Field(primary_key=True)  # ULID
    site: str = Field(index=True)
    q: str
    lang: str = "en"
    plan: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    answer: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    confidence: float = 0.0
    hits: int = 0
    provider: str = "none"
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    ts: datetime = Field(default_factory=utcnow, index=True)


class Opinion(SQLModel, table=True):
    """VLM second opinion on an event. Advisory: it may add a human-review request, never change severity."""

    __tablename__ = "opinions"
    id: int | None = Field(default=None, primary_key=True)
    event_id: str = Field(foreign_key="events.id", index=True)
    site: str = Field(index=True)
    rule_severity: int
    agrees: bool | None = None  # None = unavailable (no frames / no provider / quota)
    confidence: float = 0.0
    observed: str = ""
    disagreement_reason: str | None = None
    suggested_severity: int | None = None
    disagreement: bool = Field(default=False, index=True)  # suggested severity below the rule's: recorded, never applied
    review_action_id: int | None = Field(default=None, foreign_key="actions.id")
    trigger: str = "on_demand"  # auto_sev3 | auto_low_conf | on_demand
    status: str = "ok"  # ok | unavailable | quota_exhausted | invalid_json
    model: str = "none"
    provider: str = "none"
    frames: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    ts: datetime = Field(default_factory=utcnow, index=True)


class CrewFlag(SQLModel, table=True):
    """Operator-set switches checked before every agent run. `agents_enabled=false` is the kill switch."""

    __tablename__ = "crew_flags"
    key: str = Field(primary_key=True)
    value: str = "true"
    updated_by: str = ""
    note: str = ""
    updated_at: datetime = Field(default_factory=utcnow)


class MemorySnapshot(SQLModel, table=True):
    __tablename__ = "memory_snapshots"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(index=True)
    taken_at: datetime = Field(default_factory=utcnow, index=True)
    taken_by: str = "scheduler"
    entries: int = 0
    data: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))


class PosTransaction(SQLModel, table=True):
    """One POS transaction (CSV import or adapter). Deduplicated on (site, txn_id)."""

    __tablename__ = "pos_transactions"
    site: str = Field(primary_key=True)
    txn_id: str = Field(primary_key=True)
    ts: datetime = Field(index=True)
    till: int = Field(index=True)
    items: int = 0
    amount: float = 0.0
    source: str = "csv"  # csv | odoo | shopify
    imported_at: datetime = Field(default_factory=utcnow)


class NotifyOptIn(SQLModel, table=True):
    """WhatsApp opt-in roster: only people on this list ever receive a template, and only for their role."""

    __tablename__ = "notify_optins"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(index=True)
    phone: str = Field(index=True)  # E.164 digits, no '+'
    role: str = "floor_manager"
    lang: str = "en"
    opted_in_at: datetime = Field(default_factory=utcnow)
    opted_out_at: datetime | None = None


class EdgeHeartbeat(SQLModel, table=True):
    """One row per heartbeat from an edge box: fps, temperature, sync queue depth, model hash, cameras."""

    __tablename__ = "edge_heartbeats"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(index=True)
    box_id: str = Field(index=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    fps: float = 0.0
    temp_c: float | None = None
    queue_depth: int = 0
    model_hash: str = ""
    detector: str = ""
    version: str = ""
    cameras: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class LlmSpan(SQLModel, table=True):
    """One row per model call (the OpenTelemetry span, persisted): the ledger behind the cost KPI."""

    __tablename__ = "llm_spans"
    id: int | None = Field(default=None, primary_key=True)
    site: str = Field(default="-", index=True)
    task: str = Field(index=True)
    provider: str = Field(index=True)
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    prompt_hash: str = ""
    ok: bool = True
    attempts: int = 1
    ts: datetime = Field(default_factory=utcnow, index=True)


class RetentionLog(SQLModel, table=True):
    __tablename__ = "retention_log"
    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    kind: str  # clips | events | memories
    deleted: int = 0
    cutoff: datetime
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


V2_TABLES = ("captions", "documents", "chunks", "memories", "agent_runs", "agent_messages", "users", "stores",
             "drift_samples", "quota_counters", "ask_log", "opinions", "crew_flags", "memory_snapshots", "pos_transactions",
             "notify_optins", "edge_heartbeats", "llm_spans", "retention_log")
