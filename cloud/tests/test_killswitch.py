"""Kill switch: env + DB flag; run() raises AgentsDisabled; crew routes return 503; escalation still happens via Phase B."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from raqib_api.config import settings
from raqib_api.crew.crew import IDENTITIES, build_crew
from raqib_api.crew.killswitch import AgentsDisabled, enabled, set_enabled
from raqib_api.crew.runtime import Runtime
from raqib_api.models import Event
from tests.conftest import make_event


@pytest.fixture()
def session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


def test_env_and_flag_both_gate(session, monkeypatch):
    assert enabled(session)
    set_enabled(session, False, "admin", "drill")
    assert not enabled(session)
    set_enabled(session, True, "admin")
    assert enabled(session)
    monkeypatch.setattr(settings, "agents_enabled", False)
    assert not enabled(session)


def test_run_raises_agents_disabled(session):
    set_enabled(session, False, "admin")
    crew = build_crew(session, "s1")
    e = Event(id="01K" + "0" * 23, site="s1", camera="c", ts=datetime.now(UTC), kind="queue_over", severity=2, payload={"count": 5}, rule_id="R10")
    with pytest.raises(AgentsDisabled):
        Runtime(session, IDENTITIES).run(crew.agents["FloorOps"], "queue_over", {"site": "s1"}, event=e)


def test_routes_503_and_sev3_still_escalates(client, monkeypatch):
    assert client.get("/crew/status").json()["agents_enabled"] is True
    assert client.get("/crew/roster", params={"site": "raqib_demo_store"}).status_code == 200
    assert client.post("/crew/kill", json={"by": "admin", "confirm": "nope"}).status_code == 422
    r = client.post("/crew/kill", json={"by": "admin", "note": "drill", "confirm": "KILL"})
    assert r.status_code == 200 and r.json()["agents_enabled"] is False
    for path in ("/crew/roster", "/crew/runs", "/crew/messages", "/crew/actions"):
        assert client.get(path, params={"site": "raqib_demo_store"}).status_code == 503, path
    assert client.get("/crew/status").json()["agents_enabled"] is False
    # events keep flowing: a severity-3 event still escalates and alerts through the Phase B policy path
    ev = make_event(kind="zone_breach", severity=3, payload={"zone": "exclusion_1", "confidence": 0.9}, rule="R02")
    client.post("/events/batch", json={"events": [ev]})
    acts = client.get("/actions", params={"site": ev["site"], "limit": 50}).json()
    mine = [a for a in acts if a["event_id"] == ev["id"]]
    assert {a["tool"] for a in mine} >= {"escalate", "send_alert"} and all(a.get("agent") in (None, "") for a in mine)
    assert client.post("/crew/resume", json={"by": "admin"}).status_code == 200
    assert client.get("/crew/roster", params={"site": "raqib_demo_store"}).status_code == 200
    monkeypatch.setattr(settings, "agents_enabled", False)
    assert client.post("/crew/resume", json={"by": "admin"}).status_code == 409  # env wins
