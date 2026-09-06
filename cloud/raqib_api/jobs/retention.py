"""Retention: clips 30 days, events 400 days, memories 90 days unless pinned. Every run logs what it deleted."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import Session, delete, select

from ..config import settings
from ..models import AskLog, Caption, Chunk, Clip, Event, Memory, Opinion, RetentionLog

log = logging.getLogger(__name__)


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def run_retention(session: Session, now: datetime | None = None, *, clips_days: int | None = None, events_days: int | None = None,
                  memories_days: int | None = None, dry_run: bool = False) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    clips_days = clips_days if clips_days is not None else settings.retention_clips_days
    events_days = events_days if events_days is not None else settings.retention_events_days
    memories_days = memories_days if memories_days is not None else settings.retention_memories_days
    out: dict[str, Any] = {"now": now.isoformat(), "dry_run": dry_run}

    # clips: delete the file and the row, clear the event's clip_path
    cut = _naive(now - timedelta(days=clips_days))
    old_clips = session.exec(select(Clip).where(Clip.uploaded_at < cut)).all()
    removed_files = 0
    for c in old_clips:
        if not dry_run:
            p = Path(c.path)
            if p.exists():
                p.unlink()
                removed_files += 1
            ev = session.get(Event, c.event_id)
            if ev is not None:
                ev.clip_path = None
                session.add(ev)
            session.delete(c)
    out["clips"] = {"deleted": len(old_clips), "files_removed": removed_files, "cutoff": cut.isoformat()}

    # events older than N days, with their dependants (chunks, captions, opinions, ask log rows are site-level and kept)
    cut_e = _naive(now - timedelta(days=events_days))
    old_ids = session.exec(select(Event.id).where(Event.ts < cut_e)).all()
    old_ids = [i[0] if isinstance(i, tuple) else i for i in old_ids]
    if old_ids and not dry_run:
        for i in range(0, len(old_ids), 500):
            batch = old_ids[i:i + 500]
            session.exec(delete(Chunk).where(Chunk.event_id.in_(batch)))
            session.exec(delete(Caption).where(Caption.event_id.in_(batch)))
            session.exec(delete(Opinion).where(Opinion.event_id.in_(batch)))
            session.exec(delete(Clip).where(Clip.event_id.in_(batch)))
            session.exec(delete(Event).where(Event.id.in_(batch)))
    out["events"] = {"deleted": len(old_ids), "cutoff": cut_e.isoformat()}

    # memories: unpinned only
    cut_m = _naive(now - timedelta(days=memories_days))
    old_mem = session.exec(select(Memory).where(Memory.ts < cut_m, Memory.pinned.is_(False))).all()
    kept_pinned = len(session.exec(select(Memory).where(Memory.ts < cut_m, Memory.pinned.is_(True))).all())
    if not dry_run:
        for m in old_mem:
            session.delete(m)
    out["memories"] = {"deleted": len(old_mem), "kept_pinned": kept_pinned, "cutoff": cut_m.isoformat()}

    if not dry_run:
        for kind in ("clips", "events", "memories"):
            session.add(RetentionLog(ts=now, kind=kind, deleted=out[kind]["deleted"], cutoff=datetime.fromisoformat(out[kind]["cutoff"]), details=out[kind]))
        session.commit()
    log.info("retention: %s", out)
    return out


def retention_log(session: Session, limit: int = 50) -> list[dict[str, Any]]:
    rows = session.exec(select(RetentionLog).order_by(RetentionLog.ts.desc()).limit(limit)).all()
    return [{"id": r.id, "ts": r.ts, "kind": r.kind, "deleted": r.deleted, "cutoff": r.cutoff, "details": r.details} for r in rows]


def _unused(_: AskLog) -> None:  # AskLog rows are analytics and kept; referenced here so the import is intentional
    return None
