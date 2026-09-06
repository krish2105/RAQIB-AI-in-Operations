"""Per-run budgets: tool calls, dollars (zero in v2), seconds. A breach aborts the run."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from raqib_api.agent.tools import Call, ToolResult
from raqib_api.crew.budget import Budget, BudgetExceeded, BudgetMeter
from raqib_api.crew.crew import IDENTITIES
from raqib_api.crew.identity import AgentIdentity
from raqib_api.crew.runtime import Plan, Runtime
from raqib_api.models import Action, Event


class Spammer:
    identity = AgentIdentity(name="FloorOps", role="x", allowed_tools=frozenset({"send_alert"}), budget=Budget(max_tool_calls=3, max_usd=0.0, max_seconds=60))
    triggers = ["queue_over"]

    def plan(self, event, ctx, session):
        call = Call("send_alert", {"channel": "console", "lang": "en", "template": "queue_over", "vars": {}}, "spam")
        return Plan(calls=[call] * 8, rationale="flood")


class PaidRunner:
    def __init__(self, session):
        self.session = session

    def execute(self, call, action_id=None, ctx=None):
        return ToolResult(ok=True, output={"paid": True}, cost_usd=0.01)


@pytest.fixture()
def session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


def _event(session):
    e = Event(id="01Q" + "0" * 23, site="s1", camera="cam1", ts=datetime.now(UTC), kind="queue_over", severity=2, payload={"count": 6, "zone": "q"}, rule_id="R10")
    session.add(e)
    session.commit()
    return e


def test_meter_breaches():
    m = BudgetMeter(Budget(max_tool_calls=2, max_usd=0.0, max_seconds=60))
    m.charge_call(0.0)
    m.charge_call(0.0)
    with pytest.raises(BudgetExceeded, match="tool_calls"):
        m.charge_call(0.0)
    m2 = BudgetMeter(Budget(max_tool_calls=5, max_usd=0.0, max_seconds=60))
    with pytest.raises(BudgetExceeded, match="usd"):
        m2.charge_call(0.001)  # zero-cost policy: any paid call is a breach


def test_run_aborts_with_budget_exceeded_and_stops_executing(session):
    e = _event(session)
    rt = Runtime(session, IDENTITIES)
    out = rt.run(Spammer(), "queue_over", {"site": "s1", "lang": "en"}, event=e, audit=False)
    assert out.run.status == "budget_exceeded" and "tool_calls 4 > 3" in out.run.meta["breach"]
    executed = session.exec(select(Action).where(Action.run_id == out.run.id)).all()
    assert len(executed) == 4 and out.run.tool_calls == 4  # the 4th call tripped the meter; nothing after it ran


def test_paid_tool_call_breaches_zero_dollar_budget(session):
    e = _event(session)
    rt = Runtime(session, IDENTITIES, runner=PaidRunner(session))
    out = rt.run(Spammer(), "queue_over", {"site": "s1", "lang": "en"}, event=e, audit=False)
    assert out.run.status == "budget_exceeded" and "usd" in out.run.meta["breach"] and out.run.cost_usd == 0.01
