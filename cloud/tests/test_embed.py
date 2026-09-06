from __future__ import annotations

import os

import pytest

from raqib_api.rag.embed import EmbeddingUnavailable, embed_texts, embedding_dim


def test_fake_embedder_is_fixed_dimension_and_deterministic():
    a = embed_texts(["queue at till 1", "shelf gap B3"], model="fake:16")
    b = embed_texts(["queue at till 1", "shelf gap B3"], model="fake:16")
    assert a == b and all(len(v) == 16 for v in a)
    assert a[0] != a[1]
    assert abs(sum(x * x for x in a[0]) - 1.0) < 1e-6  # unit vectors
    assert embedding_dim("fake:16") == 16 and embed_texts([], model="fake:16") == []


def test_unknown_kind_raises_unavailable():
    with pytest.raises(EmbeddingUnavailable):
        embed_texts(["x"], model="magic:thing")


def test_ollama_unreachable_raises_unavailable(monkeypatch):
    from raqib_api.config import settings

    monkeypatch.setattr(settings, "ollama_host", "http://127.0.0.1:9")  # nothing listens
    monkeypatch.setattr(settings, "llm_timeout_s", 1.0)
    with pytest.raises(EmbeddingUnavailable):
        embed_texts(["x"], model="ollama:bge-m3:567m")


@pytest.mark.skipif(not os.environ.get("RAQIB_LIVE"), reason="needs a running Ollama with bge-m3 (RAQIB_LIVE=1)")
def test_live_bge_m3_dimension_and_determinism():
    a = embed_texts(["किस दिन सबसे ज़्यादा footfall था?"], model="ollama:bge-m3:567m")
    b = embed_texts(["किस दिन सबसे ज़्यादा footfall था?"], model="ollama:bge-m3:567m")
    assert len(a[0]) == 1024 and a == b
