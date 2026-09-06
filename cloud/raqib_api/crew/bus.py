"""Typed, schema-validated, HMAC-signed inter-agent messages with replay protection.

send(): validate the payload against the named schema, sign with the SENDER's key, reject replays
(nonce seen, or timestamp outside the window), persist as AgentMessage. verify(): recompute the HMAC
for a stored/received message. No agent may call a tool through the bus: messages carry data only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import jsonschema
from sqlmodel import Session
from ulid import ULID

from ..models import AgentMessage
from .identity import AgentIdentity

REPLAY_WINDOW = timedelta(minutes=5)

SCHEMAS: dict[str, dict[str, Any]] = {
    "proposal": {"type": "object", "properties": {"tool": {"type": "string"}, "args": {"type": "object"}, "evidence": {"type": "array", "items": {"type": "string"}},
                                                  "rationale": {"type": "string", "maxLength": 800}},
                 "required": ["tool", "args", "evidence", "rationale"], "additionalProperties": False},
    "run_report": {"type": "object", "properties": {"run_id": {"type": "string"}, "agent": {"type": "string"}, "status": {"type": "string"},
                                                    "tool_calls": {"type": "integer"}, "denied": {"type": "array", "items": {"type": "string"}},
                                                    "dropped": {"type": "array", "items": {"type": "string"}}, "cost_usd": {"type": "number"}},
                   "required": ["run_id", "agent", "status", "tool_calls", "denied", "dropped", "cost_usd"], "additionalProperties": False},
    "audit_finding": {"type": "object", "properties": {"run_id": {"type": "string"}, "finding": {"type": "string"}, "note": {"type": "string", "maxLength": 400}},
                      "required": ["run_id", "finding", "note"], "additionalProperties": False},
    "note": {"type": "object", "properties": {"text": {"type": "string", "maxLength": 2000}}, "required": ["text"], "additionalProperties": False},
}


class BusError(ValueError):
    pass


@dataclass
class Message:
    run_id: str
    from_agent: str
    to_agent: str
    schema: str
    payload: dict[str, Any]
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))
    nonce: str = field(default_factory=lambda: secrets.token_hex(8))
    id: str = field(default_factory=lambda: str(ULID()))
    hmac: str = ""


def canonical(m: Message) -> bytes:
    body = {"id": m.id, "run_id": m.run_id, "from": m.from_agent, "to": m.to_agent, "schema": m.schema, "payload": m.payload,
            "ts": m.ts.isoformat(), "nonce": m.nonce}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()


def sign(m: Message, identity: AgentIdentity) -> str:
    return hmac.new(identity.signing_key(), canonical(m), hashlib.sha256).hexdigest()


class Bus:
    def __init__(self, session: Session, identities: dict[str, AgentIdentity]) -> None:
        self.session = session
        self.identities = identities
        self._nonces: set[tuple[str, str]] = set()

    def send(self, m: Message, sender: AgentIdentity, now: datetime | None = None) -> AgentMessage:
        now = now or datetime.now(UTC)
        if sender.name != m.from_agent:
            raise BusError(f"{sender.name} cannot send as {m.from_agent}")
        if m.to_agent not in self.identities:
            raise BusError(f"unknown recipient {m.to_agent}")
        schema = SCHEMAS.get(m.schema)
        if schema is None:
            raise BusError(f"unknown schema {m.schema}")
        try:
            jsonschema.validate(m.payload, schema)
        except jsonschema.ValidationError as exc:
            raise BusError(f"payload does not match {m.schema}: {exc.message}") from exc
        ts = m.ts if m.ts.tzinfo else m.ts.replace(tzinfo=UTC)
        if abs(now - ts) > REPLAY_WINDOW:
            raise BusError("message timestamp outside the replay window")
        key = (m.from_agent, m.nonce)
        if key in self._nonces:
            raise BusError("replayed message (nonce already seen)")
        m.hmac = sign(m, sender)
        self._nonces.add(key)
        row = AgentMessage(id=m.id, run_id=m.run_id, from_agent=m.from_agent, to_agent=m.to_agent, schema_name=m.schema, payload=m.payload,
                           hmac=m.hmac, nonce=m.nonce, ts=ts, verified=True)
        self.session.add(row)
        self.session.commit()
        return row

    def verify(self, m: Message) -> bool:
        ident = self.identities.get(m.from_agent)
        if ident is None or not m.hmac:
            return False
        return hmac.compare_digest(sign(m, ident), m.hmac)

    def verify_row(self, row: AgentMessage) -> bool:
        m = Message(run_id=row.run_id, from_agent=row.from_agent, to_agent=row.to_agent, schema=row.schema_name, payload=row.payload,
                    ts=row.ts if row.ts.tzinfo else row.ts.replace(tzinfo=UTC), nonce=row.nonce, id=row.id, hmac=row.hmac)
        return self.verify(m)
