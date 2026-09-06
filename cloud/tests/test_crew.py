"""The six agents on one runtime: allow-lists enforced, Auditor after every run, attribution on every proposal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from raqib_api.agent.tools import Call
from raqib_api.crew.agents.analyst import Analyst
from raqib_api.crew.agents.floor_ops import FloorOps
from raqib_api.crew.bus import Bus, BusError, Message
from raqib_api.crew.crew import IDENTITIES, build_crew
from raqib_api.crew.runtime import Plan
from raqib_api.models import Action, AgentMessage, AgentRun, Event, Site
from tests.conftest import make_event


@pytest.fixture()
def session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Site(name="s1", profile="retail", tills=3))
        s.commit()
        yield s


class RogueFloorOps(FloorOps):
    def plan(self, event, ctx, session):
        p = super().plan(event, ctx, session)
        p.calls.append(Call("create_work_order", {"machine_id": "press-1", "summary": "FloorOps should not do this", "severity": 2}, "rogue"))
        return p


def _queue(session, count=7):
    e = Event(id="01Q" + "0" * 23, site="s1", camera="cam1", ts=datetime.now(UTC), kind="queue_over", severity=2,
              payload={"zone": "queue_till_1", "till": 1, "count": count, "sustained_s": 90, "confidence": 0.85}, rule_id="R10")
    session.add(e)
    session.commit()
    return e


def test_auditor_flags_a_run_that_attempted_a_denied_tool(session):
    crew = build_crew(session, "s1")
    e = _queue(session)
    out = crew.runtime.run(RogueFloorOps(), "queue_over", {"site": "s1", "lang": "en", "rho": 0.5}, event=e)
    assert out.denied == ["create_work_order"]
    assert not session.exec(select(Action).where(Action.tool == "create_work_order")).all()  # never reached Policy or the runner
    run = session.get(AgentRun, out.run.id)
    assert run.status == "flagged" and run.meta["flag"]["finding"] == "tool_misuse" and "create_work_order" in run.meta["flag"]["note"]
    audit = session.exec(select(AgentRun).where(AgentRun.agent == "Auditor")).one()
    assert audit.trigger == f"audit:{out.run.id}" and audit.status == "ok"
    flag = session.exec(select(Action).where(Action.tool == "flag_run")).one()
    assert flag.agent == "Auditor" and flag.run_id == audit.id and flag.status == "executed"
    reports = session.exec(select(AgentMessage).where(AgentMessage.schema_name == "run_report")).all()
    assert any(m.payload["denied"] == ["create_work_order"] for m in reports)


def test_analyst_has_no_tools_and_a_tool_call_is_rejected(session):
    assert IDENTITIES["Analyst"].allowed_tools == frozenset()

    class ChattyAnalyst(Analyst):
        def plan(self, event, ctx, session):
            return Plan(calls=[Call("send_alert", {"channel": "console", "lang": "en", "template": "queue_over", "vars": {}}, "x")], rationale="analyst tries a tool")

    crew = build_crew(session, "s1")
    out = crew.runtime.run(ChattyAnalyst(), "weekly", {"site": "s1", "lang": "en"})
    assert out.denied == ["send_alert"] and out.actions == []
    assert session.get(AgentRun, out.run.id).status == "flagged"
    # and the bus refuses a "proposal" from an agent that has nothing to propose with
    bus = Bus(session, IDENTITIES)
    with pytest.raises(BusError):
        bus.send(Message(run_id=out.run.id, from_agent="Analyst", to_agent="Auditor", schema="proposal", payload={"tool": "send_alert"}), IDENTITIES["Analyst"])


def test_every_proposal_row_has_agent_and_run_id(session):
    crew = build_crew(session, "s1")
    e = _queue(session)
    out = crew.runtime.run(crew.agents["FloorOps"], "queue_over", {"site": "s1", "lang": "en", "rho": 0.93, "next_till": 2, "window": "now+30m"}, event=e)
    assert out.run.status == "ok"
    rows = session.exec(select(Action).where(Action.run_id == out.run.id)).all()
    assert {a.tool for a in rows} == {"send_alert", "propose_open_till"}
    assert all(a.agent == "FloorOps" and a.run_id == out.run.id for a in rows)
    proposal = next(a for a in rows if a.tool == "propose_open_till")
    assert proposal.status == "proposed" and proposal.args["rho"] == 0.93 and "event:" in proposal.reasoning
    audit = session.exec(select(AgentRun).where(AgentRun.agent == "Auditor")).one()
    assert audit.status == "ok" and session.get(AgentRun, out.run.id).status == "ok"  # nothing to flag


def test_shelf_ops_restock_and_merchandising_flag(session):
    crew = build_crew(session, "s1")
    now = datetime.now(UTC)
    for i in range(3):
        session.add(Event(id=f"01S{i:023d}", site="s1", camera="cam1", ts=now - timedelta(hours=i + 1), kind="shelf_gap", severity=1, payload={"shelf_id": "B3"}, rule_id="R11"))
    e = Event(id="01S" + "9" * 23, site="s1", camera="cam1", ts=now, kind="shelf_gap", severity=1,
              payload={"zone": "shelf_b3", "shelf_id": "B3", "product": "dairy", "empty_ratio": 0.6, "sustained_s": 600, "confidence": 0.8}, rule_id="R11")
    session.add(e)
    session.commit()
    out = crew.runtime.run(crew.agents["ShelfOps"], "shelf_gap", {"site": "s1", "lang": "en"}, event=e)
    tools = {a.tool: a for a in session.exec(select(Action).where(Action.run_id == out.run.id)).all()}
    assert set(tools) == {"create_restock_task", "flag_merchandising"}
    assert tools["create_restock_task"].status == "executed" and tools["create_restock_task"].args["osa_impact_pct"] == 10.0
    assert tools["create_restock_task"].agent == "ShelfOps"


def test_ingest_routes_to_the_crew_and_safety_handles_sev3(client):
    site = "raqib_demo_store"
    q = make_event(kind="queue_over", severity=2, payload={"zone": "queue_till_1", "till": 1, "count": 8, "sustained_s": 120, "confidence": 0.9}, rule="R10")
    z = make_event(i=5, kind="zone_breach", severity=3, payload={"zone": "exclusion_1", "confidence": 0.9}, rule="R02")
    r = client.post("/events/batch", json={"events": [q, z]})
    assert r.status_code == 201
    acts = client.get("/actions", params={"site": site, "limit": 100}).json()
    by_event = {}
    for a in acts:
        by_event.setdefault(a["event_id"], []).append(a)
    assert {a["tool"] for a in by_event[q["id"]]} >= {"send_alert"} and all(a["agent"] == "FloorOps" and a["run_id"] for a in by_event[q["id"]])
    assert {a["tool"] for a in by_event[z["id"]]} >= {"escalate", "send_alert"} and all(a["agent"] == "Safety" for a in by_event[z["id"]])
    runs = client.get("/crew/runs", params={"site": site}).json()
    assert {r["agent"] for r in runs} >= {"FloorOps", "Safety", "Auditor"}
    roster = client.get("/crew/roster", params={"site": site}).json()
    assert [a["name"] for a in roster] == ["FloorOps", "ShelfOps", "Workforce", "Safety", "Analyst", "Auditor"]
    assert next(a for a in roster if a["name"] == "Auditor")["mandatory"] and next(a for a in roster if a["name"] == "Analyst")["allowed_tools"] == []
    msgs = client.get("/crew/messages", params={"site": site}).json()
    assert msgs and all(m["verified"] for m in msgs)
    crew_acts = client.get("/crew/actions", params={"site": site}).json()
    assert all(a["agent"] and a["run_id"] for a in crew_acts)
