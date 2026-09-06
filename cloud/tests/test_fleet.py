"""Fleet: PSI drift raises model_drift; heartbeat gap marks a box offline and emits edge_offline once; leaderboard sorts."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from raqib_api.fleet.drift import analyse, check_and_emit, psi
from raqib_api.fleet.health import boxes, check_offline, status_of
from raqib_api.fleet.stores import leaderboard
from raqib_api.models import DriftSample, EdgeHeartbeat, Event, Site, Store

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


@pytest.fixture()
def session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Site(name="s1", profile="retail", tills=3))
        s.add(Site(name="s2", profile="retail", tills=2))
        s.commit()
        yield s


PER_HOUR = 30  # the edge posts one sample every two minutes


def _samples(session, camera="cam1", hours=7 * 24, conf=0.8, det=12.0, seed=1, site="s1", start=None, end_offset_h=0, blur=40.0):
    rnd = random.Random(seed)
    start = start or (NOW - timedelta(hours=hours + end_offset_h))
    for i in range(hours * PER_HOUR):
        session.add(DriftSample(site=site, camera=camera, ts=start + timedelta(minutes=2 * i), det_count=max(0.0, rnd.gauss(det, 2.0)),
                                mean_conf=min(1.0, max(0.0, rnd.gauss(conf, 0.03))), brightness=rnd.gauss(120, 5), blur=rnd.gauss(blur, 4)))
    session.commit()


def test_psi_zero_for_same_distribution_and_high_for_a_shift():
    rnd = random.Random(0)
    base = [rnd.gauss(0.8, 0.03) for _ in range(2000)]
    same = [rnd.gauss(0.8, 0.03) for _ in range(60)]
    shifted = [rnd.gauss(0.55, 0.03) for _ in range(60)]
    assert psi(base, same) < 0.2 and psi(base, shifted) > 1.0 and psi(base, []) == 0.0 and psi(base[:50], same) == 0.0


def test_injected_confidence_drop_raises_model_drift_once(session):
    _samples(session, hours=5 * 24, end_offset_h=3)  # five healthy days up to now-3h, then three bad hours
    _samples(session, hours=3, conf=0.5, seed=9)
    d = analyse("s1", "cam1", session, NOW)
    assert d.psi_conf > 0.2 and d.hours_over >= 3 and d.suggestion == "relabel"
    ev = check_and_emit("s1", session, NOW)
    assert len(ev) == 1 and ev[0].kind == "model_drift" and ev[0].severity == 2 and ev[0].payload["suggestion"] == "relabel"
    assert check_and_emit("s1", session, NOW) == []  # cooldown: not repeated
    assert len(session.exec(select(Event).where(Event.kind == "model_drift")).all()) == 1
    # a lens problem is diagnosed differently
    _samples(session, camera="cam2", hours=48, seed=2, end_offset_h=3)
    _samples(session, camera="cam2", hours=3, conf=0.55, seed=3, blur=120.0)
    assert analyse("s1", "cam2", session, NOW).suggestion == "clean_lens"


def test_healthy_camera_has_no_drift(session):
    _samples(session, hours=48)
    d = analyse("s1", "cam1", session, NOW)
    assert d.psi < 0.2 and d.hours_over == 0 and d.suggestion is None and check_and_emit("s1", session, NOW) == []


def test_heartbeat_gap_marks_offline_and_emits_once(session):
    session.add(EdgeHeartbeat(site="s1", box_id="mac-mini-1", ts=NOW - timedelta(seconds=30), fps=18.0, queue_depth=0, model_hash="abc123def456", cameras=["cam1"]))
    session.add(EdgeHeartbeat(site="s1", box_id="jetson-2", ts=NOW - timedelta(minutes=6), fps=12.0, queue_depth=40, model_hash="deadbeef"))
    session.commit()
    b = {x["box_id"]: x for x in boxes("s1", session, NOW)}
    assert b["mac-mini-1"]["status"] == "online" and b["jetson-2"]["status"] == "offline" and b["jetson-2"]["gap_s"] == 360
    assert status_of(EdgeHeartbeat(site="s1", box_id="x", ts=NOW - timedelta(minutes=3), fps=20), NOW) == "degraded"
    assert status_of(EdgeHeartbeat(site="s1", box_id="x", ts=NOW, fps=2), NOW) == "degraded"
    ev = check_offline("s1", session, NOW)
    assert len(ev) == 1 and ev[0].kind == "edge_offline" and ev[0].payload["box_id"] == "jetson-2"
    assert check_offline("s1", session, NOW + timedelta(minutes=1)) == []  # once per outage
    session.add(EdgeHeartbeat(site="s1", box_id="jetson-2", ts=NOW + timedelta(minutes=2), fps=12.0))
    session.commit()
    assert {x["box_id"]: x["status"] for x in boxes("s1", session, NOW + timedelta(minutes=2))}["jetson-2"] == "online"
    session.add(EdgeHeartbeat(site="s1", box_id="jetson-2", ts=NOW + timedelta(minutes=2), fps=12.0))
    session.commit()
    again = check_offline("s1", session, NOW + timedelta(minutes=20))  # a new outage emits again (both boxes are stale by now)
    assert {e.payload["box_id"] for e in again} == {"jetson-2", "mac-mini-1"}


def test_leaderboard_sorts_by_chosen_kpi(session):
    session.add(Store(id="a", name="A", site_ids=["s1"], region="x"))
    session.add(Store(id="b", name="B", site_ids=["s2"], region="y"))
    from tests.conftest import make_event

    for i in range(6):  # s1 has bad queues, s2 is quiet
        e = make_event(i, kind="queue_over", severity=2, site="s1", payload={"zone": "q", "count": 8}, ts=NOW - timedelta(minutes=10 * i))
        e["ts"] = datetime.fromisoformat(e["ts"])
        session.add(Event(**e))
    for i in range(20):
        e = make_event(100 + i, site="s2", payload={"zone": "entrance"}, ts=NOW - timedelta(minutes=3 * i))
        e["ts"] = datetime.fromisoformat(e["ts"])
        session.add(Event(**e))
    session.commit()
    rows = leaderboard(session, "service_level", 24, NOW)
    assert rows[0]["service_level"] is not None and rows[0]["id"] == "b" and rows[0]["rank"] == 1
    by_events = leaderboard(session, "events", 24, NOW)
    assert by_events[0]["id"] == "b"  # 20 events vs 6
    by_cost = leaderboard(session, "agent_cost_usd", 24, NOW)
    assert [r["agent_cost_usd"] for r in by_cost] == sorted(r["agent_cost_usd"] for r in by_cost)
    with pytest.raises(ValueError):
        leaderboard(session, "nope")


def test_fleet_api(client):
    site = "raqib_demo_store"
    hb = client.post("/fleet/heartbeat", json={"site": site, "box_id": "mac-1", "fps": 17.2, "queue_depth": 3, "model_hash": "abcdef0123456789", "detector": "yolo", "version": "0.1.0", "cameras": ["cam1", "cam2"]})
    assert hb.status_code == 202
    h = client.get("/fleet/health", params={"site": site}).json()
    assert h["boxes"][0]["status"] == "online" and h["boxes"][0]["model_hash"] == "abcdef012345" and h["boxes"][0]["cameras"] == ["cam1", "cam2"]
    now = datetime.now(UTC)
    rnd = random.Random(4)
    good = [{"site": site, "camera": "cam1", "ts": (now - timedelta(hours=3, minutes=2 * i)).isoformat(), "det_count": max(0.0, rnd.gauss(11, 2)),
             "mean_conf": min(1.0, max(0.0, rnd.gauss(0.8, 0.03))), "brightness": 120, "blur": 40} for i in range(36 * 30)]  # 36 healthy hours before the last 3
    for i in range(0, len(good), 500):
        assert client.post("/fleet/drift", json=good[i:i + 500]).status_code == 202
    d = client.get("/fleet/drift", params={"site": site}).json()
    assert d["cameras"][0]["camera"] == "cam1" and d["cameras"][0]["hours_over"] == 0 and d["cameras"][0]["psi"] < 0.2
    bad = [{"site": site, "camera": "cam1", "ts": (now - timedelta(minutes=2 * i)).isoformat(), "det_count": 11, "mean_conf": min(1.0, max(0.0, rnd.gauss(0.45, 0.03))), "brightness": 120, "blur": 40} for i in range(90)]
    r = client.post("/fleet/drift", json=bad).json()
    assert len(r["model_drift_events"]) == 1
    assert client.get("/events", params={"site": site, "kind": "model_drift"}).json()[0]["payload"]["suggestion"] == "relabel"
    lb = client.get("/fleet/leaderboard", params={"kpi": "events"}).json()
    assert [s["id"] for s in lb["stores"]][:1] == ["demo-store"] and lb["stores"][0]["edge"]["online"] == 1
    assert client.get("/fleet/leaderboard", params={"kpi": "nope"}).status_code == 422
    assert client.get("/fleet/stores").json()[0]["id"] == "demo-store"
