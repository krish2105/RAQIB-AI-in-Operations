"""What-if: re-run slot_rates -> mmc -> service level and the staffing MILP under overrides.

Overrides: tills_by_slot (one integer per 15-minute slot, or per hour), staff_delta (+/- tills in every slot,
floor 1), zone_changes {"express_lane": true} (one extra till in every slot whose utilisation exceeds 0.85).
Identical inputs give identical outputs: everything is arithmetic on the day's events.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlmodel import Session

from ..models import Site
from ..ops_theory import mmc, slot_rates, tills_for_target_rho
from ..workforce import staffing_plan
from .replay import day_events

SLOT_MIN = 15
SLOTS_PER_DAY = 24 * 60 // SLOT_MIN


@dataclass
class DayKpis:
    tills: list[int]
    staff_hours: float
    customer_wait_min: float  # sum over slots of Wq * arrivals
    mean_wq_min: float
    peak_rho: float
    service_level_model: float  # share of slots with modelled Lq <= 3
    unstable_slots: int
    per_slot: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"tills": self.tills, "staff_hours": round(self.staff_hours, 2), "customer_wait_min": round(self.customer_wait_min, 1),
                "mean_wq_min": round(self.mean_wq_min, 2), "peak_rho": round(self.peak_rho, 3), "service_level_model": round(self.service_level_model, 3),
                "unstable_slots": self.unstable_slots, "per_slot": self.per_slot}


def evaluate(slots, mu: float, tills: list[int]) -> DayKpis:
    wait = 0.0
    wqs: list[float] = []
    met = 0
    unstable = 0
    peak = 0.0
    per_slot = []
    for s, c in zip(slots, tills, strict=True):
        r = mmc(s.lam_per_h, mu, max(1, c))
        peak = max(peak, r.rho)
        if r.stable:
            wq_min = r.wq * 60.0
            wait += wq_min * s.arrivals
            wqs.append(wq_min)
            if r.lq <= 3:
                met += 1
        else:
            unstable += 1
            wait += 30.0 * s.arrivals
            wqs.append(30.0)
        per_slot.append({"slot": s.slot_start.isoformat(), "lam": round(s.lam_per_h, 1), "tills": max(1, c), "rho": round(r.rho, 3),
                         "wq_min": None if math.isinf(r.wq) else round(r.wq * 60, 2), "arrivals": s.arrivals})
    n = len(slots) or 1
    return DayKpis(tills=[max(1, c) for c in tills], staff_hours=sum(max(1, c) for c in tills) * SLOT_MIN / 60.0, customer_wait_min=wait,
                   mean_wq_min=sum(wqs) / n, peak_rho=peak, service_level_model=met / n, unstable_slots=unstable, per_slot=per_slot)


def expand_tills(spec: list[int] | None, n: int) -> list[int] | None:
    if not spec:
        return None
    if len(spec) == n:
        return [int(x) for x in spec]
    if len(spec) == 24:  # per hour
        return [int(spec[min(23, (i * SLOT_MIN) // 60)]) for i in range(n)]
    raise ValueError(f"tills_by_slot must have {n} (per slot) or 24 (per hour) entries")


def whatif(site: str, day: date, session: Session, *, tills_by_slot: list[int] | None = None, staff_delta: int = 0,
           zone_changes: dict[str, Any] | None = None, max_rho: float = 0.85) -> dict[str, Any]:
    s = session.get(Site, site)
    base_tills = s.tills if s else 3
    events = day_events(site, day, session)
    slots = slot_rates(events, tills_open=base_tills, slot_min=SLOT_MIN)
    if not slots:
        return {"site": site, "day": day.isoformat(), "sufficient": False, "reason": "no events on this day"}
    mus = [x.mu_per_h for x in slots if x.served > 0]
    mu = sum(mus) / len(mus) if mus else 30.0
    lam = [x.lam_per_h for x in slots]
    before = evaluate(slots, mu, [base_tills] * len(slots))
    ceiling = max(base_tills, 3, tills_for_target_rho(max(lam), mu, max_rho))
    plan = staffing_plan(lam, mu, max_rho=max_rho, max_tills=ceiling, baseline_tills=base_tills)
    milp = evaluate(slots, mu, list(plan.tills))
    after_tills = expand_tills(tills_by_slot, len(slots)) or [base_tills] * len(slots)
    if staff_delta:
        after_tills = [max(1, c + int(staff_delta)) for c in after_tills]
    zc = zone_changes or {}
    if zc.get("express_lane"):
        after_tills = [c + 1 if mmc(x.lam_per_h, mu, max(1, c)).rho > max_rho else c for x, c in zip(slots, after_tills, strict=True)]
    after = evaluate(slots, mu, after_tills)
    delta = {"staff_hours": round(after.staff_hours - before.staff_hours, 2), "customer_wait_min": round(after.customer_wait_min - before.customer_wait_min, 1),
             "wait_reduction_pct": round((1 - after.customer_wait_min / before.customer_wait_min) * 100, 1) if before.customer_wait_min > 0 else 0.0,
             "service_level_model": round(after.service_level_model - before.service_level_model, 3), "peak_rho": round(after.peak_rho - before.peak_rho, 3)}
    return {"site": site, "day": day.isoformat(), "sufficient": True, "slots": len(slots), "slot_minutes": SLOT_MIN, "mu_per_h": round(mu, 2),
            "mu_source": slots[0].mu_source, "baseline_tills": base_tills, "inputs": {"tills_by_slot": tills_by_slot, "staff_delta": staff_delta, "zone_changes": zc},
            "before": before.as_dict(), "after": after.as_dict(), "milp": milp.as_dict(), "delta": delta}
