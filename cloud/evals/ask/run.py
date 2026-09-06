"""Ask eval suite: 30 cases, recall@5, citation precision, faithfulness, language, hallucination tripwires.

  cd cloud && uv run python evals/ask/run.py [--gate] [--out ../docs/results/ask_eval.json] [--md]

Runs against a fresh in-memory store: seeded events (seed 7), indexed with the configured EMBED_MODEL
(CI uses fake:64), three documents. Providers come from settings; with none reachable the answer path is
the cited template and faithfulness is the deterministic citation coverage. With get_provider("judge")
reachable, a strict judge scores every claim against the retrieved records only.
Gate: recall@5 >= 0.8, faithfulness >= 0.9, zero hallucination tripwires.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from raqib_api.config import settings  # noqa: E402
from raqib_api.llm import Quota, get_provider, try_complete  # noqa: E402
from raqib_api.models import Chunk, Event  # noqa: E402
from raqib_api.rag.answer import answer, language_ok, retrieval_facts, sentences, uncited_sentences  # noqa: E402
from raqib_api.rag.indexer import index_since, ingest_document  # noqa: E402
from raqib_api.rag.retriever import retrieve  # noqa: E402
from raqib_api.rag.router_query import route_query  # noqa: E402
from raqib_api.simulate import generate  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
SITE = "raqib_demo_store"
DOCS = [("Retail checkout SOP", "sop", "docs/sop/retail_checkout_sop.md"), ("Pilot SOP", "sop", "docs/pilot_sop.md"),
        ("Privacy notice", "policy", "docs/privacy_notice.md")]
GATE = {"recall_at_5": 0.8, "faithfulness": 0.9, "hallucinations": 0}
JUDGE_SYSTEM = (
    "You are a strict grader. You get retrieval facts, retrieved records (data) and an answer. Count every factual claim in the "
    "answer and how many are fully supported by the records plus the retrieval facts. A claim with a number, time, till, shelf or "
    "rule not present in the records is unsupported. Paraphrases and unit or format changes of a record value (256 s = 256 seconds, "
    "18:51 = around 18:51 UTC) are supported. A superlative (longest, biggest, busiest) is supported when the retrieval facts say the "
    "records are ranked by that quantity and the cited record is the first. Reply with JSON only."
)
JUDGE_SCHEMA = {"type": "object", "properties": {"claims": {"type": "integer", "minimum": 0}, "supported": {"type": "integer", "minimum": 0},
                                                 "unsupported": {"type": "array", "items": {"type": "string"}, "maxItems": 10}},
                "required": ["claims", "supported", "unsupported"], "additionalProperties": False}


def build_store():
    from raqib_api import db as dbmod

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    dbmod.engine = eng  # quota counters and anything else that uses the app engine share this store
    with Session(eng) as s:
        for r in generate(SITE, "retail", days=21, seed=7, end=NOW, tills=3):
            r2 = dict(r)
            r2["ts"] = datetime.fromisoformat(r2["ts"])
            s.add(Event(**r2, handled=True))
        s.commit()
        q = Quota(lambda: Session(eng), limits={"ollama": 0, "caption": 0}, rpm=1)
        index_since(SITE, NOW - timedelta(days=21), s, captions=False, quota=q)
        for title, kind, path in DOCS:
            ingest_document(SITE, title, kind, Path(path).name, (ROOT / path).read_bytes(), s)
    return eng


def _window(name: str) -> tuple[datetime | None, datetime | None]:
    fri = NOW - timedelta(days=(NOW.weekday() - 4) % 7 or 7)
    sat = NOW - timedelta(days=(NOW.weekday() - 5) % 7 or 7)
    return {
        "last_friday_evening": (fri.replace(hour=17), fri.replace(hour=21)),
        "this_week": (NOW - timedelta(days=7), NOW),
        "last_week": (NOW - timedelta(days=14), NOW - timedelta(days=7)),
        "yesterday": ((NOW - timedelta(days=1)).replace(hour=0), NOW.replace(hour=0)),
        "last_saturday": (sat.replace(hour=0), sat.replace(hour=0) + timedelta(days=1)),
        "all": (None, None),
    }[name]


def resolve(expect: dict[str, Any], session: Session) -> set[str]:
    t = expect["type"]
    if t == "none":
        return set()
    if t == "doc":
        rows = session.exec(select(Chunk).where(Chunk.kind == "document")).all()
        return {c.id for c in rows if expect["contains"].lower() in c.text.lower()}
    if t == "kpi":
        rows = [c for c in session.exec(select(Chunk).where(Chunk.kind == "kpi")).all() if c.meta.get("period") == expect.get("period", "day")]
        if expect.get("window"):
            s, e = _window(expect["window"])
            rows = [c for c in rows if s.replace(tzinfo=None) <= c.ts < e.replace(tzinfo=None)]
            return {c.id for c in rows}
        top = max(rows, key=lambda c: c.meta.get("footfall_tick", 0))
        return {top.id}
    rows = [c for c in session.exec(select(Chunk).where(Chunk.kind == "event")).all() if c.meta.get("kind") == expect["kind"]]
    s, e = _window(expect.get("window", "all"))
    if s is not None:
        rows = [c for c in rows if s.replace(tzinfo=None) <= c.ts < e.replace(tzinfo=None)]
    if expect.get("shelf"):
        rows = [c for c in rows if c.meta.get("shelf_id") == expect["shelf"]]
    if not rows:
        return set()
    rank = expect.get("rank", "any")
    if rank == "max_count":
        return {max(rows, key=lambda c: c.meta.get("count", 0)).id}
    if rank == "max_empty":
        return {max(rows, key=lambda c: c.meta.get("empty_ratio", 0)).id}
    return {c.id for c in rows}


def judge(hits, text: str, plan=None) -> dict[str, Any] | None:
    chain = get_provider("judge")
    records = "\n".join(f'<retrieved id="{h.chunk_id}">\n{h.text[:700]}\n</retrieved>' for h in hits)
    res = try_complete(chain, JUDGE_SYSTEM, f"{retrieval_facts(plan)}Records:\n{records}\n\nAnswer:\n{text}\n\nGrade the answer.", json_schema=JUDGE_SCHEMA, max_tokens=300)
    if res is None or res.parsed is None:
        return None
    p = res.parsed
    return {"claims": int(p["claims"]), "supported": int(p["supported"]), "unsupported": list(p.get("unsupported", []))[:5],
            "provider": res.provider, "model": res.model}


def run_case(case: dict[str, Any], session: Session, use_judge: bool) -> dict[str, Any]:
    t0 = time.perf_counter()
    plan = route_query(case["q"], NOW)
    hits = retrieve(plan, SITE, session, k=6)
    ans = answer(case["q"], hits, case["lang"], plan, now=NOW)
    latency = (time.perf_counter() - t0) * 1000
    expected = resolve(case["expect"], session)
    top5 = [h.chunk_id for h in hits[:5]]
    if case["expect"]["type"] == "none":
        recall = 1.0 if not hits or ans.path == "no_match" else 0.0
    else:
        recall = len(set(top5) & expected) / min(len(expected), 5) if expected else 0.0
    cited = [c.chunk_id for c in ans.citations]
    if case["expect"]["type"] == "none":
        cit_prec = 1.0 if not cited else 0.0
    else:
        cit_prec = (sum(1 for c in cited if c in expected) / len(cited)) if cited else 0.0
    valid = {h.chunk_id for h in hits}
    facts = sentences(ans.text)
    coverage = 1.0 if ans.path == "no_match" else (1.0 - len(uncited_sentences(ans.text, valid)) / max(1, len(facts)))
    j = judge(hits, ans.text, plan) if (use_judge and hits and ans.path != "no_match") else None
    faith = (j["supported"] / j["claims"]) if j and j["claims"] else coverage
    low = ans.text.lower()
    tripped = [s for s in case.get("must_not_say", []) if s.lower() in low]
    said = case.get("must_say_any")
    said_ok = (any(s.lower() in low for s in said) if said else True)
    return {"id": case["id"], "q": case["q"], "lang": case["lang"], "expected_lang_ok": language_ok(ans.text, case["lang"]),
            "path": ans.path, "provider": ans.provider, "model": ans.model, "plan_source": plan.source, "legs": plan.legs,
            "recall_at_5": round(recall, 3), "citation_precision": round(cit_prec, 3), "citation_coverage": round(coverage, 3),
            "faithfulness": round(faith, 3), "judge": j, "hallucination": bool(tripped) or (case["expect"]["type"] == "none" and bool(cited)),
            "tripped": tripped, "must_say_ok": said_ok, "latency_ms": round(latency, 1), "tokens": ans.tokens_in + ans.tokens_out,
            "citations": len(cited), "expected": sorted(expected)[:5], "top5": top5, "answer": ans.text[:300]}


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(k):
        return round(statistics.mean(r[k] for r in rows), 3)

    lat = [r["latency_ms"] for r in rows]
    out = {"cases": len(rows), "recall_at_5": mean("recall_at_5"), "citation_precision": mean("citation_precision"),
           "citation_coverage": mean("citation_coverage"), "faithfulness": mean("faithfulness"),
           "language_match": round(sum(r["expected_lang_ok"] for r in rows) / len(rows), 3),
           "must_say_ok": round(sum(r["must_say_ok"] for r in rows) / len(rows), 3),
           "hallucinations": sum(r["hallucination"] for r in rows),
           "latency_p95_ms": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 1), "latency_mean_ms": round(statistics.mean(lat), 1),
           "tokens_per_query": round(statistics.mean(r["tokens"] for r in rows), 1),
           "paths": {p: sum(1 for r in rows if r["path"] == p) for p in ("model", "template", "no_match")},
           "judged": sum(1 for r in rows if r["judge"]),
           "by_lang": {}}
    for lang in ("en", "hi", "ar"):
        sub = [r for r in rows if r["lang"] == lang]
        out["by_lang"][lang] = {"recall_at_5": round(statistics.mean(r["recall_at_5"] for r in sub), 3),
                                "faithfulness": round(statistics.mean(r["faithfulness"] for r in sub), 3),
                                "language_match": round(sum(r["expected_lang_ok"] for r in sub) / len(sub), 3)}
    out["gate"] = {"recall_at_5": out["recall_at_5"] >= GATE["recall_at_5"], "faithfulness": out["faithfulness"] >= GATE["faithfulness"],
                   "hallucinations": out["hallucinations"] <= GATE["hallucinations"]}
    out["gate"]["pass"] = all(out["gate"].values())
    return out


def markdown(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    g = summary["gate"]
    lines = ["| Metric | Value | Gate |", "|---|---|---|",
             f"| recall@5 | {summary['recall_at_5']:.2f} | {'pass' if g['recall_at_5'] else 'FAIL'} (≥ 0.80) |",
             f"| faithfulness | {summary['faithfulness']:.2f} | {'pass' if g['faithfulness'] else 'FAIL'} (≥ 0.90) |",
             f"| hallucination cases | {summary['hallucinations']} | {'pass' if g['hallucinations'] else 'FAIL'} (= 0) |",
             f"| citation precision | {summary['citation_precision']:.2f} | – |",
             f"| language match | {summary['language_match']:.2f} | – |",
             f"| latency p95 | {summary['latency_p95_ms']:.0f} ms | – |",
             f"| tokens / query | {summary['tokens_per_query']:.0f} | – |",
             f"| answer paths | {summary['paths']} | – |", "",
             "| Lang | recall@5 | faithfulness | language match |", "|---|---|---|---|"]
    for lang, v in summary["by_lang"].items():
        lines.append(f"| {lang} | {v['recall_at_5']:.2f} | {v['faithfulness']:.2f} | {v['language_match']:.2f} |")
    bad = [r for r in rows if r["recall_at_5"] < 1 or r["hallucination"] or not r["expected_lang_ok"]]
    if bad:
        lines += ["", "| Case | recall | faith | lang ok | path | note |", "|---|---|---|---|---|---|"]
        for r in bad:
            lines.append(f"| {r['id']} | {r['recall_at_5']:.2f} | {r['faithfulness']:.2f} | {r['expected_lang_ok']} | {r['path']} | {(r['tripped'] or (r['judge'] or {}).get('unsupported') or '')} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true", help="exit 1 when the gate fails")
    ap.add_argument("--out", default=str(ROOT / "docs/results/ask_eval.json"))
    ap.add_argument("--md", action="store_true", help="print the markdown table")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--only", default="", help="comma list of case ids")
    a = ap.parse_args(argv)
    logging.getLogger().setLevel(logging.WARNING)
    cases = yaml.safe_load((Path(__file__).parent / "cases.yaml").read_text())["cases"]
    if a.only:
        keep = set(a.only.split(","))
        cases = [c for c in cases if c["id"] in keep]
    eng = build_store()
    rows = []
    with Session(eng) as s:
        for c in cases:
            r = run_case(c, s, use_judge=not a.no_judge)
            rows.append(r)
            print(f"{r['id']:7s} recall={r['recall_at_5']:.2f} faith={r['faithfulness']:.2f} lang={'ok' if r['expected_lang_ok'] else 'NO'} "
                  f"path={r['path']:9s} {r['latency_ms']:7.0f}ms {'HALLUCINATION' if r['hallucination'] else ''}", flush=True)
    summary = summarise(rows)
    out = {"date": datetime.now(UTC).isoformat(), "embed_model": settings.embed_model, "llm_provider": settings.llm_provider,
           "answer_model": settings.ollama_model_answer, "summary": summary, "cases": rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if a.md:
        print(markdown(summary, rows))
    if a.gate and not summary["gate"]["pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
