"""Turn events, captions, KPIs and documents into `Chunk` rows with embeddings.

Runs on the Mac / edge box (`raqib-api index`). Per-event chunks for actionable kinds; hourly KPI
chunks summarise footfall and checkout volume so questions like "busiest day" have a target.
Embedding failure is not an error: chunks are stored without vectors and BM25 still finds them.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select
from ulid import ULID

from ..config import settings
from ..models import Caption, Chunk, Clip, Document, Event
from ..tz import ensure_utc
from .captions import caption_event, extract_keyframes
from .chunk import chunk_markdown, event_text
from .embed import EmbeddingUnavailable, embed_texts

log = logging.getLogger(__name__)

EVENT_KINDS_INDEXED = ("queue_over", "shelf_gap", "machine_stopped", "zone_breach", "ppe_violation")
DOC_KINDS = ("sop", "policy", "planogram", "pos_import", "manual", "scenario")


@dataclass
class IndexStats:
    site: str
    since: datetime
    events: int = 0
    kpi_hours: int = 0
    kpi_days: int = 0
    documents: int = 0
    chunks: int = 0
    captions: int = 0
    captions_skipped: dict[str, int] = field(default_factory=dict)
    embedded: int = 0
    embed_model: str = ""
    embed_error: str | None = None
    seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["since"] = self.since.isoformat()
        return d


def _new_id() -> str:
    return str(ULID())


def chunk_event(event: Event, caption: Caption | None = None, kpis: dict[str, Any] | None = None) -> Chunk:
    text = event_text({"id": event.id, "ts": event.ts, "kind": event.kind, "severity": event.severity, "rule_id": event.rule_id,
                       "camera": event.camera, "payload": event.payload}, caption.text if caption and caption.text else None, kpis)
    return Chunk(id=_new_id(), site=event.site, event_id=event.id, kind="event", ts=event.ts, text=text,
                 meta={"kind": event.kind, "severity": event.severity, "rule_id": event.rule_id, "camera": event.camera,
                       "zone": event.payload.get("zone"), "shelf_id": event.payload.get("shelf_id"), "till": event.payload.get("till"),
                       "has_clip": bool(event.clip_path), "caption_model": caption.model if caption else None,
                       "simulated": bool(event.payload.get("simulated")),
                       **{k: event.payload[k] for k in ("count", "dwell_s", "empty_ratio", "stopped_s", "sustained_s", "confidence")
                          if event.payload.get(k) is not None}})


def chunk_document(doc: Document, text: str) -> list[Chunk]:
    if doc.path.lower().endswith(".csv") or doc.kind in ("pos_import", "planogram"):
        spans = _chunk_csv(text, doc.title)
    else:
        spans = chunk_markdown(text, doc.title)
    return [Chunk(id=_new_id(), site=doc.site, doc_id=doc.id, kind="document", ts=doc.ts, text=s["text"],
                  meta={**s["meta"], "doc_kind": doc.kind, "doc_title": doc.title, "lang": doc.lang}) for s in spans]


def _chunk_csv(text: str, title: str, rows_per_chunk: int = 25) -> list[dict[str, Any]]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header, body = rows[0], rows[1:]
    out = []
    for i in range(0, len(body), rows_per_chunk):
        lines = ["; ".join(f"{h}: {v}" for h, v in zip(header, r, strict=False)) for r in body[i:i + rows_per_chunk]]
        out.append({"text": f"{title} — rows {i + 1}-{i + len(lines)}\n" + "\n".join(lines),
                    "meta": {"title": title, "heading": f"rows {i + 1}-{i + len(lines)}", "columns": header, "order": len(out)}})
    return out


def document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    return path.read_text(errors="replace")


def kpi_chunks(site: str, events: list[Event], tills: int) -> list[Chunk]:
    """One chunk per hour with footfall, checkouts and queue alerts; deterministic ids so re-indexing upserts."""
    hours: dict[datetime, Counter] = {}
    for e in events:
        h = e.ts.replace(minute=0, second=0, microsecond=0)
        hours.setdefault(h, Counter())[e.kind] += 1
    out = []
    days: dict[datetime, Counter] = {}
    for h, c in sorted(hours.items()):
        text = (f"Hourly KPI for {h.strftime('%A %Y-%m-%d %H:00')} UTC: footfall {c['footfall_tick']} customers entered, "
                f"{c['checkout_served']} checkouts served, {c['queue_over']} queue-over alerts, {c['shelf_gap']} shelf-gap alerts, "
                f"{tills} tills configured.")
        out.append(Chunk(id=f"kpi-{site}-{h.strftime('%Y%m%d%H')}", site=site, kind="kpi", ts=h, text=text,
                         meta={"period": "hour", "hour": h.isoformat(), **{k: int(v) for k, v in c.items()}}))
        d = h.replace(hour=0)
        days[d] = days.get(d, Counter()) + c
    for d, c in sorted(days.items()):
        peak = max((h for h in hours if h.date() == d.date()), key=lambda h: hours[h]["footfall_tick"], default=None)
        text = (f"Daily KPI for {d.strftime('%A %Y-%m-%d')}: footfall {c['footfall_tick']} customers entered the store, "
                f"{c['checkout_served']} checkouts served, {c['queue_over']} queue-over alerts, {c['shelf_gap']} shelf-gap alerts"
                + (f", busiest hour {peak.strftime('%H:00')} UTC with {hours[peak]['footfall_tick']} customers" if peak else "") + ".")
        out.append(Chunk(id=f"kpi-{site}-{d.strftime('%Y%m%d')}-day", site=site, kind="kpi", ts=d, text=text,
                         meta={"period": "day", "day": d.date().isoformat(), **{k: int(v) for k, v in c.items()}}))
    return out


def embed_chunks(chunks: list[Chunk], stats: IndexStats | None = None, batch: int = 64) -> int:
    """Fill `embedding` in batches. Returns the number embedded; leaves vectors None on failure."""
    done = 0
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        try:
            vecs = embed_texts([c.text for c in part])
        except EmbeddingUnavailable as exc:
            log.warning("embedding unavailable, chunks stored without vectors: %s", exc)
            if stats is not None:
                stats.embed_error = str(exc)[:200]
            break
        for c, v in zip(part, vecs, strict=True):
            c.embedding, c.model = v, settings.embed_model
        done += len(part)
    return done


def index_since(site: str, since: datetime, session: Session, *, embed: bool = True, captions: bool = True,
                clips_dir: str | None = None, caption_provider: Any = None, quota: Any = None, tills: int = 3) -> IndexStats:
    t0 = time.perf_counter()
    since = since if since.tzinfo else since.replace(tzinfo=UTC)
    stats = IndexStats(site=site, since=since, embed_model=settings.embed_model if embed else "")
    already = {c.event_id for c in session.exec(select(Chunk).where(Chunk.site == site, Chunk.kind == "event", Chunk.ts >= since)).all()}
    events = ensure_utc(session.exec(select(Event).where(Event.site == site, Event.ts >= since).order_by(Event.ts)).all())
    new_chunks: list[Chunk] = []
    for e in events:
        if e.kind not in EVENT_KINDS_INDEXED or e.id in already:
            continue
        cap = session.exec(select(Caption).where(Caption.event_id == e.id)).first()
        if cap is None and captions and e.severity >= settings.caption_min_severity:
            clip = session.get(Clip, e.id)
            path = clip.path if clip else e.clip_path
            if path and clips_dir and not Path(path).is_absolute():
                path = str(Path(clips_dir) / Path(path).name)
            frames = extract_keyframes(path)
            cap = caption_event(e, frames, provider=caption_provider, quota=quota)
            session.add(cap)
            if cap.model != "none":
                stats.captions += 1
            else:
                reason = (cap.parsed or {}).get("reason", "unknown")
                stats.captions_skipped[reason] = stats.captions_skipped.get(reason, 0) + 1
        new_chunks.append(chunk_event(e, cap))
        stats.events += 1
    kpis = kpi_chunks(site, events, tills)
    existing_kpi = set(session.exec(select(Chunk.id).where(Chunk.id.in_([k.id for k in kpis]))).all()) if kpis else set()
    for k in kpis:
        if k.id in existing_kpi:
            session.merge(k)
        else:
            new_chunks.append(k)
    stats.kpi_hours = sum(1 for k in kpis if k.meta.get('period') == 'hour')
    stats.kpi_days = sum(1 for k in kpis if k.meta.get('period') == 'day')
    if embed and new_chunks:
        stats.embedded = embed_chunks(new_chunks, stats)
    for c in new_chunks:
        session.add(c)
    session.commit()
    stats.chunks = len(new_chunks)
    stats.seconds = round(time.perf_counter() - t0, 2)
    log.info("indexed %s: %s", site, stats.as_dict())
    return stats


def ingest_document(site: str, title: str, kind: str, filename: str, data: bytes, session: Session, *, embed: bool = True,
                    lang: str = "en") -> tuple[Document, int, bool]:
    """Store the file, chunk it, embed if possible. Returns (document, chunks, created). Same bytes → same document."""
    if kind not in DOC_KINDS:
        raise ValueError(f"kind must be one of {DOC_KINDS}")
    sha = hashlib.sha256(data).hexdigest()
    existing = session.exec(select(Document).where(Document.site == site, Document.sha256 == sha)).first()
    if existing is not None:
        n = len(session.exec(select(Chunk).where(Chunk.doc_id == existing.id)).all())
        return existing, n, False
    doc_id = _new_id()
    safe = Path(filename).name or "document"
    dest = Path(settings.docs_dir) / site / f"{doc_id}-{safe}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    doc = Document(id=doc_id, site=site, title=title or safe, kind=kind, path=str(dest), sha256=sha, lang=lang,
                   meta={"filename": safe, "bytes": len(data)})
    chunks = chunk_document(doc, document_text(dest))
    if embed and chunks:
        embed_chunks(chunks)
    session.add(doc)
    for c in chunks:
        session.add(c)
    session.commit()
    session.refresh(doc)
    return doc, len(chunks), True
