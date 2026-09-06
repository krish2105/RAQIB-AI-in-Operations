"""Edge box health from heartbeats: online (< 2 min), degraded (< offline threshold or low fps), offline (gap > 5 min).
Going offline emits one `edge_offline` event (severity 2) per box until it is back."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, select
from ulid import ULID

from ..config import settings
from ..models import EdgeHeartbeat, Event


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def status_of(last: EdgeHeartbeat | None, now: datetime) -> str:
    if last is None:
        return "unknown"
    gap = (now - _aware(last.ts)).total_seconds()
    if gap > settings.heartbeat_offline_s:
        return "offline"
    if gap > 120 or last.fps < 5:
        return "degraded"
    return "online"


def boxes(site: str, session: Session, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    ids = [r[0] if isinstance(r, tuple) else r for r in session.exec(select(EdgeHeartbeat.box_id).where(EdgeHeartbeat.site == site).distinct()).all()]
    out = []
    for box in sorted(ids):
        last = session.exec(select(EdgeHeartbeat).where(EdgeHeartbeat.site == site, EdgeHeartbeat.box_id == box).order_by(EdgeHeartbeat.ts.desc())).first()
        hist = session.exec(select(EdgeHeartbeat).where(EdgeHeartbeat.site == site, EdgeHeartbeat.box_id == box, EdgeHeartbeat.ts >= (now - timedelta(hours=24)).replace(tzinfo=None)).order_by(EdgeHeartbeat.ts)).all()
        out.append({"box_id": box, "status": status_of(last, now), "last_seen": _aware(last.ts).isoformat() if last else None,
                    "gap_s": round((now - _aware(last.ts)).total_seconds()) if last else None, "fps": last.fps if last else None, "temp_c": last.temp_c if last else None,
                    "queue_depth": last.queue_depth if last else None, "model_hash": (last.model_hash[:12] if last and last.model_hash else None),
                    "detector": last.detector if last else None, "version": last.version if last else None, "cameras": last.cameras if last else [],
                    "heartbeats_24h": len(hist), "fps_24h": [{"ts": _aware(h.ts).isoformat(), "fps": h.fps, "queue_depth": h.queue_depth} for h in hist[-96:]]})
    return out


def check_offline(site: str, session: Session, now: datetime | None = None) -> list[Event]:
    """Emit edge_offline once per box per outage: when the latest heartbeat is older than the threshold and no
    edge_offline event exists after that heartbeat."""
    now = now or datetime.now(UTC)
    out: list[Event] = []
    for b in boxes(site, session, now):
        if b["status"] != "offline":
            continue
        last_ts = datetime.fromisoformat(b["last_seen"]).replace(tzinfo=None)
        already = session.exec(select(Event).where(Event.site == site, Event.kind == "edge_offline", Event.payload.is_not(None), Event.ts >= last_ts)).all()
        if any(e.payload.get("box_id") == b["box_id"] for e in already):
            continue
        e = Event(id=str(ULID()), site=site, camera="-", ts=now, kind="edge_offline", severity=2, rule_id="H01",
                  payload={"box_id": b["box_id"], "last_seen": b["last_seen"], "gap_s": b["gap_s"], "confidence": 1.0}, handled=True)
        session.add(e)
        out.append(e)
    session.commit()
    return out
