"""Documents for Ask: SOPs, policies, planograms, POS imports, manuals, saved scenarios."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlmodel import Session, select

from ..auth.deps import require
from ..auth.rbac import Principal
from ..db import get_session
from ..models import Chunk, Document
from ..rag.indexer import DOC_KINDS, ingest_document

router = APIRouter(tags=["documents"])
MAX_BYTES = 20 * 1024 * 1024


def _out(d: Document, chunks: int | None = None) -> dict:
    return {"id": d.id, "site": d.site, "title": d.title, "kind": d.kind, "lang": d.lang, "sha256": d.sha256,
            "ts": d.ts, "meta": d.meta, "chunks": chunks}


@router.post("/documents", status_code=201)
async def upload_document(site: str = Form(...), kind: str = Form(...), title: str = Form(""), lang: str = Form("en"),
                          file: UploadFile = File(...), p: Principal = Depends(require("manage")), session: Session = Depends(get_session)) -> dict:
    if kind not in DOC_KINDS:
        raise HTTPException(422, f"kind must be one of {DOC_KINDS}")
    name = file.filename or "document"
    if not name.lower().endswith((".md", ".txt", ".csv", ".pdf")):
        raise HTTPException(415, "upload .md, .txt, .csv or .pdf")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "document larger than 20 MB")
    doc, n, created = ingest_document(site, title, kind, name, data, session, lang=lang)
    return {**_out(doc, n), "created": created}


@router.get("/documents")
def list_documents(site: str = Query(...), kind: str | None = None, session: Session = Depends(get_session)) -> list[dict]:
    q = select(Document).where(Document.site == site)
    if kind:
        q = q.where(Document.kind == kind)
    docs = session.exec(q.order_by(Document.ts.desc())).all()
    counts = {}
    for d in docs:
        counts[d.id] = len(session.exec(select(Chunk.id).where(Chunk.doc_id == d.id)).all())
    return [_out(d, counts[d.id]) for d in docs]


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, session: Session = Depends(get_session)) -> dict:
    d = session.get(Document, doc_id)
    if d is None:
        raise HTTPException(404, "document not found")
    chunks = session.exec(select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.id)).all()
    chunks.sort(key=lambda c: c.meta.get("order", 0))
    return {**_out(d, len(chunks)), "chunks": [{"id": c.id, "text": c.text, "meta": c.meta, "embedded": c.embedding is not None} for c in chunks]}
