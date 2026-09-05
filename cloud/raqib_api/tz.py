"""Timezone normalisation that never mutates or dirties a session-tracked ORM row.

SQLite stores `TIMESTAMP WITHOUT TIME ZONE` and hands back naive datetimes;
Postgres does the same for this column type. Every analytics function expects
timezone-aware UTC. The wrong way to fix that is `event.ts = event.ts.replace(...)`
on a row fetched from `session.exec(select(Event)...)` — that row is tracked by
the session's identity map, so mutating any attribute marks it dirty, and the
next autoflush issues an `UPDATE` for every row touched. On a real dataset
(tens of thousands of events) that stray write starves SQLite's one writer and
every concurrent request gets `database is locked`; on Postgres it is merely a
wasteful write hidden inside a read endpoint.

A `copy.copy()` of a mapped instance does not fix this either: SQLAlchemy
instruments attribute assignment through `_sa_instance_state`, and a shallow
copy's `__dict__` carries a reference to the *same* state object as the
original, so setting an attribute on the "copy" still marks the original row
dirty. The only reliable fix is to never touch a mapped object at all: read
what analytics code needs into a plain, uninstrumented value object.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


class HasEventFields(Protocol):
    id: str
    site: str
    camera: str
    ts: datetime
    kind: str
    severity: int
    payload: dict[str, Any]
    clip_path: str | None
    rule_id: str


@dataclass(frozen=True, slots=True)
class EventView:
    """A plain, session-free snapshot of the Event fields analytics code reads."""

    id: str
    site: str
    camera: str
    ts: datetime
    kind: str
    severity: int
    payload: dict[str, Any]
    clip_path: str | None
    rule_id: str


def ensure_utc(rows: list[HasEventFields]) -> list[EventView]:
    """Detach each row into an `EventView` with a timezone-aware `ts`.

    Always returns new, plain objects — never the ORM rows themselves — so
    nothing downstream can accidentally mark the session dirty by reading.
    """
    out: list[EventView] = []
    for r in rows:
        ts = r.ts if r.ts.tzinfo is not None else r.ts.replace(tzinfo=UTC)
        out.append(
            EventView(
                id=r.id,
                site=r.site,
                camera=r.camera,
                ts=ts,
                kind=r.kind,
                severity=r.severity,
                payload=r.payload,
                clip_path=r.clip_path,
                rule_id=r.rule_id,
            )
        )
    return out
