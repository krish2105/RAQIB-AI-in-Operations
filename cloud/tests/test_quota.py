from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from raqib_api.llm import Quota


def _quota(**kw):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return Quota(lambda: Session(eng), **kw)


def test_daily_cap_and_record():
    q = _quota(limits={"gemini": 3}, rpm=100)
    assert q.check("gemini")
    for _ in range(3):
        q.record("gemini", 100)
    assert not q.check("gemini")
    assert q.usage("gemini") == (3, 300)
    assert q.summary()["gemini"] == {"requests": 3, "tokens": 300, "limit": 3}


def test_zero_limit_disables_provider():
    q = _quota(limits={"claude": 0}, rpm=100)
    assert not q.check("claude")


def test_minute_bucket():
    q = _quota(limits={"ollama": 100}, rpm=2)
    q.record("ollama", 1)
    q.record("ollama", 1)
    assert not q.check("ollama")


def test_exhaust_marks_day_used_up():
    q = _quota(limits={"groq": 10}, rpm=100)
    q.record("groq", 5)
    q.exhaust("groq")
    assert q.usage("groq")[0] == 10 and not q.check("groq")
