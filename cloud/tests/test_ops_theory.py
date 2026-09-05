import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from raqib_api.ops_theory import mmc, service_level, slot_rates, tills_for_target_rho


def test_mm2_textbook_example():
    # Hillier & Lieberman style: λ=4/h, μ=3/h, c=2 -> ρ=2/3, P0=0.2, Lq=1.0667, Wq=0.2667 h
    r = mmc(4, 3, 2)
    assert r.stable
    assert abs(r.rho - 2 / 3) < 1e-9
    assert abs(r.p0 - 0.2) < 1e-6
    assert abs(r.lq - 1.0667) < 1e-3
    assert abs(r.wq - 0.2667) < 1e-3
    assert abs(r.l - (r.lq + 4 / 3)) < 1e-9
    assert abs(r.w - (r.wq + 1 / 3)) < 1e-9


def test_c1_reduces_to_mm1():
    lam, mu = 2.0, 5.0
    r = mmc(lam, mu, 1)
    rho = lam / mu
    assert abs(r.lq - rho**2 / (1 - rho)) < 1e-9
    assert abs(r.wq - lam / (mu * (mu - lam))) < 1e-9
    assert abs(r.p0 - (1 - rho)) < 1e-9


def test_unstable_system_reports_inf_and_rho():
    r = mmc(10, 3, 2)
    assert not r.stable and r.rho > 1 and math.isinf(r.wq)
    assert r.as_dict()["wq"] is None


def test_zero_arrivals_and_bad_inputs():
    assert mmc(0, 3, 2).wq == 0.0
    with pytest.raises(ValueError):
        mmc(1, 0, 1)
    with pytest.raises(ValueError):
        mmc(1, 1, 0)


def test_tills_for_target_rho():
    assert tills_for_target_rho(lam=40, mu=30, max_rho=0.85) == 2   # 40/(2*30)=0.67
    assert tills_for_target_rho(lam=80, mu=30, max_rho=0.85) == 4   # 80/(3*30)=0.89 > 0.85 -> 4
    assert tills_for_target_rho(lam=0, mu=30) == 1


def _ev(ts, kind, **payload):
    return SimpleNamespace(ts=ts, kind=kind, payload=payload)


def test_slot_rates_from_events():
    t0 = datetime(2026, 9, 6, 10, 0, tzinfo=UTC)
    events = []
    for i in range(12):  # 12 arrivals in 15 min -> λ = 48/h
        events.append(_ev(t0 + timedelta(seconds=60 * i), "footfall_tick"))
    for i in range(6):  # 6 served, mean dwell 90 s -> μ = 40/h per till
        events.append(_ev(t0 + timedelta(seconds=100 * i + 5), "checkout_served", dwell_s=90))
    events.append(_ev(t0 + timedelta(minutes=8), "queue_over", count=4))
    slots = slot_rates(events, tills_open=2)
    assert len(slots) == 1
    s = slots[0]
    assert s.arrivals == 12 and s.lam_per_h == 48.0
    assert abs(s.mu_per_h - 40.0) < 1e-9
    assert abs(s.rho - 48 / 80) < 1e-9
    assert s.wq_model_min is not None and s.wq_model_min > 0
    assert s.queue_observed == 4.0
    assert s.wq_observed_min == pytest.approx(4 / 48 * 60)
    assert s.mu_source == "estimated_from_video"


def test_service_level_counts_quiet_slots_as_met():
    t0 = datetime(2026, 9, 6, 10, 0, tzinfo=UTC)
    events = [_ev(t0, "footfall_tick"), _ev(t0 + timedelta(minutes=50), "queue_over", count=6),
              _ev(t0 + timedelta(minutes=59), "footfall_tick")]
    # slots 10:00,10:15,10:30,10:45 -> one breached (10:45) -> 0.75
    assert service_level(events, slot_min=15, max_queue=3) == 0.75
    assert service_level([], slot_min=15) is None
