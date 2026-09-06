"""Hybrid retrieval: SQL filters → {structured, BM25, vector} legs → reciprocal rank fusion → optional rerank.

Every leg is optional at runtime: no embedder means no vector leg, a text-only corpus still ranks by
BM25 and structure. The similarity floor keeps junk out so the answerer can say "no matching data".
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from ..config import settings
from ..models import Chunk
from .embed import EmbeddingUnavailable, embed_texts
from .router_query import QueryPlan

log = logging.getLogger(__name__)

RRF_K = 60
MAX_CANDIDATES = 4000
VECTOR_FLOOR = 0.30  # cosine similarity below which a vector hit is ignored
RANK_FIELDS = {"queue_over": "count", "shelf_gap": "empty_ratio", "checkout_served": "dwell_s", "machine_stopped": "stopped_s",
               "footfall": "footfall_tick"}
LEG_WEIGHTS = {"structured": 2.0, "bm25": 1.0, "vector": 1.0}


@dataclass
class Hit:
    chunk_id: str
    kind: str
    text: str
    ts: datetime
    meta: dict[str, Any]
    event_id: str | None = None
    doc_id: str | None = None
    score: float = 0.0
    legs: dict[str, int] = field(default_factory=dict)  # leg -> rank

    def as_dict(self) -> dict[str, Any]:
        return {"chunk_id": self.chunk_id, "kind": self.kind, "event_id": self.event_id, "doc_id": self.doc_id, "ts": self.ts.isoformat(),
                "score": round(self.score, 4), "legs": self.legs, "meta": self.meta, "text": self.text}


def _tok(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) > 1]


def candidates(plan: QueryPlan, site: str, session: Session) -> list[Chunk]:
    q = select(Chunk).where(Chunk.site == site)
    if plan.target == "documents":
        q = q.where(Chunk.kind == "document")
    elif plan.target == "kpis":
        q = q.where(Chunk.kind == "kpi")
    elif plan.target == "events":
        q = q.where(Chunk.kind == "event")
    if plan.time_start is not None and plan.target != "documents":
        q = q.where(Chunk.ts >= plan.time_start.replace(tzinfo=None))
    if plan.time_end is not None and plan.target != "documents":
        q = q.where(Chunk.ts < plan.time_end.replace(tzinfo=None))
    rows = session.exec(q.order_by(Chunk.ts.desc()).limit(MAX_CANDIDATES)).all()
    out = []
    for c in rows:
        m = c.meta or {}
        if plan.kind and c.kind == "event" and m.get("kind") != plan.kind:
            continue
        if plan.till is not None and c.kind == "event" and m.get("till") not in (None, plan.till):
            continue
        if plan.shelf and c.kind == "event" and m.get("shelf_id") not in (None, plan.shelf):
            continue
        if plan.camera and c.kind == "event" and m.get("camera") not in (None, plan.camera):
            continue
        if c.kind == "kpi" and (plan.granularity or "day") != m.get("period", "hour"):
            continue
        out.append(c)
    return out


def _structured(plan: QueryPlan, cands: list[Chunk]) -> list[str]:
    """Rank by the numeric field a superlative asks for; without a superlative, newest first."""
    fld = RANK_FIELDS.get(plan.kind or "")
    if plan.superlative and fld:
        vals = [(c, float((c.meta or {}).get(fld) or 0.0)) for c in cands]
        vals = [(c, v) for c, v in vals if v > 0]
        vals.sort(key=lambda cv: cv[1], reverse=plan.superlative == "max")
        return [c.id for c, _ in vals[:30]]
    if plan.kind or plan.time_start or plan.till or plan.shelf:
        return [c.id for c in cands[:30]]
    return []


def _bm25(plan: QueryPlan, cands: list[Chunk]) -> list[str]:
    from rank_bm25 import BM25Okapi

    terms = _tok(" ".join([plan.q, *plan.terms]))
    if not cands or not terms:
        return []
    corpus = [_tok(c.text) for c in cands]
    scores = BM25Okapi(corpus).get_scores(terms)
    ranked = sorted(zip(cands, scores, strict=True), key=lambda cs: cs[1], reverse=True)
    return [c.id for c, s in ranked[:30] if s > 0]


def _vector(plan: QueryPlan, cands: list[Chunk], session: Session) -> tuple[list[str], str | None]:
    model = settings.embed_model
    pool = [c for c in cands if c.embedding is not None and c.model == model]
    if not pool:
        return [], "no vectors for the configured embedding model"
    try:
        qv = embed_texts([plan.q])[0]
    except EmbeddingUnavailable as exc:
        return [], str(exc)[:160]
    import numpy as np

    mat = np.array([c.embedding for c in pool], dtype=np.float32)
    sims = mat @ np.array(qv, dtype=np.float32)
    order = np.argsort(-sims)[:30]
    return [pool[i].id for i in order if sims[i] >= VECTOR_FLOOR], None


def rrf(legs: dict[str, list[str]], weights: dict[str, float] | None = None) -> dict[str, tuple[float, dict[str, int]]]:
    fused: dict[str, tuple[float, dict[str, int]]] = {}
    weights = weights or LEG_WEIGHTS
    for leg, ids in legs.items():
        w = weights.get(leg, 1.0)
        for rank, cid in enumerate(ids, start=1):
            score, ranks = fused.get(cid, (0.0, {}))
            fused[cid] = (score + w / (RRF_K + rank), {**ranks, leg: rank})
    return fused


def retrieve(plan: QueryPlan, site: str, session: Session, k: int = 12) -> list[Hit]:
    cands = candidates(plan, site, session)
    legs: dict[str, list[str]] = {}
    if plan.mode != "semantic":
        legs["structured"] = _structured(plan, cands)
    legs["bm25"] = _bm25(plan, cands)
    vec, why = _vector(plan, cands, session)
    if vec:
        legs["vector"] = vec
    elif why:
        log.info("vector leg skipped: %s", why)
    plan.legs = [leg for leg, ids in legs.items() if ids]
    # a superlative ("longest", "busiest") is answered by the numeric ranking; text legs only break ties
    weights = {**LEG_WEIGHTS, "structured": 3.0} if plan.superlative else LEG_WEIGHTS
    fused = rrf(legs, weights)
    if not fused:
        return []
    by_id = {c.id: c for c in cands}
    hits = [Hit(chunk_id=cid, kind=by_id[cid].kind, text=by_id[cid].text, ts=_aware(by_id[cid].ts), meta=by_id[cid].meta or {},
                event_id=by_id[cid].event_id, doc_id=by_id[cid].doc_id, score=score, legs=ranks)
            for cid, (score, ranks) in fused.items() if cid in by_id]
    hits.sort(key=lambda h: h.score, reverse=True)
    if plan.superlative and legs.get("structured"):
        # "longest", "busiest": the numeric ranking is the answer; text legs only order what it did not rank.
        pos = {cid: i for i, cid in enumerate(legs["structured"])}
        hits.sort(key=lambda h: (pos.get(h.chunk_id, len(pos)), -h.score))
    hits = hits[: max(k, 30)]
    if settings.rerank_enabled and len(hits) > 1:
        hits = _rerank(plan.q, hits)
    return hits[:k]


def _rerank(q: str, hits: list[Hit]) -> list[Hit]:
    try:
        from sentence_transformers import CrossEncoder

        ce = CrossEncoder("BAAI/bge-reranker-v2-m3")
        scores = ce.predict([(q, h.text) for h in hits])
    except Exception as exc:  # noqa: BLE001 — rerank is optional
        log.info("rerank skipped: %s", exc)
        return hits
    for h, s in zip(hits, scores, strict=True):
        h.legs["rerank"] = float(s)
    return sorted(hits, key=lambda h: h.legs["rerank"], reverse=True)


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def similarity_floor_met(hits: list[Hit]) -> bool:
    """At least one hit came from a structured match, a positive BM25 score, or a vector above the floor."""
    return any(h.legs for h in hits) and not all(math.isclose(h.score, 0.0) for h in hits)
