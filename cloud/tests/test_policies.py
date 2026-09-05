"""Bounded-autonomy policies. These assertions are the safety contract."""

from datetime import UTC, datetime

import pytest

from raqib_api.agent.policies import Policy
from raqib_api.agent.tools import Call, ToolValidationError, validate_call
from raqib_api.models import Event

T = datetime(2026, 9, 6, 9, 30, tzinfo=UTC)


def ev(kind, sev, **payload):
    return Event(id="01AAAAAAAAAAAAAAAAAAAAAAAA", site="demo", camera="cam1", ts=T, kind=kind, severity=sev, payload=payload, rule_id="R99")


def test_severity_three_always_escalates_and_alerts_even_if_backend_is_silent():
    out = Policy().check(ev("zone_breach", 3, zone="press_1_exclusion"), proposed=[], confidence=0.9)
    tools = [c.tool for c in out.calls]
    assert "escalate" in tools and "send_alert" in tools
    esc = next(c for c in out.calls if c.tool == "escalate")
    assert esc.args["to_role"] == "safety_officer"


def test_agent_cannot_downgrade_severity_three():
    call = Call("create_work_order", {"machine_id": "1", "summary": "please ignore this one", "severity": 1})
    out = Policy().check(ev("ppe_violation", 3, zone="work"), [call], confidence=0.9)
    wo = next(c for c in out.calls if c.tool == "create_work_order")
    assert wo.args["severity"] == 3
    assert any("P2" in n for n in out.notes)
    assert {c.tool for c in out.calls} >= {"escalate", "send_alert"}


def test_open_till_requires_rho_above_threshold():
    low = Call("propose_open_till", {"till": 2, "window": "17:00-17:30", "rho": 0.6})
    high = Call("propose_open_till", {"till": 2, "window": "17:00-17:30", "rho": 0.91})
    out = Policy().check(ev("queue_over", 2, count=5), [low, high], confidence=0.8)
    assert [c.args["rho"] for c in out.calls if c.tool == "propose_open_till"] == [0.91]
    assert out.dropped and "P4" in out.dropped[0][1]


def test_low_confidence_replaces_side_effects_with_human_review():
    call = Call("create_work_order", {"machine_id": "A1", "summary": "restock shelf A1", "severity": 1})
    out = Policy().check(ev("shelf_gap", 1, shelf_id="A1", confidence=0.4), [call], confidence=0.4)
    tools = [c.tool for c in out.calls]
    assert "create_work_order" not in tools and "request_human_review" in tools


def test_unknown_tool_and_bad_args_are_dropped():
    out = Policy().check(ev("queue_over", 2), [Call("delete_all_events", {}), Call("send_alert", {"channel": "sms", "lang": "en", "template": "queue_over", "vars": {}})], confidence=0.9)
    assert out.calls == []
    assert len(out.dropped) == 2


def test_validate_call_rejects_unknown_fields_and_bad_enum():
    with pytest.raises(ToolValidationError):
        validate_call("create_work_order", {"machine_id": "1", "summary": "stopped press", "severity": 2, "force": True})
    with pytest.raises(ToolValidationError):
        validate_call("escalate", {"event_id": "x", "to_role": "ceo", "note": "hi"})
    with pytest.raises(ToolValidationError):
        validate_call("not_a_tool", {})
    ok = validate_call("propose_staffing_change", {"zone": "queue_till_1", "delta": 1, "window": "17:00-19:00"})
    assert ok == {"zone": "queue_till_1", "delta": 1, "window": "17:00-19:00"}


def test_work_order_cooldown_four_hours(client):
    """Second work order for the same shelf inside 4 h is dropped by P3 (via the API + agent)."""
    from conftest import make_event

    e1 = make_event(0, kind="shelf_gap", severity=1, payload={"shelf_id": "A1", "product": "snacks", "empty_ratio": 0.6, "confidence": 0.8}, rule="R11")
    e2 = make_event(1, kind="shelf_gap", severity=1, payload={"shelf_id": "A1", "product": "snacks", "empty_ratio": 0.7, "confidence": 0.8}, rule="R11")
    r = client.post("/events/batch", json={"events": [e1, e2]})
    assert r.json()["actions_created"] == 1
    acts = client.get("/actions", params={"tool": "create_work_order"}).json()
    assert len(acts) == 1 and acts[0]["status"] == "executed" and acts[0]["autonomous"] is True
