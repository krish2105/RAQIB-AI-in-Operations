from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session

from raqib_api.models import Event, Site


def fresh_session(ctx: dict[str, Any]) -> Session:
    return Session(ctx["engine"])


def ensure_site(session: Session, name: str = "sec-store", tills: int = 3) -> Site:
    s = session.get(Site, name)
    if s is None:
        s = Site(name=name, profile="retail", tills=tills)
        session.add(s)
        session.commit()
    return s


def queue_event(session: Session, i: int = 0, site: str = "sec-store", count: int = 6, conf: float = 0.9) -> Event:
    e = Event(id=f"01SEC{i:021d}", site=site, camera="cam1", ts=datetime.now(UTC), kind="queue_over", severity=2,
              payload={"zone": "queue_till_1", "till": 1, "count": count, "sustained_s": 90, "confidence": conf}, rule_id="R10")
    session.add(e)
    session.commit()
    return e
