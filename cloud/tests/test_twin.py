"""Twin: 1440-bin replay, deterministic what-if, +1 till at peak cuts wait and adds staff-hours."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from raqib_api.models import Event, Site
from raqib_api.simulate import generate
from raqib_api.twin.replay import MINUTES, build_timeline, replay
from raqib_api.twin.whatif import expand_tills, whatif

DAY = date(2026, 9, 4)  # a Friday in the seed
SITE = "raqib_demo_store"


@pytest.fixture(scope="module")
def eng():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(e)
    with Session(e) as s:
        s.add(Site(name=SITE, profile="retail", tills=3, floor={"zones": [{"name": "entrance", "kind": "entrance"}, {"name": "queue_till_1", "kind": "queue"},
                                                                          {"name": "checkout_till_1", "kind": "checkout"}, {"name": "shelf_b3", "kind": "shelf", "meta": {"shelf_id": "B3"}}]}))
        for r in generate(SITE, "retail", days=7, seed=7, end=datetime(2026, 9, 7, 0, 0, tzinfo=UTC), tills=3):
            r2 = dict(r)
            r2["ts"] = datetime.fromisoformat(r2["ts"])
            s.add(Event(**r2, handled=True))
        s.commit()
    return e


def test_replay_of_a_seeded_day_has_1440_bins(eng):
    with Session(eng) as s:
        tl = replay(SITE, DAY, s)
    d = tl.as_dict()
    assert d["bins"] == MINUTES and len(d["arrivals"]) == MINUTES and len(d["queue"]) == MINUTES
    assert d["totals"]["arrivals"] > 300 and d["totals"]["queue_alerts"] > 0 and d["totals"]["shelf_gaps"] >= 0
    assert set(d["occupancy"]) >= {"entrance", "queue_till_1", "checkout_till_1"}
    assert all(len(v) == MINUTES for v in d["occupancy"].values())
    assert d["simulated_share"] == 1.0 and all(e["kind"] not in ("footfall_tick", "checkout_served") for e in d["events"])
    # queue readings are held for 5 minutes and shelf availability never exceeds 1
    assert max(d["queue"]) == d["totals"]["peak_queue"] and all(0 <= x <= 1 for v in d["shelf"].values() for x in v)
    assert 8 * 60 <= d["totals"]["busiest_minute"] < 23 * 60  # inside opening hours


def test_build_timeline_is_pure_and_holds_queue_and_shelf():
    from raqib_api.tz import EventView

    start = datetime(2026, 9, 4, tzinfo=UTC)
    ev = [EventView(id="a", site=SITE, camera="c", ts=start.replace(hour=10, minute=0), kind="queue_over", severity=2, payload={"zone": "queue_till_1", "count": 6}, clip_path=None, rule_id="R10"),
          EventView(id="b", site=SITE, camera="c", ts=start.replace(hour=10, minute=2), kind="shelf_gap", severity=1, payload={"shelf_id": "B3", "empty_ratio": 0.6}, clip_path=None, rule_id="R11"),
          EventView(id="c", site=SITE, camera="c", ts=start.replace(hour=10, minute=1), kind="footfall_tick", severity=1, payload={"zone": "entrance"}, clip_path=None, rule_id="R12")]
    tl = build_timeline(SITE, DAY, ev)
    assert tl.queue[600] == 6 and tl.queue[604] == 6 and tl.queue[605] == 0
    assert tl.shelf["B3"][602] == pytest.approx(0.4) and tl.shelf["B3"][607] == 1.0
    assert tl.arrivals[601] == 1 and tl.occupancy["entrance"][601] == 1 and len(tl.events) == 2
    assert build_timeline(SITE, DAY, ev).as_dict() == tl.as_dict()  # deterministic


def test_whatif_plus_one_till_at_peak_cuts_wait_and_adds_staff_hours(eng):
    with Session(eng) as s:
        base = whatif(SITE, DAY, s)
        plus = whatif(SITE, DAY, s, staff_delta=1)
        express = whatif(SITE, DAY, s, zone_changes={"express_lane": True})
        again = whatif(SITE, DAY, s, staff_delta=1)
    assert base["sufficient"] and base["slots"] > 0
    assert plus["after"]["customer_wait_min"] < base["before"]["customer_wait_min"]
    assert plus["after"]["staff_hours"] > base["before"]["staff_hours"] and plus["delta"]["staff_hours"] == pytest.approx(plus["slots"] * 0.25, abs=0.01)
    assert plus["delta"]["wait_reduction_pct"] > 0 and plus["after"]["peak_rho"] < base["before"]["peak_rho"]
    assert express["after"]["staff_hours"] <= plus["after"]["staff_hours"] and express["after"]["customer_wait_min"] <= base["before"]["customer_wait_min"]
    assert base["milp"]["staff_hours"] <= base["before"]["staff_hours"] + 1e-9 or base["milp"]["unstable_slots"] <= base["before"]["unstable_slots"]
    assert again == plus  # identical inputs are deterministic


def test_expand_tills_per_hour_and_validation():
    assert expand_tills(None, 96) is None
    assert expand_tills([2] * 24, 96) == [2] * 96 and expand_tills(list(range(96)), 96)[95] == 95
    with pytest.raises(ValueError):
        expand_tills([1, 2, 3], 96)


def test_twin_api(client):
    client.post("/admin/seed", params={"site": SITE, "days": 3, "run_agent_last_hours": 0})
    day = (datetime.now(UTC).date().toordinal() - 1)
    d = date.fromordinal(day).isoformat()
    r = client.get("/twin/replay", params={"site": SITE, "date": d})
    assert r.status_code == 200 and r.json()["bins"] == 1440 and r.json()["totals"]["arrivals"] > 0
    assert client.get("/twin/replay", params={"site": SITE, "date": "nope"}).status_code == 422
    w = client.post("/twin/whatif", json={"site": SITE, "date": d, "staff_delta": 1})
    assert w.status_code == 200 and w.json()["sufficient"] and w.json()["delta"]["staff_hours"] > 0
    assert client.post("/twin/whatif", json={"site": SITE, "date": d, "tills_by_slot": [1, 2]}).status_code == 422
    empty = client.post("/twin/whatif", json={"site": SITE, "date": "2001-01-01"}).json()
    assert empty["sufficient"] is False
