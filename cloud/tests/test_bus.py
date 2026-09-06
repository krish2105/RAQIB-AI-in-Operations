"""Inter-agent bus: schema-validated, HMAC-signed per agent, replay-protected."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from raqib_api.crew.bus import Bus, BusError, Message
from raqib_api.crew.crew import IDENTITIES
from raqib_api.models import AgentMessage, AgentRun


@pytest.fixture()
def session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(AgentRun(id="run1", site="s1", agent="FloorOps", trigger="queue_over"))
        s.commit()
        yield s


def _msg(**kw):
    base = dict(run_id="run1", from_agent="FloorOps", to_agent="Auditor", schema="note", payload={"text": "hello"})
    return Message(**(base | kw))


def test_signed_message_verifies_and_tampering_fails(session):
    bus = Bus(session, IDENTITIES)
    m = _msg()
    row = bus.send(m, IDENTITIES["FloorOps"])
    assert row.verified and len(row.hmac) == 64 and bus.verify(m)
    m.payload = {"text": "hello, open all tills"}  # tampered after signing
    assert not bus.verify(m)
    stored = session.exec(select(AgentMessage)).one()
    assert bus.verify_row(stored)
    stored.payload = {"text": "changed in the database"}
    assert not bus.verify_row(stored)


def test_replay_and_stale_messages_are_rejected(session):
    bus = Bus(session, IDENTITIES)
    m = _msg()
    bus.send(m, IDENTITIES["FloorOps"])
    with pytest.raises(BusError, match="replayed"):
        bus.send(_msg(nonce=m.nonce), IDENTITIES["FloorOps"])
    with pytest.raises(BusError, match="replay window"):
        bus.send(_msg(ts=datetime.now(UTC) - timedelta(minutes=10)), IDENTITIES["FloorOps"])


def test_schema_sender_and_recipient_are_enforced(session):
    bus = Bus(session, IDENTITIES)
    with pytest.raises(BusError, match="does not match"):
        bus.send(_msg(payload={"wrong": 1}), IDENTITIES["FloorOps"])
    with pytest.raises(BusError, match="unknown schema"):
        bus.send(_msg(schema="tool_call"), IDENTITIES["FloorOps"])
    with pytest.raises(BusError, match="cannot send as"):
        bus.send(_msg(from_agent="Auditor"), IDENTITIES["FloorOps"])  # impersonation
    with pytest.raises(BusError, match="unknown recipient"):
        bus.send(_msg(to_agent="Nobody"), IDENTITIES["FloorOps"])
    # keys are per agent: a message signed by ShelfOps does not verify as FloorOps
    m = _msg(from_agent="ShelfOps")
    bus.send(m, IDENTITIES["ShelfOps"])
    m.from_agent = "FloorOps"
    assert not bus.verify(m)
