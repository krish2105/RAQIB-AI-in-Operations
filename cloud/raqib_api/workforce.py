"""Workforce scheduling as a small integer program.

minimise  Σ_s tills_s              (staff-hours, each till = one cashier for the slot)
s.t.      λ_s / (tills_s · μ) <= max_rho   for every slot s   (utilisation cap)
          1 <= tills_s <= max_tills, integer
Solved with scipy.optimize.milp (HiGHS). The problem separates per slot, which is
why the closed form `tills_for_target_rho` gives the same answer; the MILP is kept
so the coupling constraints below (max change between adjacent slots, minimum
shift length) can be added without rewriting the model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from .ops_theory import mmc


@dataclass
class StaffingPlan:
    tills: list[int]
    lam: list[float]
    mu: float
    max_rho: float
    staff_hours: float
    rho: list[float]
    wq_min: list[float | None]
    baseline_tills: int
    baseline_staff_hours: float
    savings_hours: float
    slot_minutes: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def staffing_plan(lam: list[float], mu: float, max_rho: float = 0.85, max_tills: int = 6, slot_minutes: int = 15,
                  max_step: int | None = None) -> StaffingPlan:
    """λ per slot (per hour), μ per till per hour. Returns integer tills per slot."""
    n = len(lam)
    if n == 0:
        raise ValueError("need at least one slot")
    if mu <= 0:
        raise ValueError("mu must be positive")
    lam_arr = np.asarray(lam, dtype=float)
    # tills_s >= lam_s / (mu * max_rho)   ->  -tills_s <= -lam_s/(mu*max_rho)
    lower = np.maximum(1.0, lam_arr / (mu * max_rho))
    c = np.ones(n)
    constraints = [LinearConstraint(np.eye(n), lb=lower, ub=np.full(n, max_tills))]
    if max_step is not None and n > 1:
        d = np.zeros((n - 1, n))
        for i in range(n - 1):
            d[i, i], d[i, i + 1] = -1, 1
        constraints.append(LinearConstraint(d, lb=-max_step, ub=max_step))
    res = milp(c, constraints=constraints, integrality=np.ones(n), bounds=Bounds(1, max_tills))
    if not res.success:
        raise RuntimeError(f"MILP infeasible: {res.message}. Raise max_tills or max_rho.")
    tills = [int(round(x)) for x in res.x]
    rho = [float(l / (t * mu)) if t else 0.0 for l, t in zip(lam_arr, tills, strict=True)]
    wq = []
    for l, t in zip(lam_arr, tills, strict=True):
        r = mmc(float(l), mu, t)
        wq.append(None if not r.stable else round(r.wq * 60, 2))
    hours = slot_minutes / 60.0
    staff_hours = sum(tills) * hours
    baseline = max_tills if lam_arr.size else 1
    baseline_hours = baseline * n * hours
    return StaffingPlan(tills, [float(x) for x in lam_arr], mu, max_rho, round(staff_hours, 2), [round(r, 3) for r in rho],
                        wq, baseline, round(baseline_hours, 2), round(baseline_hours - staff_hours, 2), slot_minutes)
