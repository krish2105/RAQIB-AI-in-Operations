"""Task 24b embedding spike: pick embed_texts()'s model with numbers, not opinions.

Corpus: ~500 event chunks from the labelled simulator (retail, 21 days) plus daily/hourly KPI
chunks and three documents. 20 queries (EN/HI/AR) with programmatic ground truth. For every
candidate: index time, query p95, recall@5 (hits in top 5 / min(relevant, 5)), process RSS delta.
Writes docs/results/embed_spike.json and the table in docs/models.md.

  cd cloud && uv run python evals/embed/spike.py [--skip ollama:nomic-embed-text]
"""

from __future__ import annotations

import json
import resource
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from raqib_api.rag.chunk import chunk_markdown, event_text  # noqa: E402
from raqib_api.rag.embed import EmbeddingUnavailable, embed_texts  # noqa: E402
from raqib_api.simulate import generate  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
END = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)
CANDIDATES = [
    ("ollama:bge-m3:567m", "bge-m3 (Ollama, 1024-d, multilingual)", "Mac / edge box"),
    ("ollama:nomic-embed-text", "nomic-embed-text (Ollama, 768-d, present already)", "Mac / edge box"),
    ("fastembed:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "multilingual-MiniLM-L12 (fastembed ONNX, 384-d)", "Mac and Render free"),
    ("gemini:gemini-embedding-001", "gemini-embedding-001 (free API, EMBED_DIM output)", "anywhere with a key"),
]


def build_corpus() -> tuple[list[dict], dict[str, set[str]]]:
    rows = generate("raqib_demo_store", "retail", days=21, seed=7, end=END, tills=3)
    by_kind = defaultdict(list)
    for r in rows:
        by_kind[r["kind"]].append(r)
    def spread(rows: list[dict], n: int) -> list[dict]:
        step = max(1, len(rows) // n)
        return rows[::step][:n]

    chosen = spread(by_kind["queue_over"], 160) + spread(by_kind["shelf_gap"], 160) + spread(by_kind["checkout_served"], 150)
    chunks = [{"id": r["id"], "kind": "event", "ekind": r["kind"], "ts": datetime.fromisoformat(r["ts"]),
               "payload": r["payload"], "text": event_text(r)} for r in chosen]
    # daily and hourly footfall KPI chunks
    daily = Counter(datetime.fromisoformat(r["ts"]).date() for r in by_kind["footfall_tick"])
    for d, n in sorted(daily.items()):
        chunks.append({"id": f"kpi-day-{d}", "kind": "kpi", "ekind": "footfall_day", "ts": datetime(d.year, d.month, d.day, tzinfo=UTC),
                       "payload": {"footfall": n}, "text": f"Daily KPI for {d.strftime('%A %Y-%m-%d')}: footfall {n} customers entered the store, 3 tills configured."})
    hourly = Counter(datetime.fromisoformat(r["ts"]).replace(minute=0, second=0, microsecond=0) for r in by_kind["footfall_tick"])
    for h, n in sorted(hourly.items())[-48:]:
        chunks.append({"id": f"kpi-hour-{h.isoformat()}", "kind": "kpi", "ekind": "footfall_hour", "ts": h, "payload": {"footfall": n},
                       "text": f"Hourly KPI {h.strftime('%A %Y-%m-%d %H:00')} UTC: footfall {n} customers in the hour."})
    for path in ("docs/sop/retail_checkout_sop.md", "docs/pilot_sop.md", "docs/privacy_notice.md"):
        title = path.split("/")[-1].replace(".md", "").replace("_", " ")
        for i, c in enumerate(chunk_markdown((ROOT / path).read_text(), title)):
            chunks.append({"id": f"doc-{title}-{i}", "kind": "document", "ekind": "document", "ts": END, "payload": c["meta"], "text": c["text"]})

    # ---- ground truth (programmatic) ----
    def ids(pred):
        return {c["id"] for c in chunks if pred(c)}

    last_friday = max(c["ts"].date() for c in chunks if c["kind"] == "event" and c["ts"].weekday() == 4)
    fri_evening = [c for c in chunks if c["ekind"] == "queue_over" and c["ts"].date() == last_friday and 17 <= c["ts"].hour < 21]
    top_fri = {max(fri_evening, key=lambda c: c["payload"]["count"])["id"]} if fri_evening else set()
    week_ago = END - timedelta(days=7)
    busiest_day = {max((c for c in chunks if c["ekind"] == "footfall_day"), key=lambda c: c["payload"]["footfall"])["id"]}
    longest_dwell = {max((c for c in chunks if c["ekind"] == "checkout_served"), key=lambda c: c["payload"]["dwell_s"])["id"]}
    biggest_queue_week = {max((c for c in chunks if c["ekind"] == "queue_over" and c["ts"] >= week_ago), key=lambda c: c["payload"]["count"])["id"]}
    doc = lambda needle: ids(lambda c: c["kind"] == "document" and needle.lower() in c["text"].lower())  # noqa: E731
    truth = {
        "Which till had the longest queue last Friday evening?": top_fri,
        "Show me shelf gaps in the dairy aisle this week": ids(lambda c: c["ekind"] == "shelf_gap" and c["payload"].get("shelf_id") == "B3" and c["ts"] >= week_ago),
        "What does the SOP say about opening a third till?": doc("Opening a third till"),
        "How long are clips and events kept?": doc("Clips are kept for 30 days") | doc("retention"),
        "Which day had the highest footfall?": busiest_day,
        "Longest checkout dwell time on record": longest_dwell,
        "Biggest queue this week": biggest_queue_week,
        "When should a till be closed?": doc("Closing a till"),
        "किस दिन सबसे ज़्यादा footfall था?": busiest_day,
        "पिछले शुक्रवार शाम को किस टिल पर सबसे लंबी कतार थी?": top_fri,
        "तीसरा टिल खोलने के बारे में SOP क्या कहता है?": doc("Opening a third till"),
        "इस हफ़्ते डेयरी शेल्फ़ में कहाँ गैप थे?": ids(lambda c: c["ekind"] == "shelf_gap" and c["payload"].get("shelf_id") == "B3" and c["ts"] >= week_ago),
        "क्लिप कितने दिन रखी जाती हैं?": doc("Clips are kept for 30 days") | doc("retention"),
        "टिल कब बंद करना चाहिए?": doc("Closing a till"),
        "ما هي أطول فترة انتظار هذا الأسبوع؟": biggest_queue_week,
        "في أي يوم كان عدد الزوار هو الأعلى؟": busiest_day,
        "ماذا يقول دليل الإجراءات عن فتح صندوق دفع ثالث؟": doc("Opening a third till"),
        "أين كانت فجوات الرفوف في قسم الألبان هذا الأسبوع؟": ids(lambda c: c["ekind"] == "shelf_gap" and c["payload"].get("shelf_id") == "B3" and c["ts"] >= week_ago),
        "كم يوماً يتم الاحتفاظ بالمقاطع؟": doc("Clips are kept for 30 days") | doc("retention"),
        "متى يجب إغلاق صندوق الدفع؟": doc("Closing a till"),
    }
    assert all(truth.values()), [q for q, v in truth.items() if not v]
    return chunks, truth


def evaluate(model: str, chunks: list[dict], truth: dict[str, set[str]]) -> dict:
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
    texts = [c["text"] for c in chunks]
    t0 = time.perf_counter()
    mat = np.array(embed_texts(texts, model=model), dtype=np.float32)
    index_s = time.perf_counter() - t0
    ids = [c["id"] for c in chunks]
    lat, hits = [], {}
    for q, rel in truth.items():
        t1 = time.perf_counter()
        qv = np.array(embed_texts([q], model=model)[0], dtype=np.float32)
        top = np.argsort(-(mat @ qv))[:5]
        lat.append((time.perf_counter() - t1) * 1000)
        got = {ids[i] for i in top}
        hits[q] = len(got & rel) / min(len(rel), 5)
    rss1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
    by_lang = {"en": [], "hi": [], "ar": []}
    for q, h in hits.items():
        by_lang["hi" if any("ऀ" <= ch <= "ॿ" for ch in q) else "ar" if any("؀" <= ch <= "ۿ" for ch in q) else "en"].append(h)
    return {"model": model, "dim": int(mat.shape[1]), "chunks": len(chunks), "index_s": round(index_s, 1),
            "query_p95_ms": round(float(np.percentile(lat, 95)), 1), "query_mean_ms": round(statistics.mean(lat), 1),
            "recall_at_5": round(statistics.mean(hits.values()), 3),
            "recall_by_lang": {k: round(statistics.mean(v), 3) for k, v in by_lang.items() if v},
            "rss_delta_mb": round(rss1 - rss0, 1), "per_query": {q: round(h, 2) for q, h in hits.items()}}


def main() -> None:
    skip = {a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--skip=")}
    chunks, truth = build_corpus()
    print(f"corpus: {len(chunks)} chunks ({Counter(c['kind'] for c in chunks)}), {len(truth)} queries")
    results = []
    for model, label, where in CANDIDATES:
        if model in skip:
            continue
        try:
            r = evaluate(model, chunks, truth)
            r.update(label=label, where=where, status="ok")
            print(f"{label:55s} dim={r['dim']:4d} index={r['index_s']:6.1f}s p95={r['query_p95_ms']:7.1f}ms recall@5={r['recall_at_5']:.2f} {r['recall_by_lang']} rss+{r['rss_delta_mb']}MB")
        except EmbeddingUnavailable as exc:
            r = {"model": model, "label": label, "where": where, "status": "unavailable", "reason": str(exc)[:160]}
            print(f"{label:55s} UNAVAILABLE: {r['reason']}")
        results.append(r)
    out = {"date": datetime.now(UTC).isoformat(), "corpus_chunks": len(chunks), "queries": len(truth), "results": results}
    (ROOT / "docs/results/embed_spike.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print("wrote docs/results/embed_spike.json")


if __name__ == "__main__":
    main()
