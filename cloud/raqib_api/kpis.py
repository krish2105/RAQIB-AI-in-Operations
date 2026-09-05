"""Operational KPIs computed from events. Pure functions over event lists."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from .ops_theory import service_level, slot_rates


def osa(events: Iterable[Any], now: datetime, window_h: float = 24.0, gap_default_min: float = 15.0) -> dict[str, float]:
    """On-shelf availability per shelf over the window.

    A `shelf_gap` event opens a gap; the gap closes at the next shelf_gap-free
    re-emit boundary or after `gap_default_min` when no further signal arrives.
    OSA = 1 - gap_time / window.
    """
    start = now - timedelta(hours=window_h)
    gaps: dict[str, list[datetime]] = {}
    for e in events:
        if e.kind == "shelf_gap" and e.ts >= start:
            gaps.setdefault(str(e.payload.get("shelf_id", e.payload.get("zone", "?"))), []).append(e.ts)
    result: dict[str, float] = {}
    for shelf, times in gaps.items():
        times.sort()
        total = 0.0
        for i, t in enumerate(times):
            nxt = times[i + 1] if i + 1 < len(times) else None
            dur = min((nxt - t).total_seconds() if nxt else gap_default_min * 60, gap_default_min * 60)
            total += dur
        result[shelf] = max(0.0, 1.0 - total / (window_h * 3600))
    return result


def time_to_restock(events: Iterable[Any], gap_default_min: float = 15.0) -> dict[str, float]:
    """Mean minutes a shelf stayed in gap before the signal stopped (proxy for restock)."""
    by: dict[str, list[datetime]] = {}
    for e in events:
        if e.kind == "shelf_gap":
            by.setdefault(str(e.payload.get("shelf_id", "?")), []).append(e.ts)
    out: dict[str, float] = {}
    for shelf, ts in by.items():
        ts.sort()
        episodes: list[float] = []
        run_start = ts[0]
        prev = ts[0]
        for t in ts[1:]:
            if (t - prev).total_seconds() > gap_default_min * 60 * 1.5:
                episodes.append((prev - run_start).total_seconds() / 60 + gap_default_min)
                run_start = t
            prev = t
        episodes.append((prev - run_start).total_seconds() / 60 + gap_default_min)
        out[shelf] = sum(episodes) / len(episodes)
    return out


def compliance(events: Iterable[Any], footfall: int) -> float | None:
    """Factory: 1 - PPE violations / person entries (bounded 0..1)."""
    viol = sum(1 for e in events if e.kind == "ppe_violation")
    if footfall <= 0:
        return None
    return max(0.0, 1.0 - viol / footfall)


def downtime_minutes(events: Iterable[Any]) -> float:
    return sum(float(e.payload.get("stopped_s", 0)) for e in events if e.kind == "machine_stopped") / 60.0


def summary(events: list[Any], profile: str, tills: int, now: datetime, window_h: float = 24.0) -> dict[str, Any]:
    start = now - timedelta(hours=window_h)
    recent = [e for e in events if e.ts >= start]
    footfall = sum(1 for e in recent if e.kind == "footfall_tick")
    hours = max(1e-9, min(window_h, (now - min((e.ts for e in recent), default=now)).total_seconds() / 3600)) if recent else 1.0
    queue_counts = [float(e.payload.get("count", 0)) for e in recent if e.kind == "queue_over"]
    slots = slot_rates(recent, tills_open=tills)
    out: dict[str, Any] = {
        "profile": profile,
        "window_h": window_h,
        "footfall": footfall,
        "footfall_per_hour": round(footfall / hours, 1) if recent else 0.0,
        "avg_queue": round(sum(queue_counts) / len(queue_counts), 2) if queue_counts else 0.0,
        "events_by_severity": {s: sum(1 for e in recent if e.severity == s) for s in (1, 2, 3)},
        "queue_model": [s.as_dict() for s in slots[-32:]],
        "simulated_share": round(sum(1 for e in recent if e.payload.get("simulated")) / len(recent), 3) if recent else 0.0,
    }
    if profile == "retail":
        sl = service_level(recent, max_queue=3)
        shelf = osa(recent, now, window_h)
        out.update({
            "service_level": round(sl, 3) if sl is not None else None,
            "osa": {k: round(v, 3) for k, v in shelf.items()},
            "osa_store": round(sum(shelf.values()) / len(shelf), 3) if shelf else None,
            "time_to_restock_min": {k: round(v, 1) for k, v in time_to_restock(recent).items()},
            "peak_rho": round(max((s.rho for s in slots), default=0.0), 3),
        })
    else:
        out.update({
            "compliance": compliance(recent, footfall),
            "downtime_min": round(downtime_minutes(recent), 1),
            "stopped_machines": sorted({str(e.payload.get("machine_id")) for e in recent if e.kind == "machine_stopped"}),
            "breaches": sum(1 for e in recent if e.kind == "zone_breach"),
        })
    return out
