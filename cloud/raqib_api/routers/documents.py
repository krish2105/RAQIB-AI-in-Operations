"""Documents for Ask: SOPs, policies, planograms, POS imports, manuals, saved scenarios."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
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


class UrlIn(BaseModel):
    site: str
    kind: str
    url: str = Field(max_length=2000)
    title: str = ""
    lang: str = "en"


ALLOWED_TYPES = ("text/markdown", "text/plain", "text/csv", "application/pdf", "application/octet-stream")


def _resolve_public(host: str) -> None:
    """SSRF guard: every resolved address must be public; loopback, private, link-local (cloud metadata) and
    reserved ranges are refused before any connection is made."""
    import ipaddress
    import socket

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise HTTPException(422, f"cannot resolve {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise HTTPException(422, f"refusing to fetch a non-public address ({ip})")


def guard_url(url: str) -> str:
    from urllib.parse import urlparse

    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise HTTPException(422, "only http(s) URLs with a host are accepted")
    if u.username or u.password:
        raise HTTPException(422, "credentials in URLs are not accepted")
    _resolve_public(u.hostname)
    return url


@router.post("/documents/url", status_code=201)
def ingest_url(body: UrlIn, p: Principal = Depends(require("manage")), session: Session = Depends(get_session)) -> dict:
    """Fetch a document by URL with an SSRF guard, then ingest it like an upload."""
    import httpx

    if body.kind not in DOC_KINDS:
        raise HTTPException(422, f"kind must be one of {DOC_KINDS}")
    url = guard_url(body.url)
    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as c:
            r = c.get(url, headers={"User-Agent": "raqib-docs/1.0"})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"fetch failed: {exc.__class__.__name__}") from exc
    if 300 <= r.status_code < 400:
        raise HTTPException(422, "redirects are not followed; give the final URL")
    if r.status_code != 200:
        raise HTTPException(502, f"fetch returned {r.status_code}")
    ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype and ctype not in ALLOWED_TYPES:
        raise HTTPException(415, f"unsupported content type {ctype}")
    data = r.content
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "document larger than 20 MB")
    name = url.rstrip("/").rsplit("/", 1)[-1] or "document.md"
    if not name.lower().endswith((".md", ".txt", ".csv", ".pdf")):
        name += ".pdf" if ctype == "application/pdf" else ".csv" if ctype == "text/csv" else ".md"
    doc, n, created = ingest_document(body.site, body.title, body.kind, name, data, session, lang=body.lang)
    return {**_out(doc, n), "created": created, "source_url": url}


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
