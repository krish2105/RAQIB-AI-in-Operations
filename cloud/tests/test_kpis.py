from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from raqib_api.kpis import compliance, downtime_minutes, osa, summary, time_to_restock

NOW = datetime(2026, 9, 6, 18, 0, tzinfo=UTC)


def ev(minutes_ago, kind, sev=1, **payload):
    return SimpleNamespace(ts=NOW - timedelta(minutes=minutes_ago), kind=kind, severity=sev, payload=payload)


def test_osa_is_one_minus_gap_fraction():
    # one gap signal 60 min ago, default gap 15 min -> 15/1440 lost
    events = [ev(60, "shelf_gap", shelf_id="A1")]
    got = osa(events, NOW, window_h=24, gap_default_min=15)
    assert abs(got["A1"] - (1 - 15 / 1440)) < 1e-9
    # continuous signals every 5 min for 30 min -> 6 signals: 5 gaps of 5 min + last 15 default = 40 min
    events = [ev(60 - 5 * i, "shelf_gap", shelf_id="B3") for i in range(6)]
    assert abs(osa(events, NOW)["B3"] - (1 - 40 / 1440)) < 1e-9


def test_time_to_restock_splits_episodes():
    events = [ev(300, "shelf_gap", shelf_id="A1"), ev(295, "shelf_gap", shelf_id="A1"),
              ev(60, "shelf_gap", shelf_id="A1")]
    ttr = time_to_restock(events, gap_default_min=15)
    assert abs(ttr["A1"] - ((5 + 15) + (0 + 15)) / 2) < 1e-9


def test_compliance_and_downtime():
    events = [ev(10, "ppe_violation", 3), ev(20, "machine_stopped", 2, stopped_s=600), ev(5, "machine_stopped", 2, stopped_s=300)]
    assert compliance(events, footfall=20) == 0.95
    assert compliance(events, footfall=0) is None
    assert downtime_minutes(events) == 15.0


def test_summary_retail_and_factory_shapes():
    events = [ev(30 - i, "footfall_tick") for i in range(10)] + [
        ev(20, "checkout_served", dwell_s=60), ev(15, "queue_over", 2, count=5), ev(40, "shelf_gap", shelf_id="A1", simulated=True)]
    r = summary(events, "retail", tills=3, now=NOW)
    assert r["footfall"] == 10 and r["avg_queue"] == 5.0
    assert r["service_level"] is not None and 0 <= r["service_level"] <= 1
    assert r["osa"]["A1"] < 1 and r["osa_store"] < 1
    assert r["queue_model"] and "rho" in r["queue_model"][0]
    assert 0 < r["simulated_share"] < 1
    f = summary([ev(5, "zone_breach", 3, machine_id=1), ev(3, "footfall_tick")], "factory", tills=1, now=NOW)
    assert f["breaches"] == 1 and f["compliance"] == 1.0 and f["downtime_min"] == 0.0
