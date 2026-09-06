"""Indexer: event chunks, captions (≤3 frames, strict JSON, quota), KPI chunks, document upload."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from raqib_api.config import settings
from raqib_api.llm import LLMResult, ProviderChain, Quota
from raqib_api.models import Caption, Chunk, Document, Event
from raqib_api.rag.captions import caption_event
from raqib_api.rag.indexer import index_since, ingest_document

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)


class VLM:
    """Records how many images it received; replies with valid JSON."""

    name = "ollama"

    def __init__(self):
        self.images = []

    def complete(self, system, user, *, json_schema=None, images=None, max_tokens=800):
        self.images.append(len(images or []))
        body = {"scene": "queue at till 1", "people_count": 7, "actions": ["waiting"], "risk_notes": ["long queue"]}
        return LLMResult(text=json.dumps(body), parsed=None, tokens_in=50, tokens_out=20, provider="ollama", model="qwen2.5vl:7b", latency_ms=5)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(settings, "embed_model", "fake:8")
    monkeypatch.setattr(settings, "docs_dir", str(tmp_path / "docs"))
    return eng


def _events(session, n_queue=3, n_foot=40):
    from ulid import ULID

    rows = []
    for i in range(n_queue):
        ts = T0 + timedelta(minutes=10 * i)
        rows.append(Event(id=str(ULID.from_timestamp(ts.timestamp())), site="s1", camera="cam1", ts=ts, kind="queue_over", severity=2,
                          payload={"zone": "queue_till_1", "till": 1, "count": 5 + i, "sustained_s": 90, "confidence": 0.8}, rule_id="R10",
                          clip_path=None))
    for i in range(n_foot):
        ts = T0 + timedelta(minutes=i)
        rows.append(Event(id=str(ULID.from_timestamp(ts.timestamp() + 0.5)), site="s1", camera="cam1", ts=ts, kind="footfall_tick", severity=1,
                          payload={"zone": "entrance"}, rule_id="R12"))
    for r in rows:
        session.add(r)
    session.commit()
    return rows


def _quota(eng, **limits):
    return Quota(lambda: Session(eng), limits={"ollama": 100, "caption": limits.get("caption", 100)}, rpm=100)


def test_index_creates_event_and_kpi_chunks_with_embeddings(db):
    with Session(db) as s:
        _events(s)
        stats = index_since("s1", T0 - timedelta(hours=1), s, captions=False, quota=_quota(db))
        assert stats.events == 3 and stats.kpi_hours == 1 and stats.kpi_days == 1 and stats.chunks == 5 and stats.embedded == 5
        chunks = s.exec(select(Chunk).where(Chunk.site == "s1")).all()
        ev = [c for c in chunks if c.kind == "event"]
        assert len(ev) == 3 and all("R10" in c.text and len(c.embedding) == 8 and c.model == "fake:8" for c in ev)
        kpi = [c for c in chunks if c.kind == "kpi" and c.meta["period"] == "hour"][0]
        assert "footfall 40 customers" in kpi.text and "3 queue-over alerts" in kpi.text
        day = [c for c in chunks if c.kind == "kpi" and c.meta["period"] == "day"][0]
        assert "Daily KPI" in day.text and day.meta["footfall_tick"] == 40
        # re-index is idempotent
        again = index_since("s1", T0 - timedelta(hours=1), s, captions=False, quota=_quota(db))
        assert again.events == 0 and len(s.exec(select(Chunk).where(Chunk.site == "s1")).all()) == 5


def test_embedding_failure_keeps_chunks_without_vectors(db, monkeypatch):
    monkeypatch.setattr(settings, "embed_model", "ollama:bge-m3:567m")
    monkeypatch.setattr(settings, "ollama_host", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "llm_timeout_s", 1.0)
    with Session(db) as s:
        _events(s, n_queue=1, n_foot=2)
        stats = index_since("s1", T0 - timedelta(hours=1), s, captions=False, quota=_quota(db))
        assert stats.chunks == 3 and stats.embedded == 0 and stats.embed_error
        assert all(c.embedding is None for c in s.exec(select(Chunk)).all())


def test_caption_uses_at_most_three_frames_and_valid_json(db):
    vlm = VLM()
    chain = ProviderChain("caption", [vlm], None)
    frames = [np.zeros((32, 32, 3), dtype=np.uint8)] * 6
    e = Event(id="01" + "A" * 24, site="s1", camera="cam1", ts=T0, kind="queue_over", severity=2, payload={"zone": "q"}, rule_id="R10")
    cap = caption_event(e, frames, provider=chain, quota=_quota(db))
    assert vlm.images == [3] and cap.frames == 3 and cap.model == "qwen2.5vl:7b"
    assert cap.parsed["people_count"] == 7 and "queue at till 1" in cap.text and "risks: long queue" in cap.text


def test_caption_quota_exhaustion_stops_captioning(db, caplog):
    vlm = VLM()
    chain = ProviderChain("caption", [vlm], None)
    q = _quota(db, caption=1)
    frames = [np.zeros((8, 8, 3), dtype=np.uint8)]
    e1 = Event(id="01" + "B" * 24, site="s1", camera="cam1", ts=T0, kind="zone_breach", severity=3, payload={}, rule_id="R02")
    e2 = Event(id="01" + "C" * 24, site="s1", camera="cam1", ts=T0, kind="zone_breach", severity=3, payload={}, rule_id="R02")
    c1 = caption_event(e1, frames, provider=chain, quota=q)
    c2 = caption_event(e2, frames, provider=chain, quota=q)
    assert c1.model == "qwen2.5vl:7b" and c2.model == "none" and c2.parsed == {"reason": "quota_exhausted"}
    assert vlm.images == [1] and "quota_exhausted" in caplog.text


def test_caption_invalid_json_and_no_provider_never_raise(db):
    class Bad:
        name = "ollama"

        def complete(self, *a, **k):
            return LLMResult(text="I cannot see", parsed=None, tokens_in=1, tokens_out=1, provider="ollama", model="m", latency_ms=1)

    e = Event(id="01" + "D" * 24, site="s1", camera="cam1", ts=T0, kind="queue_over", severity=2, payload={}, rule_id="R10")
    frames = [np.zeros((8, 8, 3), dtype=np.uint8)]
    cap = caption_event(e, frames, provider=ProviderChain("caption", [Bad()], None), quota=_quota(db))
    assert cap.model == "m" and cap.parsed["reason"] == "invalid_json" and cap.text == ""
    none = caption_event(e, frames, provider=ProviderChain("caption", [], None), quota=_quota(db))
    assert none.model == "none" and none.parsed == {"reason": "provider_unavailable"}
    assert caption_event(e, [], provider=ProviderChain("caption", [], None), quota=_quota(db)).parsed == {"reason": "no_frames"}


def test_index_captions_sev2_only_and_records_skips(db):
    vlm = VLM()
    with Session(db) as s:
        _events(s, n_queue=2, n_foot=1)
        s.add(Event(id="01" + "E" * 24, site="s1", camera="cam1", ts=T0, kind="shelf_gap", severity=1, payload={"shelf_id": "B3"}, rule_id="R11"))
        s.commit()
        stats = index_since("s1", T0 - timedelta(hours=1), s, quota=_quota(db), caption_provider=ProviderChain("caption", [vlm], None))
        # no clips on disk → captions skipped with reason no_frames, only for severity >= 2
        assert stats.captions == 0 and stats.captions_skipped == {"no_frames": 2}
        assert len(s.exec(select(Caption)).all()) == 2 and all(c.model == "none" for c in s.exec(select(Caption)).all())


def test_ingest_document_chunks_dedupes_and_lists(db, client, monkeypatch):
    from raqib_api import db as dbmod

    monkeypatch.setattr(dbmod, "engine", db)
    data = (ROOT / "docs/sop/retail_checkout_sop.md").read_bytes()
    r = client.post("/documents", data={"site": "s1", "kind": "sop", "title": "Retail checkout SOP"},
                    files={"file": ("retail_checkout_sop.md", data, "text/markdown")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] and body["chunks"] >= 6
    r2 = client.post("/documents", data={"site": "s1", "kind": "sop"}, files={"file": ("copy.md", data, "text/markdown")})
    assert r2.status_code == 201 and r2.json()["created"] is False and r2.json()["id"] == body["id"]
    lst = client.get("/documents", params={"site": "s1"}).json()
    assert len(lst) == 1 and lst[0]["chunks"] == body["chunks"]
    one = client.get(f"/documents/{body['id']}").json()
    assert one["chunks"][0]["embedded"] and "Opening a third till" in "".join(c["text"] for c in one["chunks"])
    assert client.post("/documents", data={"site": "s1", "kind": "poem"}, files={"file": ("x.md", b"# a", "text/markdown")}).status_code == 422
    assert client.post("/documents", data={"site": "s1", "kind": "sop"}, files={"file": ("x.exe", b"a", "application/octet-stream")}).status_code == 415


def test_csv_planogram_chunks(db):
    with Session(db) as s:
        csv = "shelf,sku,facings,price\nB3,milk-1l,6,5.50\nB3,yogurt,4,3.25\nA1,chocolate,8,7.00\n"
        doc, n, created = ingest_document("s1", "Planogram Sept", "planogram", "plan.csv", csv.encode(), s)
        assert created and n == 1
        c = s.exec(select(Chunk).where(Chunk.doc_id == doc.id)).one()
        assert "shelf: B3; sku: milk-1l; facings: 6; price: 5.50" in c.text and c.meta["columns"] == ["shelf", "sku", "facings", "price"]
        assert s.get(Document, doc.id).kind == "planogram"


def test_seed_reset_removes_chunks_and_captions_before_events(client, monkeypatch):
    monkeypatch.setattr(settings, "embed_model", "fake:8")
    client.post("/admin/seed", params={"site": "raqib_demo_store", "days": 3, "run_agent_last_hours": 0})
    assert client.post("/admin/index", params={"site": "raqib_demo_store", "days": 3}).json()["chunks"] > 0
    r = client.post("/admin/seed", params={"site": "raqib_demo_store", "days": 2, "run_agent_last_hours": 0})
    assert r.status_code == 200 and r.json()["inserted"] > 0
    from raqib_api import db as dbmod

    with Session(dbmod.engine) as s:
        assert s.exec(select(Chunk).where(Chunk.kind == "event")).all() == []
        assert client.post("/admin/reset", params={"site": "raqib_demo_store"}).json()["reset"]
        assert s.exec(select(Event)).all() == []
