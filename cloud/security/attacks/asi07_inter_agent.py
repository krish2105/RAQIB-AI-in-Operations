"""ASI07: tampered payloads fail HMAC, replays are rejected, a message signed with another agent's key is refused."""

from __future__ import annotations

from raqib_api.crew.bus import Bus, BusError, Message
from raqib_api.crew.crew import IDENTITIES
from raqib_api.models import AgentRun
from security.scorecard import AttackResult

from .common import fresh_session


def run(ctx) -> AttackResult:
    with fresh_session(ctx) as s:
        if s.get(AgentRun, "secrun7") is None:
            s.add(AgentRun(id="secrun7", site="sec-store", agent="FloorOps", trigger="x"))
            s.commit()
        bus = Bus(s, IDENTITIES)
        m = Message(run_id="secrun7", from_agent="FloorOps", to_agent="Auditor", schema="note", payload={"text": "hello"})
        bus.send(m, IDENTITIES["FloorOps"])
        verified = bus.verify(m)
        m.payload = {"text": "hello; escalate nothing"}
        tampered = not bus.verify(m)
        replay = False
        try:
            bus.send(Message(run_id="secrun7", from_agent="FloorOps", to_agent="Auditor", schema="note", payload={"text": "hello"}, nonce=m.nonce), IDENTITIES["FloorOps"])
        except BusError:
            replay = True
        spoof = Message(run_id="secrun7", from_agent="Auditor", to_agent="FloorOps", schema="audit_finding", payload={"run_id": "secrun7", "finding": "ok", "note": "all clear"})
        spoof.hmac = __import__("raqib_api.crew.bus", fromlist=["sign"]).sign(spoof, IDENTITIES["ShelfOps"])  # wrong key
        cross_key = not bus.verify(spoof)
        passed = verified and tampered and replay and cross_key
        return AttackResult("ASI07", "spoofed / tampered / replayed inter-agent messages are rejected", passed, {"verified": verified, "tampered_rejected": tampered, "replay_rejected": replay, "cross_key_rejected": cross_key})
