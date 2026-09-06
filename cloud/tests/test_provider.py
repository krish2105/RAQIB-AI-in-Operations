"""LLMProvider chain: free fallback order, quota degradation, strict-JSON retry."""

from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from raqib_api.llm import (
    LLMResult,
    ProviderChain,
    ProviderUnavailable,
    Quota,
    QuotaExhausted,
    get_provider,
    try_complete,
)
from raqib_api.llm.ollama import OllamaProvider
from raqib_api.llm.provider import parse_json

SCHEMA = {"type": "object", "properties": {"kind": {"type": "string"}, "n": {"type": "integer"}},
          "required": ["kind", "n"], "additionalProperties": False}


class Fake:
    def __init__(self, name, replies=None, error=None):
        self.name, self.replies, self.error, self.calls = name, list(replies or []), error, 0

    def complete(self, system, user, *, json_schema=None, images=None, max_tokens=800):
        self.calls += 1
        if self.error:
            raise self.error
        text = self.replies.pop(0) if self.replies else "ok"
        return LLMResult(text=text, parsed=None, tokens_in=10, tokens_out=5, provider=self.name, model="m", latency_ms=1.0)


@pytest.fixture()
def quota():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return Quota(lambda: Session(eng), limits={"ollama": 5, "gemini": 2, "groq": 2, "claude": 0}, rpm=100)


def test_chain_falls_from_ollama_to_gemini_to_groq(quota):
    ollama = Fake("ollama", error=ProviderUnavailable("connection refused"))
    gemini = Fake("gemini", error=QuotaExhausted("429"))
    groq = Fake("groq", replies=["from groq"])
    res = ProviderChain("answer", [ollama, gemini, groq], quota).complete("s", "u")
    assert res.provider == "groq" and res.text == "from groq"
    assert (ollama.calls, gemini.calls, groq.calls) == (1, 1, 1)
    assert quota.usage("groq") == (1, 15) and quota.usage("ollama") == (0, 0)


def test_quota_exhaustion_degrades_without_exception(quota):
    good = Fake("gemini", replies=["a", "b", "c"])
    chain = ProviderChain("route", [good], quota)
    assert chain.complete("s", "u").text == "a"
    assert chain.complete("s", "u").text == "b"
    with pytest.raises(ProviderUnavailable, match="quota exhausted"):
        chain.complete("s", "u")
    assert try_complete(chain, "s", "u") is None  # never escapes
    assert good.calls == 2  # the third request was not even attempted


def test_json_schema_invalid_twice_returns_parsed_none(quota):
    p = Fake("ollama", replies=['{"kind": "queue_over"}', "not json at all"])
    res = ProviderChain("route", [p], quota).complete("s", "u", json_schema=SCHEMA)
    assert res.parsed is None and res.attempts == 2 and res.schema_error
    assert p.calls == 2  # exactly one retry, then the deterministic path


def test_json_schema_retry_succeeds(quota):
    p = Fake("ollama", replies=['{"kind": 3}', '```json\n{"kind": "queue_over", "n": 4}\n```'])
    res = ProviderChain("route", [p], quota).complete("s", "u", json_schema=SCHEMA)
    assert res.parsed == {"kind": "queue_over", "n": 4} and res.attempts == 2
    assert quota.usage("ollama")[0] == 2  # both attempts count against the daily cap


def test_disabled_provider_is_skipped(quota):
    claude = Fake("claude", replies=["paid"])
    ollama = Fake("ollama", replies=["free"])
    res = ProviderChain("answer", [claude, ollama], quota).complete("s", "u")
    assert res.provider == "ollama" and claude.calls == 0


def test_ollama_connection_error_maps_to_unavailable():
    class Dead:
        def chat(self, **kw):
            raise ConnectionError("refused")

    with pytest.raises(ProviderUnavailable, match="ConnectionError"):
        OllamaProvider(model="qwen3:8b", client=Dead()).complete("s", "u")


def test_ollama_sets_json_format_and_no_think():
    seen = {}

    class Rec:
        def chat(self, **kw):
            seen.update(kw)
            return {"message": {"content": '{"kind":"x","n":1}'}, "prompt_eval_count": 7, "eval_count": 3}

    res = OllamaProvider(model="qwen3:8b", client=Rec()).complete("sys", "usr", json_schema=SCHEMA, images=[b"jpg"])
    assert seen["format"] == SCHEMA and seen["think"] is False and seen["messages"][1]["images"] == [b"jpg"]
    assert res.parsed == {"kind": "x", "n": 1} and (res.tokens_in, res.tokens_out) == (7, 3)


def test_get_provider_default_order_and_overrides(monkeypatch):
    from raqib_api.config import settings

    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_provider_order", "ollama,gemini,groq")
    chain = get_provider("answer")
    assert [p.name for p in chain.providers] == ["ollama", "gemini", "groq"]
    monkeypatch.setattr(settings, "llm_provider_route", "groq,ollama")
    assert [p.name for p in get_provider("route").providers] == ["groq", "ollama"]
    monkeypatch.setattr(settings, "llm_provider", "claude")
    assert [p.name for p in get_provider("judge").providers] == ["claude"]
    with pytest.raises(ValueError):
        get_provider("nope")  # type: ignore[arg-type]


def test_parse_json_tolerates_fences_and_prose():
    assert parse_json('Sure! ```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json("[1,2]") is None and parse_json("") is None
