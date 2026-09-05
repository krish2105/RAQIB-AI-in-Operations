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
