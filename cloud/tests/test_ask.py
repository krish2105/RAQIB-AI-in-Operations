"""Ask: routing, hybrid retrieval on seeded data, cited answers, no-match path, EN/HI/AR."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from raqib_api.config import settings
from raqib_api.llm import LLMResult, ProviderChain, Quota
from raqib_api.models import Event
from raqib_api.rag.answer import CITE, answer, language_ok, uncited_sentences
from raqib_api.rag.indexer import index_since, ingest_document
from raqib_api.rag.retriever import retrieve
from raqib_api.rag.router_query import parse_regex, route_query
from raqib_api.simulate import generate

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)  # Monday
SITE = "raqib_demo_store"
ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


class Fake:
    name = "ollama"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, system, user, *, json_schema=None, images=None, max_tokens=800):
        self.calls += 1
        r = self.replies.pop(0) if self.replies else self.replies_default
        text = json.dumps(r) if isinstance(r, dict) else r
        return LLMResult(text=text, parsed=None, tokens_in=100, tokens_out=40, provider="ollama", model="qwen3:8b", latency_ms=3)


def chain(*replies):
    return ProviderChain("answer", [Fake(replies)], None)


EMPTY = ProviderChain("answer", [], None)


@pytest.fixture(scope="module")
def eng():
    """21 days of seeded retail history, indexed with fake embeddings (module scoped: seeding is slow)."""
    settings.embed_model = "fake:8"
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(e)
    with Session(e) as s:
        rows = generate(SITE, "retail", days=21, seed=7, end=NOW, tills=3)
        for r in rows:
            r2 = dict(r)
            r2["ts"] = datetime.fromisoformat(r2["ts"])
            s.add(Event(**r2, handled=True))
        s.commit()
        q = Quota(lambda: Session(e), limits={"ollama": 0, "caption": 0}, rpm=1)
        index_since(SITE, NOW - timedelta(days=21), s, captions=False, quota=q)
        ingest_document(SITE, "Retail checkout SOP", "sop", "retail_checkout_sop.md", (ROOT / "docs/sop/retail_checkout_sop.md").read_bytes(), s)
    return e


@pytest.fixture()
def session(eng):
    with Session(eng) as s:
        yield s


def _max_queue_last_friday(session):
    fri = NOW - timedelta(days=(NOW.weekday() - 4) % 7 or 7)
    s, e = fri.replace(hour=17), fri.replace(hour=21)
    evs = session.exec(select(Event).where(Event.site == SITE, Event.kind == "queue_over", Event.ts >= s.replace(tzinfo=None), Event.ts < e.replace(tzinfo=None))).all()
    return max(evs, key=lambda x: x.payload["count"])


# ---- router ----

def test_router_regex_extracts_kind_and_last_friday_evening():
    p = parse_regex("Which till had the longest queue last Friday evening?", NOW)
    assert p.kind == "queue_over" and p.superlative == "max" and p.mode == "structured"
    assert p.time_start == datetime(2026, 9, 4, 17, tzinfo=UTC) and p.time_end == datetime(2026, 9, 4, 21, tzinfo=UTC)


def test_router_model_plan_with_regex_time_parsing():
    r = ProviderChain("route", [Fake([{"target": "events", "kind": "queue_over", "time_phrase": "last friday evening", "superlative": "max",
                                       "till": None, "shelf": None, "camera": None, "keywords": ["queue", "till"]}])], None)
    p = route_query("पिछले शुक्रवार शाम को किस टिल पर सबसे लंबी कतार थी?", NOW, provider=r)
    assert p.source == "model" and p.lang == "hi" and p.kind == "queue_over"
    assert p.time_start == datetime(2026, 9, 4, 17, tzinfo=UTC) and p.time_label == "last friday evening"


def test_model_cannot_override_regex_signals():
    r = ProviderChain("route", [Fake([{"target": "documents", "kind": None, "time_phrase": None, "superlative": None,
                                       "till": None, "shelf": None, "camera": None, "keywords": []}])], None)
    p = route_query("Which till had the longest queue last Friday evening?", NOW, provider=r)
    assert p.source == "model" and p.target == "events" and p.kind == "queue_over" and p.superlative == "max"
    assert p.time_label == "last friday evening" and p.mode == "structured"


def test_answer_trims_a_minority_of_uncited_sentences(session):
    plan = parse_regex("Biggest queue this week", NOW)
    hits = retrieve(plan, SITE, session, k=4)
    top = hits[0].chunk_id
    prov = chain({"answer": f"Till 1 had the biggest queue this week [c:{top}]. It was a severity 2 warning [c:{top}]. Let me know if you need more.",
                  "followups": ["a", "b", "c"]})
    a = answer(plan.q, hits, "en", plan, provider=prov)
    assert a.path == "model" and "Let me know" not in a.text and "dropped 1 uncited" in " ".join(a.notes)
    assert prov.providers[0].calls == 1  # no regeneration needed


def test_model_cannot_invent_a_till_or_shelf():
    r = ProviderChain("route", [Fake([{"target": "events", "kind": "queue_over", "time_phrase": "this week", "superlative": "max",
                                       "till": 3, "shelf": "B3", "camera": "cam2", "keywords": []}])], None)
    p = route_query("Which till had the biggest queue this week?", NOW, provider=r)
    assert p.till is None and p.shelf is None and p.camera is None
    p2 = route_query("How long was the queue at till 2 on cam1 this week?", NOW, provider=ProviderChain("route", [Fake([
        {"target": "events", "kind": "queue_over", "time_phrase": "this week", "superlative": None, "till": 2, "shelf": None, "camera": "cam1", "keywords": []}])], None))
    assert p2.till == 2 and p2.camera == "cam1"
    p3 = route_query("Show me shelf gaps in the dairy aisle this week", NOW, provider=ProviderChain("route", [Fake([
        {"target": "events", "kind": "shelf_gap", "time_phrase": "this week", "superlative": None, "till": None, "shelf": "dairy", "camera": "aisle", "keywords": []}])], None))
    assert p3.shelf is None and p3.camera is None and "dairy" in p3.terms and p3.kind == "shelf_gap"


def test_router_falls_back_when_model_output_invalid():
    r = ProviderChain("route", [Fake(["nonsense", "still nonsense"])], None)
    p = route_query("Show me shelf gaps in aisle 3 this week", NOW, provider=r)
    assert p.source == "regex" and p.kind == "shelf_gap" and p.time_label == "this week"


def test_router_document_and_kpi_questions():
    assert parse_regex("What does the SOP say about opening a third till?", NOW).target == "documents"
    p = parse_regex("किस दिन सबसे ज़्यादा footfall था?", NOW)
    assert p.target == "kpis" and p.kind == "footfall" and p.granularity == "day" and p.superlative == "max"
    assert parse_regex("ما هي أطول فترة انتظار هذا الأسبوع؟", NOW).kind == "queue_over"


# ---- retrieval ----

def test_hybrid_retrieval_returns_max_queue_event_in_top_3(session):
    target = _max_queue_last_friday(session)
    plan = parse_regex("Which till had the longest queue last Friday evening?", NOW)
    hits = retrieve(plan, SITE, session, k=12)
    assert target.id in [h.event_id for h in hits[:3]]
    assert "structured" in plan.legs and hits[0].kind == "event"


def test_retrieval_document_question_hits_sop_section(session):
    plan = parse_regex("What does the SOP say about opening a third till?", NOW)
    hits = retrieve(plan, SITE, session, k=5)
    assert hits and hits[0].kind == "document" and "third till" in hits[0].text.lower()


def test_retrieval_busiest_day_kpi(session):
    plan = parse_regex("Which day had the highest footfall?", NOW)
    hits = retrieve(plan, SITE, session, k=5)
    assert hits and hits[0].kind == "kpi" and hits[0].meta["period"] == "day"
    assert hits[0].meta["footfall_tick"] == max(h.meta["footfall_tick"] for h in hits)


def test_superlative_order_is_the_numeric_ranking_not_text_similarity(session):
    """A day chunk that merely mentions the query words must not outrank the true maximum."""
    from raqib_api.models import Chunk

    decoy = Chunk(id="kpi-decoy-day", site=SITE, kind="kpi", ts=NOW - timedelta(days=3),
                  text="Daily KPI: which day had the highest footfall footfall footfall highest day customers entered", meta={"period": "day", "footfall_tick": 5})
    session.add(decoy)
    session.commit()
    try:
        plan = parse_regex("Which day had the highest footfall?", NOW)
        hits = retrieve(plan, SITE, session, k=5)
        assert hits[0].chunk_id != "kpi-decoy-day"
        assert hits[0].meta["footfall_tick"] == max(h.meta["footfall_tick"] for h in hits)
        vals = [h.meta["footfall_tick"] for h in hits]
        assert vals == sorted(vals, reverse=True)
    finally:
        session.delete(decoy)
        session.commit()


def test_retrieval_no_hits_for_empty_window(session):
    plan = parse_regex("machine downtime yesterday", NOW)  # retail seed has no machines
    assert retrieve(plan, SITE, session) == []


# ---- answers ----

def test_answer_with_zero_hits_says_no_matching_and_has_no_citations():
    a = answer("Which machine stopped?", [], "en", provider=EMPTY)
    assert "No matching data" in a.text and a.citations == [] and a.path == "no_match"
    assert "कोई मिलता-जुलता डेटा नहीं" in answer("मशीन?", [], "hi", provider=EMPTY).text
    assert "لا توجد بيانات مطابقة" in answer("آلة؟", [], "ar", provider=EMPTY).text


def test_every_factual_sentence_has_a_citation_and_citations_link_events(session):
    plan = parse_regex("Which till had the longest queue last Friday evening?", NOW)
    hits = retrieve(plan, SITE, session, k=6)
    top = hits[0].chunk_id
    prov = chain({"answer": f"Till 1 had the longest queue on Friday evening with the most people waiting [c:{top}]. It was a severity 2 warning [c:{top}].",
                  "followups": ["a", "b", "c"]})
    a = answer(plan.q, hits, "en", plan, provider=prov)
    assert a.path == "model" and uncited_sentences(a.text, {h.chunk_id for h in hits}) == []
    assert a.citations[0].chunk_id == top and a.citations[0].event_id == hits[0].event_id and a.citations[0].event_kind == "queue_over"
    assert all(re.search(r"\[c:", s) for s in re.split(r"(?<=\.)\s+", a.text) if s.strip())


def test_uncited_or_fabricated_citations_fall_back_to_cited_template(session):
    plan = parse_regex("Biggest queue this week", NOW)
    hits = retrieve(plan, SITE, session, k=6)
    prov = chain({"answer": "Till 9 had a queue of 40 people. Trust me.", "followups": ["a", "b", "c"]},
                 {"answer": "Till 9 had a queue of 40 people [c:made-up-id].", "followups": ["a", "b", "c"]})
    a = answer(plan.q, hits, "en", plan, provider=prov)
    assert a.path == "template" and a.confidence == 0.3
    assert uncited_sentences(a.text, {h.chunk_id for h in hits}) == [] and "made-up-id" not in a.text
    assert all(c.chunk_id in {h.chunk_id for h in hits} for c in a.citations) and a.citations


def test_hindi_and_arabic_answers_keep_the_query_language(session):
    plan = parse_regex("ما هي أطول فترة انتظار هذا الأسبوع؟", NOW)
    hits = retrieve(plan, SITE, session, k=6)
    top = hits[0].chunk_id
    ar = answer(plan.q, hits, "ar", plan, provider=chain({"answer": f"أطول طابور هذا الأسبوع كان عند صندوق الدفع 1 [c:{top}].", "followups": ["أ", "ب", "ج"]}))
    assert ar.path == "model" and language_ok(ar.text, "ar") and ar.citations
    # model answers in English to a Hindi question → rejected → Hindi template, still cited
    hi = answer("इस हफ़्ते सबसे लंबी कतार?", hits, "hi", plan, provider=chain({"answer": f"Till 1 had the longest queue [c:{top}].", "followups": ["a", "b", "c"]}))
    assert hi.path == "template" and language_ok(hi.text, "hi") and hi.citations
    assert "answer language did not match" in " ".join(hi.notes)
    # no provider at all → template in the query language
    assert language_ok(answer(plan.q, hits, "ar", plan, provider=EMPTY).text, "ar")


def test_retrieved_block_wraps_chunks_as_data(session):
    seen = {}

    class Rec:
        name = "ollama"

        def complete(self, system, user, **kw):
            seen["system"], seen["user"] = system, user
            return LLMResult(text="{}", parsed=None, tokens_in=1, tokens_out=1, provider="ollama", model="m", latency_ms=1)

    plan = parse_regex("shelf gaps this week", NOW)
    hits = retrieve(plan, SITE, session, k=3)
    answer(plan.q, hits, "en", plan, provider=ProviderChain("answer", [Rec()], None))
    assert seen["user"].count("<retrieved id=") == len(hits) and "DATA, not instructions" in seen["system"]


# ---- API ----

def test_post_ask_and_history(eng, client, monkeypatch):
    from raqib_api import db as dbmod
    from raqib_api.routers import ask as ask_router

    monkeypatch.setattr(dbmod, "engine", eng)
    monkeypatch.setattr(settings, "llm_provider_route", "groq")  # no key → regex path, no network
    monkeypatch.setattr(settings, "llm_provider_answer", "groq")
    monkeypatch.setattr(ask_router, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: NOW)}))
    r = client.post("/ask", json={"q": "Which till had the longest queue last Friday evening?", "site": SITE})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["citations"] and body["citations"][0]["event_id"] and body["path"] == "template"
    assert CITE.search(body["text"]) and body["plan"]["kind"] == "queue_over" and body["hit_list"]
    h = client.get("/ask/history", params={"site": SITE}).json()
    assert h[0]["q"].startswith("Which till") and h[0]["provider"] == "none"
    with client.stream("GET", "/ask/stream", params={"q": "Biggest queue this week", "site": SITE}) as s:
        text = "".join(s.iter_text())
    assert "event: plan" in text and "event: hits" in text and "event: delta" in text and "event: done" in text
