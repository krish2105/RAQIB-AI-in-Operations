"""Ask: natural-language questions over events, KPIs, captions and documents, with citations."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from ulid import ULID

from ..db import get_session
from ..models import AskLog
from ..rag.answer import answer
from ..rag.retriever import retrieve
from ..rag.router_query import route_query

router = APIRouter(tags=["ask"])


class AskIn(BaseModel):
    q: str = Field(min_length=2, max_length=500)
    site: str
    lang: str | None = Field(default=None, pattern="^(en|hi|ar)$")


def run_ask(body: AskIn, session: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    plan = route_query(body.q, now)
    if body.lang:
        plan.lang = body.lang
    hits = retrieve(plan, body.site, session, k=6)
    ans = answer(body.q, hits, plan.lang, plan, now=now)
    out = ans.as_dict()
    log = AskLog(id=str(ULID()), site=body.site, q=body.q, lang=ans.lang, plan=out["plan"], answer=ans.text, citations=out["citations"],
                 confidence=ans.confidence, hits=ans.hits, provider=ans.provider, model=ans.model, tokens_in=ans.tokens_in,
                 tokens_out=ans.tokens_out, cost_usd=ans.cost_usd, latency_ms=ans.latency_ms)
    session.add(log)
    session.commit()
    out["id"] = log.id
    out["hit_list"] = [h.as_dict() | {"text": h.text[:240]} for h in hits[:5]]
    return out


@router.post("/ask")
def ask(body: AskIn, session: Session = Depends(get_session)) -> dict:
    return run_ask(body, session)


@router.get("/ask/stream")
def ask_stream(q: str = Query(min_length=2, max_length=500), site: str = Query(...), lang: str | None = Query(None, pattern="^(en|hi|ar)$"),
               session: Session = Depends(get_session)) -> StreamingResponse:
    """Server-sent stages: plan → hits → answer text in word groups → done. Lets the UI render progressively."""

    def gen():
        now = datetime.now(UTC)
        plan = route_query(q, now)
        if lang:
            plan.lang = lang
        yield f"event: plan\ndata: {json.dumps(plan.as_dict(), default=str)}\n\n"
        hits = retrieve(plan, site, session, k=6)
        yield f"event: hits\ndata: {json.dumps([h.as_dict() | {'text': h.text[:240]} for h in hits[:5]], default=str)}\n\n"
        ans = answer(q, hits, plan.lang, plan, now=now)
        words = ans.text.split(" ")
        for i in range(0, len(words), 6):
            yield f"event: delta\ndata: {json.dumps(' '.join(words[i:i + 6]) + (' ' if i + 6 < len(words) else ''))}\n\n"
        out = ans.as_dict()
        log = AskLog(id=str(ULID()), site=site, q=q, lang=ans.lang, plan=out["plan"], answer=ans.text, citations=out["citations"],
                     confidence=ans.confidence, hits=ans.hits, provider=ans.provider, model=ans.model, tokens_in=ans.tokens_in,
                     tokens_out=ans.tokens_out, cost_usd=ans.cost_usd, latency_ms=ans.latency_ms)
        session.add(log)
        session.commit()
        out["id"] = log.id
        yield f"event: done\ndata: {json.dumps(out, default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/ask/history")
def history(site: str = Query(...), limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(select(AskLog).where(AskLog.site == site).order_by(AskLog.ts.desc()).limit(limit)).all()
    return [{"id": r.id, "q": r.q, "lang": r.lang, "answer": r.answer, "citations": r.citations, "confidence": r.confidence, "hits": r.hits,
             "provider": r.provider, "model": r.model, "tokens": r.tokens_in + r.tokens_out, "cost_usd": r.cost_usd, "latency_ms": r.latency_ms,
             "ts": r.ts, "plan": r.plan} for r in rows]
