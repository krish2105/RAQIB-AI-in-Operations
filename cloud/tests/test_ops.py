"""Retention deletes a 31-day-old clip and logs it; pinned memory survives; every LLM call emits a span with cost; the daily cost KPI equals the sum of spans."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from raqib_api.llm import LLMResult, ProviderChain
from raqib_api.telemetry import memory_exporter


def test_retention_deletes_old_clip_and_logs_and_keeps_pinned_memory(client, tmp_path):
    from raqib_api import db as dbmod
    from raqib_api.jobs.retention import run_retention
    from raqib_api.models import Clip, Event, Memory, RetentionLog
    from tests.conftest import make_event

    now = datetime.now(UTC)
    old = make_event(0, kind="queue_over", severity=2, ts=now - timedelta(days=31, hours=1), payload={"count": 5})
    fresh = make_event(1, kind="queue_over", severity=2, ts=now - timedelta(days=2), payload={"count": 5})
    ancient = make_event(2, kind="footfall_tick", ts=now - timedelta(days=401), payload={})
    client.post("/events/batch", json={"events": [old, fresh, ancient]})
    for e in (old, fresh):
        client.put(f"/clips/{e['id']}", files={"file": ("c.mp4", b"\x00\x00\x00\x18ftypmp42" + b"x" * 32, "video/mp4")})
    with Session(dbmod.engine) as s:
        for e, age in ((old, 31), (fresh, 2)):
            c = s.get(Clip, e["id"])
            c.uploaded_at = now - timedelta(days=age, hours=1)
            s.add(c)
        s.add(Memory(site="raqib_demo_store", agent="FloorOps", key="old", value="stale", ts=now - timedelta(days=91), pinned=False, sha256="x"))
        s.add(Memory(site="raqib_demo_store", agent="FloorOps", key="keep", value="pinned by a manager", ts=now - timedelta(days=91), pinned=True, sha256="y"))
        s.add(Memory(site="raqib_demo_store", agent="FloorOps", key="new", value="recent", ts=now - timedelta(days=1), pinned=False, sha256="z"))
        s.commit()
        old_path = s.get(Clip, old["id"]).path
        dry = run_retention(s, now, dry_run=True)
        assert dry["clips"]["deleted"] == 1 and dry["events"]["deleted"] == 1 and dry["memories"]["deleted"] == 1 and dry["memories"]["kept_pinned"] == 1
        assert s.get(Clip, old["id"]) is not None  # dry run touched nothing
        out = run_retention(s, now)
        assert out["clips"]["deleted"] == 1 and out["clips"]["files_removed"] == 1 and not __import__("pathlib").Path(old_path).exists()
        assert s.get(Clip, old["id"]) is None and s.get(Clip, fresh["id"]) is not None and s.get(Event, old["id"]).clip_path is None
        assert s.get(Event, ancient["id"]) is None and s.get(Event, fresh["id"]) is not None
        keys = {m.key for m in s.exec(select(Memory)).all()}
        assert keys == {"keep", "new"}
        logs = s.exec(select(RetentionLog)).all()
        assert {(r.kind, r.deleted) for r in logs} == {("clips", 1), ("events", 1), ("memories", 1)}
    assert client.get("/jobs/retention/log").json()[0]["kind"] in ("clips", "events", "memories")
    assert client.post("/jobs/retention", params={"dry_run": "true"}).status_code == 200


class Fake:
    name = "ollama"

    def complete(self, system, user, **kw):
        return LLMResult(text="ok", parsed=None, tokens_in=120, tokens_out=30, provider="ollama", model="qwen3:8b", latency_ms=12.5, cost_usd=0.0)


class Paid:
    name = "claude"

    def complete(self, system, user, **kw):
        return LLMResult(text="ok", parsed=None, tokens_in=100, tokens_out=50, provider="claude", model="claude-sonnet-4-6", latency_ms=800, cost_usd=0.00105)


def test_every_llm_call_emits_a_span_with_cost_and_the_ledger_matches(client):
    from raqib_api import db as dbmod
    from raqib_api.jobs.cost import daily_cost
    from raqib_api.models import LlmSpan

    memory_exporter.clear()
    with Session(dbmod.engine) as s:
        s.exec(__import__("sqlmodel").delete(LlmSpan))
        s.commit()
    ProviderChain("answer", [Fake()], None, site="raqib_demo_store").complete("sys", "user question")
    ProviderChain("route", [Fake()], None, site="raqib_demo_store").complete("sys", "another")
    ProviderChain("judge", [Paid()], None, site="raqib_demo_store").complete("sys", "grade")
    spans = [sp for sp in memory_exporter.get_finished_spans() if sp.name.startswith("llm.")]
    assert len(spans) == 3
    for sp in spans:
        a = dict(sp.attributes)
        assert "raqib.cost_usd" in a and "raqib.model" in a and "raqib.tokens_in" in a and "raqib.latency_ms" in a and len(a["raqib.prompt_hash"]) == 16
        assert "user question" not in str(a.values())  # the prompt never leaves as an attribute, only its hash
    assert sum(dict(sp.attributes)["raqib.cost_usd"] for sp in spans) == 0.00105
    with Session(dbmod.engine) as s:
        rows = s.exec(select(LlmSpan)).all()
        assert len(rows) == 3 and sum(r.cost_usd for r in rows) == 0.00105 and {r.task for r in rows} == {"answer", "route", "judge"}
        kpi = daily_cost(s, "raqib_demo_store", days=1)
    assert kpi["today"]["requests"] == 3 and kpi["today"]["usd"] == 0.00105 and kpi["today"]["tokens_in"] == 340
    assert kpi["today"]["providers"]["ollama"] == {"requests": 2, "tokens": 300, "usd": 0.0} and kpi["spans_today"] == 3
    api = client.get("/cost", params={"site": "raqib_demo_store", "days": 1}).json()
    assert api["total_usd"] == 0.00105 and api["today"]["requests"] == 3


def test_failed_chain_still_emits_a_span_without_cost():
    from raqib_api.llm import ProviderUnavailable

    memory_exporter.clear()
    try:
        ProviderChain("caption", [], None).complete("s", "u")
    except ProviderUnavailable:
        pass
    sp = [x for x in memory_exporter.get_finished_spans() if x.name == "llm.caption"][-1]
    assert dict(sp.attributes)["raqib.provider"] == "none" and dict(sp.attributes)["raqib.cost_usd"] == 0.0
