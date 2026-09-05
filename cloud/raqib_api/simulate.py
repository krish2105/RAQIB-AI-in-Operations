"""Labelled history generator for demos, forecasting, and tests.

Produces `days` of events with daily and weekly seasonality so the dashboard,
forecast, and workforce pages have something to show before the edge box has
run for weeks. EVERY event carries payload.simulated = True; the UI labels it.
Live edge events never carry the flag. Deterministic for a given seed.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta
from typing import Any

from ulid import ULID

RETAIL_SHELVES = [("A1", "confectionery display"), ("B3", "dairy"), ("C2", "bread")]


def _ulid(ts: datetime, rnd: random.Random) -> str:
    return str(ULID.from_timestamp(ts.timestamp() + rnd.random() * 0.9))


def footfall_rate(ts: datetime) -> float:
    """Customers per hour: open 08:00-23:00, lunch and evening peaks, busier Thu-Sat (Gulf weekend)."""
    h = ts.hour + ts.minute / 60
    if h < 8 or h >= 23:
        return 0.0
    base = 22 + 26 * math.exp(-((h - 13) ** 2) / 4) + 40 * math.exp(-((h - 19.5) ** 2) / 3)
    weekday = ts.weekday()  # Mon=0
    mult = {3: 1.25, 4: 1.45, 5: 1.35, 6: 1.05}.get(weekday, 1.0)
    return base * mult


def generate(site: str, profile: str, days: int = 21, seed: int = 7, end: datetime | None = None, tills: int = 3,
             camera: str = "cam1") -> list[dict[str, Any]]:
    rnd = random.Random(seed)
    end = end or datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    out: list[dict[str, Any]] = []
    t = start
    queue_since: datetime | None = None
    shelf_gap_until: dict[str, datetime] = {}
    machine_stop_until: datetime | None = None
    while t < end:
        rate = footfall_rate(t)
        step = timedelta(minutes=5)
        n = _poisson(rate * step.total_seconds() / 3600, rnd)
        for i in range(n):
            ts = t + timedelta(seconds=rnd.uniform(0, 299))
            out.append(_ev(site, camera, ts, "footfall_tick", 1, {"zone": "entrance", "track_id": rnd.randint(1, 9999), "confidence": round(rnd.uniform(0.5, 0.95), 2), "simulated": True}, "R12", rnd))
        if profile == "retail":
            served = _poisson(min(n, tills * 2.2 * step.total_seconds() / 3600 * 60 / 2.0), rnd)
            for _ in range(served):
                ts = t + timedelta(seconds=rnd.uniform(0, 299))
                out.append(_ev(site, camera, ts, "checkout_served", 1, {"zone": "checkout_till_1", "till": rnd.randint(1, tills), "dwell_s": round(rnd.gauss(95, 25), 1), "confidence": 0.7, "mu_source": "estimated_from_video", "simulated": True}, "R13", rnd))
            capacity = tills * 30 / 12  # per 5 min
            if n > capacity * 1.15:
                queue_since = queue_since or t
                if (t - queue_since) >= timedelta(minutes=5) and rnd.random() < 0.7:
                    count = min(12, 3 + int((n - capacity) * 1.2) + rnd.randint(0, 2))
                    out.append(_ev(site, camera, t + timedelta(seconds=rnd.uniform(0, 299)), "queue_over", 2,
                                   {"zone": "queue_till_1", "till": 1, "count": count, "sustained_s": 60 + rnd.randint(0, 240), "confidence": round(rnd.uniform(0.6, 0.9), 2), "simulated": True}, "R10", rnd))
            else:
                queue_since = None
            for shelf, product in RETAIL_SHELVES:
                until = shelf_gap_until.get(shelf)
                if until and t < until:
                    if rnd.random() < 0.9:
                        out.append(_ev(site, camera, t + timedelta(seconds=rnd.uniform(0, 299)), "shelf_gap", 1,
                                       {"zone": f"shelf_{shelf.lower()}", "shelf_id": shelf, "product": product, "empty_ratio": round(rnd.uniform(0.42, 0.8), 2), "sustained_s": 300, "confidence": 0.75, "simulated": True}, "R11", rnd))
                elif rate > 0 and rnd.random() < 0.004 * (1 + rate / 40):
                    shelf_gap_until[shelf] = t + timedelta(minutes=rnd.choice([15, 25, 40, 60]))
        else:
            if machine_stop_until and t < machine_stop_until:
                pass
            elif rate > 0 and rnd.random() < 0.006:
                dur = rnd.choice([3, 6, 12, 25])
                machine_stop_until = t + timedelta(minutes=dur)
                out.append(_ev(site, camera, t, "machine_stopped", 2, {"zone": "press_1_roi", "machine_id": 1, "stopped_s": dur * 60, "confidence": 0.8, "simulated": True}, "R03", rnd))
            if rate > 0 and rnd.random() < 0.0035:
                kind = rnd.choice(["zone_breach", "ppe_violation"])
                out.append(_ev(site, camera, t + timedelta(seconds=rnd.uniform(0, 299)), kind, 3,
                               {"zone": "press_1_exclusion" if kind == "zone_breach" else "press_line_work_area", "machine_id": 1, "track_id": rnd.randint(1, 999), "confidence": round(rnd.uniform(0.55, 0.95), 2), "simulated": True, **({"class": "no_helmet", "sustained_s": 2.4} if kind == "ppe_violation" else {})}, "R02" if kind == "zone_breach" else "R01", rnd))
        t += step
    out.sort(key=lambda e: e["ts"])
    return out


def _poisson(lam: float, rnd: random.Random) -> int:
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rnd.gauss(lam, math.sqrt(lam)))))
    l_, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rnd.random()
        if p <= l_:
            return k
        k += 1


def _ev(site, camera, ts, kind, sev, payload, rule, rnd) -> dict[str, Any]:
    return {"id": _ulid(ts, rnd), "site": site, "camera": camera, "ts": ts.isoformat(), "kind": kind, "severity": sev,
            "payload": payload, "clip_path": None, "rule_id": rule}
