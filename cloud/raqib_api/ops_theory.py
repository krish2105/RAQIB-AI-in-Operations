"""Queueing theory for the checkout line: M/M/c per 15-minute slot.

Arrival rate λ comes from `footfall_tick` events per slot (customers entering
the checkout area). Service rate μ per till comes from `checkout_served`
dwell times: μ = 1 / mean(dwell). Both are estimated from video, which is
stated in every output (`mu_source`). `c` is the number of open tills.

Assumptions (stated for the viva): Poisson arrivals, exponential service,
FCFS, one shared queue for c identical servers, steady state within a slot.
Real checkouts violate exponential service; the model-vs-observed card on the
dashboard is precisely there to show how much.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class MMCResult:
    lam: float
    mu: float
    c: int
    rho: float  # utilisation per server, λ/(cμ)
    p0: float  # probability system empty
    lq: float  # expected number waiting
    wq: float  # expected wait in queue (same time unit as rates)
    l: float  # expected number in system
    w: float  # expected time in system
    stable: bool

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("lq", "wq", "l", "w"):
            if math.isinf(d[k]):
                d[k] = None
        return d


def mmc(lam: float, mu: float, c: int) -> MMCResult:
    """Erlang-C. Rates in the same time unit; results in that unit."""
    if c < 1:
        raise ValueError("c must be >= 1")
    if mu <= 0:
        raise ValueError("mu must be > 0")
    if lam < 0:
        raise ValueError("lam must be >= 0")
    a = lam / mu  # offered load in Erlangs
    rho = a / c
    if lam == 0:
        return MMCResult(lam, mu, c, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, True)
    if rho >= 1:
        inf = math.inf
        return MMCResult(lam, mu, c, rho, 0.0, inf, inf, inf, inf, False)
    s = sum(a**n / math.factorial(n) for n in range(c))
    tail = (a**c / math.factorial(c)) * (1.0 / (1.0 - rho))
    p0 = 1.0 / (s + tail)
    lq = p0 * (a**c) * rho / (math.factorial(c) * (1.0 - rho) ** 2)
    wq = lq / lam
    l = lq + a
    w = wq + 1.0 / mu
    return MMCResult(lam, mu, c, rho, p0, lq, wq, l, w, True)


def tills_for_target_rho(lam: float, mu: float, max_rho: float = 0.85, max_c: int = 12) -> int:
    """Smallest c such that λ/(cμ) <= max_rho."""
    if lam <= 0:
        return 1
    c = max(1, math.ceil(lam / (mu * max_rho)))
    return min(c, max_c)


@dataclass
class SlotRates:
    slot_start: datetime
    lam_per_h: float
    mu_per_h: float
    served: int
    arrivals: int
    tills_open: int
    rho: float
    wq_model_min: float | None
    wq_observed_min: float | None
    queue_observed: float | None
    mu_source: str = "estimated_from_video"

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["slot_start"] = self.slot_start.isoformat()
        return d


def _floor_slot(ts: datetime, slot_min: int) -> datetime:
    return ts.replace(minute=(ts.minute // slot_min) * slot_min, second=0, microsecond=0)


def slot_rates(
    events: Iterable[Any],
    tills_open: int,
    slot_min: int = 15,
    default_mu_per_h: float = 30.0,
) -> list[SlotRates]:
    """Aggregate events into slots and compute M/M/c per slot.

    `events` need .ts, .kind, .payload. footfall_tick -> arrivals; checkout_served -> service
    completions with payload.dwell_s; queue_over -> observed queue length (payload.count).
    μ falls back to `default_mu_per_h` (2 min per customer) in slots with no completions.
    """
    slots: dict[datetime, dict[str, Any]] = {}
    for e in events:
        key = _floor_slot(e.ts, slot_min)
        s = slots.setdefault(key, {"arrivals": 0, "dwells": [], "queues": []})
        if e.kind == "footfall_tick":
            s["arrivals"] += 1
        elif e.kind == "checkout_served":
            d = e.payload.get("dwell_s")
            if d:
                s["dwells"].append(float(d))
        elif e.kind == "queue_over":
            s["queues"].append(float(e.payload.get("count", 0)))
    out: list[SlotRates] = []
    per_h = 60.0 / slot_min
    for key in sorted(slots):
        s = slots[key]
        lam = s["arrivals"] * per_h
        mu = (3600.0 / (sum(s["dwells"]) / len(s["dwells"]))) if s["dwells"] else default_mu_per_h
        c = max(1, tills_open)
        r = mmc(lam, mu, c)
        wq_model = None if math.isinf(r.wq) else r.wq * 60.0
        q_obs = (sum(s["queues"]) / len(s["queues"])) if s["queues"] else None
        # Little's law on the observed queue: Wq = Lq / λ
        wq_obs = (q_obs / lam * 60.0) if (q_obs is not None and lam > 0) else None
        out.append(SlotRates(key, lam, mu, len(s["dwells"]), s["arrivals"], c, r.rho, wq_model, wq_obs, q_obs))
    return out


def service_level(events: Iterable[Any], slot_min: int = 15, max_queue: int = 3, day_start: datetime | None = None,
                  day_end: datetime | None = None) -> float | None:
    """Share of slots whose worst observed queue was <= max_queue. Slots with no queue_over count as met."""
    events = list(events)
    if not events:
        return None
    start = _floor_slot(day_start or min(e.ts for e in events), slot_min)
    end = day_end or max(e.ts for e in events)
    worst: dict[datetime, float] = {}
    for e in events:
        if e.kind == "queue_over":
            k = _floor_slot(e.ts, slot_min)
            worst[k] = max(worst.get(k, 0), float(e.payload.get("count", 0)))
    n = 0
    met = 0
    t = start
    while t <= end:
        n += 1
        if worst.get(t, 0) <= max_queue:
            met += 1
        t += timedelta(minutes=slot_min)
    return met / n if n else None
