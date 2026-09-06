from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from raqib_api.rag.chunk import chunk_markdown, event_text

ROOT = Path(__file__).resolve().parents[2]


def test_sop_yields_at_least_six_chunks_with_headings():
    text = (ROOT / "docs/sop/retail_checkout_sop.md").read_text()
    chunks = chunk_markdown(text, "Retail checkout SOP")
    assert len(chunks) >= 6
    assert all(c["meta"]["heading"] for c in chunks)
    third = [c for c in chunks if "Opening a third till" in c["meta"]["heading"]]
    assert third and "0.85" in third[0]["text"]
    assert third[0]["meta"]["path"][-1].startswith("1. Opening a third till")


def test_long_section_splits_by_words():
    text = "# Big\n" + " ".join(f"w{i}" for i in range(800))
    chunks = chunk_markdown(text, "T", max_words=350)
    assert len(chunks) == 3 and all(c["meta"]["heading"] == "Big" for c in chunks)


def test_event_text_contains_rule_id_and_caption():
    e = {"id": "x", "ts": datetime(2026, 9, 4, 19, 15, tzinfo=UTC), "kind": "queue_over", "severity": 2, "rule_id": "R10",
         "camera": "cam1", "payload": {"zone": "queue_till_1", "till": 1, "count": 9, "sustained_s": 120, "confidence": 0.82, "simulated": True}}
    t = event_text(e, caption="Long queue at till 1, 8 people visible", kpis={"rho": 0.91})
    assert "R10" in t and "Friday 2026-09-04 at 19:15" in t and "9 people waiting" in t
    assert "Scene: Long queue at till 1" in t and "rho 0.91" in t and "Simulated history" in t
