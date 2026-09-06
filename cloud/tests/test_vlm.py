"""VLM second opinion: advisory only. It can raise attention; it can never lower severity or cancel an action."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from raqib_api.config import settings
from raqib_api.llm import LLMResult, ProviderChain, Quota
from raqib_api.models import Action, Event, ToolCall
from raqib_api.vlm.opinion import qualifies_for_auto, record_opinion, second_opinion

T0 = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
FRAMES = [np.zeros((16, 16, 3), dtype=np.uint8)] * 3


class VLM:
    name = "ollama"

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def complete(self, system, user, *, json_schema=None, images=None, max_tokens=800):
        self.calls += 1
        assert len(images) <= 3 and "<event kind=" in user
        return LLMResult(text=json.dumps(self.reply), parsed=None, tokens_in=900, tokens_out=60, provider="ollama", model="qwen2.5vl:7b", latency_ms=5)


def chain(reply):
    return ProviderChain("opinion", [VLM(reply)], None)


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


def _quota(eng, vlm=100):
    return Quota(lambda: Session(eng), limits={"ollama": 100, "vlm": vlm}, rpm=100)


def _sev3(session, i=0):
    e = Event(id=f"01SEV3{i:020d}", site="s1", camera="cam1", ts=T0, kind="zone_breach", severity=3, payload={"zone": "exclusion_1", "confidence": 0.9}, rule_id="R02")
    session.add(e)
    session.commit()
    return e


def test_downgrade_suggestion_is_recorded_but_severity_stays_3(db):
    with Session(db) as s:
        e = _sev3(s)
        res = second_opinion(e, FRAMES, provider=chain({"agrees": True, "confidence": 0.9, "observed": "one person near the line", "disagreement_reason": None, "suggested_severity": 1}), quota=_quota(db))
        row = record_opinion(e, res, s, trigger="auto_sev3")
        assert row.disagreement is True and row.suggested_severity == 1 and row.rule_severity == 3 and row.review_action_id is None
        assert s.get(Event, e.id).severity == 3
        assert s.exec(select(Action)).all() == []  # nothing cancelled, nothing created


def test_confident_disagreement_requests_human_review_and_changes_nothing_else(db):
    with Session(db) as s:
        e = _sev3(s)
        prior = Action(site="s1", event_id=e.id, tool="escalate", args={"event_id": e.id, "to_role": "safety_officer", "note": "n"}, status="executed", autonomous=True)
        s.add(prior)
        s.commit()
        res = second_opinion(e, FRAMES, provider=chain({"agrees": False, "confidence": 0.85, "observed": "area is empty", "disagreement_reason": "no person in the exclusion zone", "suggested_severity": None}), quota=_quota(db))
        row = record_opinion(e, res, s, trigger="auto_sev3")
        assert row.disagreement is True and row.review_action_id is not None
        review = s.get(Action, row.review_action_id)
        assert review.tool == "request_human_review" and review.status == "executed" and review.backend == "vlm"
        assert "disagrees" in review.args["question"]
        assert s.exec(select(ToolCall).where(ToolCall.action_id == review.id)).one().ok
        assert s.get(Event, e.id).severity == 3
        assert s.get(Action, prior.id).status == "executed"  # the escalation stands


def test_low_confidence_disagreement_is_metric_only(db):
    with Session(db) as s:
        e = _sev3(s)
        res = second_opinion(e, FRAMES, provider=chain({"agrees": False, "confidence": 0.4, "observed": "unclear", "disagreement_reason": "blurred", "suggested_severity": None}), quota=_quota(db))
        row = record_opinion(e, res, s)
        assert row.disagreement is False and row.review_action_id is None and s.get(Event, e.id).severity == 3


def test_budget_cap_enforced(db):
    q = _quota(db, vlm=1)
    with Session(db) as s:
        e = _sev3(s)
        vlm = VLM({"agrees": True, "confidence": 0.7, "observed": "ok", "disagreement_reason": None, "suggested_severity": 3})
        p = ProviderChain("opinion", [vlm], None)
        first = second_opinion(e, FRAMES, provider=p, quota=q)
        second = second_opinion(e, FRAMES, provider=p, quota=q)
        assert first.status == "ok" and second.status == "quota_exhausted" and vlm.calls == 1
        assert q.usage("vlm") == (1, 960)


def test_unavailable_paths_never_raise(db):
    with Session(db) as s:
        e = _sev3(s)
        assert second_opinion(e, [], provider=chain({}), quota=_quota(db)).status == "no_frames"
        assert second_opinion(e, FRAMES, provider=ProviderChain("opinion", [], None), quota=_quota(db)).status == "unavailable"

        class Bad:
            name = "ollama"

            def complete(self, *a, **k):
                return LLMResult(text="no", parsed=None, tokens_in=1, tokens_out=1, provider="ollama", model="m", latency_ms=1)

        res = second_opinion(e, FRAMES, provider=ProviderChain("opinion", [Bad()], None), quota=_quota(db))
        assert res.status == "invalid_json" and res.agrees is None
        row = record_opinion(e, res, s)
        assert row.status == "invalid_json" and row.agrees is None and row.disagreement is False


def test_qualifies_for_auto(monkeypatch):
    e3 = Event(id="a", site="s", camera="c", ts=T0, kind="zone_breach", severity=3, payload={"confidence": 0.9}, rule_id="R02")
    low = Event(id="b", site="s", camera="c", ts=T0, kind="queue_over", severity=2, payload={"confidence": 0.5}, rule_id="R10")
    fine = Event(id="c", site="s", camera="c", ts=T0, kind="queue_over", severity=2, payload={"confidence": 0.9}, rule_id="R10")
    assert qualifies_for_auto(e3) == "auto_sev3" and qualifies_for_auto(low) == "auto_low_conf" and qualifies_for_auto(fine) is None
    monkeypatch.setattr(settings, "vlm_auto", False)
    assert qualifies_for_auto(e3) is None


def test_api_on_demand_list_summary_and_auto_on_clip(client, monkeypatch):
    from tests.conftest import make_event

    monkeypatch.setattr(settings, "llm_provider_opinion", "groq")  # no key: opinion unavailable, still recorded
    ev = make_event(kind="zone_breach", severity=3, payload={"zone": "exclusion_1", "confidence": 0.9}, rule="R02")
    assert client.post("/events/batch", json={"events": [ev]}).status_code == 201
    r = client.post(f"/vlm/opinion/{ev['id']}")
    assert r.status_code == 201 and r.json()["status"] == "no_frames" and r.json()["agrees"] is None
    # a clip arrives -> the auto path runs after the response (garbage bytes: no decodable frames, so 'no_frames')
    client.put(f"/clips/{ev['id']}", files={"file": ("c.mp4", b"\x00\x00\x00\x18ftypmp42" + b"x" * 64, "video/mp4")})
    rows = client.get("/vlm/opinions", params={"site": ev["site"], "event_id": ev["id"]}).json()
    assert {x["trigger"] for x in rows} == {"on_demand", "auto_sev3"}
    assert client.get("/events/" + ev["id"]).json()["severity"] == 3
    sm = client.get("/vlm/summary", params={"site": ev["site"]}).json()
    assert sm["opinions"] == 2 and sm["available"] == 0 and sm["cost_usd"] == 0.0
    assert client.post("/vlm/opinion/nope").status_code == 404
