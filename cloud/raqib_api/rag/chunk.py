"""Chunkers: one text per event, heading-preserving spans per document.

Kept deliberately plain: the retriever fuses BM25 and vectors, so the text must read well for both.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

KIND_TEXT = {
    "queue_over": "queue over limit", "shelf_gap": "shelf gap", "footfall_tick": "footfall",
    "checkout_served": "checkout served", "machine_stopped": "machine stopped",
    "zone_breach": "exclusion zone breach", "ppe_violation": "PPE violation (no helmet)",
}
SEVERITY_TEXT = {1: "info", 2: "warning", 3: "critical"}


def event_text(e: dict[str, Any], caption: str | None = None, kpis: dict[str, Any] | None = None) -> str:
    """Rule text + payload + caption + KPIs at that minute, in one searchable paragraph."""
    ts = e["ts"] if isinstance(e["ts"], datetime) else datetime.fromisoformat(str(e["ts"]))
    p = e.get("payload") or {}
    parts = [f"Event {KIND_TEXT.get(e['kind'], e['kind'])} (kind {e['kind']}, rule {e.get('rule_id') or '-'}, "
             f"severity {e['severity']} {SEVERITY_TEXT.get(int(e['severity']), '')}) on {ts.strftime('%A %Y-%m-%d at %H:%M')} UTC, "
             f"camera {e.get('camera', '-')}"]
    if p.get("zone"):
        parts.append(f"zone {p['zone']}")
    if p.get("till") is not None:
        parts.append(f"till {p['till']}")
    if p.get("shelf_id"):
        parts.append(f"shelf {p['shelf_id']}" + (f" ({p['product']})" if p.get("product") else ""))
    if p.get("count") is not None:
        parts.append(f"{p['count']} people waiting")
    if p.get("sustained_s") is not None:
        parts.append(f"sustained {int(p['sustained_s'])} s")
    if p.get("dwell_s") is not None:
        parts.append(f"dwell {float(p['dwell_s']):.0f} s")
    if p.get("empty_ratio") is not None:
        parts.append(f"empty ratio {float(p['empty_ratio']):.2f}")
    if p.get("machine_id"):
        parts.append(f"machine {p['machine_id']}" + (f" stopped {int(p['stopped_s'])} s" if p.get("stopped_s") else ""))
    if p.get("confidence") is not None:
        parts.append(f"detector confidence {float(p['confidence']):.2f}")
    text = ", ".join(parts) + "."
    if caption:
        text += f" Scene: {caption.strip()}"
    if kpis:
        text += " KPIs: " + ", ".join(f"{k} {v}" for k, v in kpis.items()) + "."
    if p.get("simulated"):
        text += " Simulated history."
    return text


_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def chunk_markdown(text: str, title: str, max_words: int = 350) -> list[dict[str, Any]]:
    """Split on headings; long sections split on paragraphs. Each chunk keeps its heading path in meta."""
    chunks: list[dict[str, Any]] = []
    path: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        buf.clear()
        if not body:
            return
        heading = " › ".join(path) if path else title
        words = body.split()
        for i in range(0, max(len(words), 1), max_words):
            span = " ".join(words[i:i + max_words])
            chunks.append({"text": f"{title} — {heading}\n{span}", "meta": {"title": title, "heading": heading, "path": list(path), "order": len(chunks)}})

    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            path = path[: level - 1] + [m.group(2).strip()]
            continue
        buf.append(line)
    flush()
    return chunks
