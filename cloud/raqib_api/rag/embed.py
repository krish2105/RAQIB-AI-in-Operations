"""embed_texts(): the one embedding entry point. The model is a setting so the spike's choice is a
one-line change; `Chunk.model` records which embedder produced each vector so ANN never mixes models.

EMBED_MODEL forms:
  ollama:<tag>       local Ollama (bge-m3:567m, nomic-embed-text) — dev Mac / edge box
  fastembed:<name>   ONNX in-process (sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) — fits Render free
  gemini:<model>     Gemini free API (gemini-embedding-001)
  fake:<dim>         deterministic hash embedding for tests
"""

from __future__ import annotations

import hashlib
import logging
import math
from functools import lru_cache
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)


class EmbeddingUnavailable(RuntimeError):
    """No embedder reachable; callers degrade to SQL + BM25 retrieval."""


def embed_texts(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Fixed-dimension unit vectors, deterministic for identical input. Raises EmbeddingUnavailable."""
    model = model or settings.embed_model
    if not texts:
        return []
    kind, _, name = model.partition(":")
    fn = {"ollama": _ollama, "fastembed": _fastembed, "gemini": _gemini, "fake": _fake}.get(kind)
    if fn is None:
        raise EmbeddingUnavailable(f"unknown EMBED_MODEL kind {kind!r} in {model!r}")
    vecs = fn(name, texts)
    return [_unit(v) for v in vecs]


def embedding_dim(model: str | None = None) -> int:
    model = model or settings.embed_model
    kind, _, name = model.partition(":")
    if kind == "fake":
        return int(name)
    return len(embed_texts(["dimension probe"], model)[0])


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [float(x) / n for x in v]


def _fake(dim: str, texts: list[str]) -> list[list[float]]:
    """Hashed bag-of-words: deterministic, token-overlap-aware, so tests exercise the vector leg realistically."""
    import re

    d = int(dim)
    out = []
    for t in texts:
        vec = [0.0] * d
        for tok in re.findall(r"\w+", t.lower()):
            h = hashlib.sha256(tok.encode()).digest()
            idx = int.from_bytes(h[:4], "little") % d
            vec[idx] += 1.0 if h[4] % 2 else -1.0
        if not any(vec):
            vec[0] = 1.0
        out.append(vec)
    return out


def _ollama(tag: str, texts: list[str]) -> list[list[float]]:
    try:
        import ollama

        client = ollama.Client(host=settings.ollama_host, timeout=settings.llm_timeout_s)
        resp = client.embed(model=tag, input=texts)
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingUnavailable(f"ollama embed {tag}: {exc.__class__.__name__}: {exc}") from exc
    embs: Any = resp.get("embeddings") if isinstance(resp, dict) else getattr(resp, "embeddings", None)
    if not embs:
        raise EmbeddingUnavailable(f"ollama embed {tag}: empty response")
    return [list(map(float, e)) for e in embs]


@lru_cache(maxsize=2)
def _fastembed_model(name: str) -> Any:
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=name)


def _fastembed(name: str, texts: list[str]) -> list[list[float]]:
    try:
        m = _fastembed_model(name)
        return [list(map(float, v)) for v in m.embed(texts, batch_size=32)]
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingUnavailable(f"fastembed {name}: {exc.__class__.__name__}: {exc}") from exc


def _gemini(model: str, texts: list[str]) -> list[list[float]]:
    if not settings.gemini_api_key:
        raise EmbeddingUnavailable("gemini embed: GEMINI_API_KEY is not set")
    try:
        from google import genai

        client = genai.Client(api_key=settings.gemini_api_key)
        out: list[list[float]] = []
        for i in range(0, len(texts), 100):
            resp = client.models.embed_content(model=model, contents=texts[i:i + 100], config={"output_dimensionality": settings.embed_dim})
            out.extend([list(map(float, e.values)) for e in resp.embeddings])
        return out
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingUnavailable(f"gemini embed {model}: {exc.__class__.__name__}: {exc}") from exc
