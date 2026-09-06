"""Event ingestion (idempotent), listing, clips."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..agent.ops_agent import handle_event
from ..bus import bus
from ..config import settings
from ..db import get_session
from ..models import Clip, Event
from ..schemas import BatchResult, EventBatch, EventOut

router = APIRouter(tags=["events"])


def _out(e: Event, has_clip: bool | None = None) -> EventOut:
    return EventOut(
        id=e.id, site=e.site, camera=e.camera, ts=e.ts, kind=e.kind, severity=e.severity, payload=e.payload,
        clip_path=e.clip_path, rule_id=e.rule_id, received_at=e.received_at, handled=e.handled,
        has_clip=bool(has_clip if has_clip is not None else e.clip_path),
    )


@router.post("/events/batch", response_model=BatchResult, status_code=201)
def ingest_batch(batch: EventBatch, session: Session = Depends(get_session)) -> BatchResult:
    inserted = dup = created = 0
    for ev in batch.events:
        if session.get(Event, ev.id) is not None:
            dup += 1
            continue
        row = Event(**ev.model_dump())
        session.add(row)
        session.commit()
        session.refresh(row)
        inserted += 1
        bus.publish(row.site, "event", _out(row).model_dump(mode="json"))
        if row.kind not in ("footfall_tick", "checkout_served"):
            # v2 crew first (attributed, budgeted, audited); the Phase B path when the crew is off, killed, or has
            # no agent for this kind. Severity-3 escalation is guaranteed by Policy on both paths.
            from ..crew.crew import dispatch

            actions = dispatch(row, session)
            if actions is None:
                actions = handle_event(row, session)
            created += len(actions)
            for a in actions:
                bus.publish(row.site, "action", {"id": a.id, "tool": a.tool, "status": a.status, "event_id": a.event_id,
                                                 "autonomous": a.autonomous, "reasoning": a.reasoning})
        row.handled = True
        session.add(row)
        session.commit()
    return BatchResult(inserted=inserted, duplicates=dup, actions_created=created)


@router.get("/events", response_model=list[EventOut])
def list_events(
    site: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    kind: str | None = None,
    severity: int | None = Query(None, ge=1, le=3),
    min_severity: int | None = Query(None, ge=1, le=3),
    limit: int = Query(100, ge=1, le=5000),
    session: Session = Depends(get_session),
) -> list[EventOut]:
    q = select(Event)
    if site:
        q = q.where(Event.site == site)
    if since:
        q = q.where(Event.ts >= since)
    if until:
        q = q.where(Event.ts < until)
    if kind:
        q = q.where(Event.kind == kind)
    if severity:
        q = q.where(Event.severity == severity)
    if min_severity:
        q = q.where(Event.severity >= min_severity)
    rows = session.exec(q.order_by(Event.ts.desc()).limit(limit)).all()
    clips = {c.event_id for c in session.exec(select(Clip).where(Clip.event_id.in_([r.id for r in rows]))).all()} if rows else set()
    return [_out(r, r.id in clips) for r in rows]


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: str, session: Session = Depends(get_session)) -> EventOut:
    e = session.get(Event, event_id)
    if e is None:
        raise HTTPException(404, "event not found")
    return _out(e, session.get(Clip, event_id) is not None)


@router.put("/clips/{event_id}", status_code=201)
async def upload_clip(event_id: str, background: BackgroundTasks, file: UploadFile = File(...), session: Session = Depends(get_session)) -> dict:
    if session.get(Event, event_id) is None:
        raise HTTPException(404, "event not found")
    dest = Path(settings.clips_dir) / f"{event_id}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    dest.write_bytes(data)
    clip = session.get(Clip, event_id) or Clip(event_id=event_id, path=str(dest))
    clip.path, clip.bytes = str(dest), len(data)
    session.add(clip)
    ev = session.get(Event, event_id)
    ev.clip_path = str(dest)
    session.add(ev)
    session.commit()
    bus.publish(ev.site, "clip", {"event_id": event_id, "bytes": len(data)})
    # v2 Watch: once the (blurred) clip exists, severity-3 and low-confidence events get a VLM second
    # opinion after the response is sent; it can add a review request, never change severity.
    from ..vlm.opinion import qualifies_for_auto

    trigger = qualifies_for_auto(ev)
    if trigger:
        background.add_task(_auto_opinion, event_id, trigger)
    return {"event_id": event_id, "bytes": len(data)}


def _auto_opinion(event_id: str, trigger: str) -> None:
    from sqlmodel import Session

    from .. import db as dbmod
    from ..vlm.opinion import opine_event

    try:
        with Session(dbmod.engine) as s:
            o = opine_event(event_id, s, trigger=trigger)
            if o is not None:
                bus.publish(o.site, "opinion", {"event_id": event_id, "agrees": o.agrees, "disagreement": o.disagreement, "status": o.status})
    except Exception:  # noqa: BLE001 — advisory path must never take the API down
        import logging

        logging.getLogger(__name__).exception("auto opinion failed for %s", event_id)


@router.get("/clips/{event_id}")
def get_clip(event_id: str, session: Session = Depends(get_session)):
    clip = session.get(Clip, event_id)
    if clip is None or not Path(clip.path).exists():
        raise HTTPException(404, "clip not available")
    return FileResponse(clip.path, media_type="video/mp4", filename=f"{event_id}.mp4")
