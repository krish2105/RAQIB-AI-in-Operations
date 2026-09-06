"""Replay timeline: 1440 one-minute bins for one site-day, built from events only (never video).

Per bin: arrivals (footfall ticks), served (checkout completions), queue length (last queue_over count,
held for 5 minutes), occupancy per zone (arrivals for the entrance, held queue counts for queue zones,
completions for checkout zones), shelf availability (1 - empty_ratio held for 5 minutes after a gap),
and the events that fell into the bin. Deterministic for a given set of events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from ..models import Event, Site
from ..tz import ensure_utc

MINUTES = 1440
HOLD_MIN = 5


@dataclass
class Timeline:
    site: str
    day: str
    arrivals: list[int] = field(default_factory=lambda: [0] * MINUTES)
    served: list[int] = field(default_factory=lambda: [0] * MINUTES)
    queue: list[float] = field(default_factory=lambda: [0.0] * MINUTES)
    occupancy: dict[str, list[float]] = field(default_factory=dict)
    shelf: dict[str, list[float]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    zones: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)
    simulated_share: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"site": self.site, "day": self.day, "bins": MINUTES, "arrivals": self.arrivals, "served": self.served,
                "queue": [round(x, 2) for x in self.queue], "occupancy": {k: [round(x, 2) for x in v] for k, v in self.occupancy.items()},
                "shelf": {k: [round(x, 3) for x in v] for k, v in self.shelf.items()}, "events": self.events, "zones": self.zones,
                "totals": self.totals, "simulated_share": self.simulated_share}


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def day_events(site: str, day: date, session: Session) -> list[Any]:
    start, end = day_bounds(day)
    rows = session.exec(select(Event).where(Event.site == site, Event.ts >= start.replace(tzinfo=None), Event.ts < end.replace(tzinfo=None)).order_by(Event.ts)).all()
    return ensure_utc(rows)


def build_timeline(site: str, day: date, events: list[Any], zones: list[dict[str, Any]] | None = None) -> Timeline:
    start, _ = day_bounds(day)
    tl = Timeline(site=site, day=day.isoformat(), zones=zones or [])
    zone_kind = {z["name"]: z.get("kind", "") for z in (zones or [])}
    for z in zone_kind:
        tl.occupancy[z] = [0.0] * MINUTES
    queue_hold: list[tuple[int, float, str]] = []  # (minute, count, zone)
    shelf_hold: list[tuple[int, float, str]] = []
    simulated = 0
    for e in events:
        m = int((e.ts - start).total_seconds() // 60)
        if not 0 <= m < MINUTES:
            continue
        z = e.payload.get("zone") or ("entrance" if e.kind == "footfall_tick" else None)
        if e.payload.get("simulated"):
            simulated += 1
        if e.kind == "footfall_tick":
            tl.arrivals[m] += 1
            if z:
                tl.occupancy.setdefault(z, [0.0] * MINUTES)[m] += 1
        elif e.kind == "checkout_served":
            tl.served[m] += 1
            if z:
                tl.occupancy.setdefault(z, [0.0] * MINUTES)[m] += 1
        elif e.kind == "queue_over":
            queue_hold.append((m, float(e.payload.get("count", 0) or 0), z or "queue"))
        elif e.kind == "shelf_gap":
            shelf_hold.append((m, float(e.payload.get("empty_ratio", 0.5) or 0.5), str(e.payload.get("shelf_id", z or "shelf"))))
        if e.kind not in ("footfall_tick", "checkout_served"):
            tl.events.append({"min": m, "id": e.id, "kind": e.kind, "severity": e.severity, "zone": z, "rule_id": e.rule_id})
    for m, count, z in queue_hold:  # hold a queue reading for HOLD_MIN minutes
        occ = tl.occupancy.setdefault(z, [0.0] * MINUTES)
        for k in range(m, min(MINUTES, m + HOLD_MIN)):
            tl.queue[k] = max(tl.queue[k], count)
            occ[k] = max(occ[k], count)
    shelves = {s for _, _, s in shelf_hold} | {str(z.get("meta", {}).get("shelf_id")) for z in (zones or []) if z.get("kind") == "shelf" and z.get("meta", {}).get("shelf_id")}
    for s in shelves:
        tl.shelf[s] = [1.0] * MINUTES
    for m, ratio, s in shelf_hold:
        for k in range(m, min(MINUTES, m + HOLD_MIN)):
            tl.shelf[s][k] = min(tl.shelf[s][k], 1.0 - ratio)
    n = len(events)
    tl.simulated_share = round(simulated / n, 3) if n else 0.0
    tl.totals = {"events": n, "arrivals": sum(tl.arrivals), "served": sum(tl.served), "queue_alerts": len(queue_hold), "shelf_gaps": len(shelf_hold),
                 "peak_queue": max(tl.queue) if tl.queue else 0.0,
                 "busiest_minute": max(range(MINUTES), key=lambda i: tl.arrivals[i]) if any(tl.arrivals) else None,
                 "shelf_availability": {s: round(sum(v) / MINUTES, 4) for s, v in tl.shelf.items()}}
    return tl


def replay(site: str, day: date, session: Session) -> Timeline:
    s = session.get(Site, site)
    zones = [{"name": z["name"], "kind": z.get("kind"), "meta": {}} for z in (s.floor or {}).get("zones", [])] if s else []
    return build_timeline(site, day, day_events(site, day, session), zones)
