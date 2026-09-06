"""Build docs/AI218_RAQIB_deck.pptx: 12 dark slides, one idea each, speaker notes as talking points.

  cd cloud && uv run --no-sync python ../docs/term4/build_deck.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DOCS, all_figures, load, num, pct  # noqa: E402

from pptx import Presentation  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.text import PP_ALIGN  # noqa: E402
from pptx.util import Emu, Inches, Pt  # noqa: E402

OUT = DOCS / "AI218_RAQIB_deck.pptx"
BG = RGBColor(0x0B, 0x0D, 0x10)
INK = RGBColor(0xE8, 0xEA, 0xED)
MUTED = RGBColor(0x8B, 0x93, 0xA1)
SIGNAL = RGBColor(0x1F, 0xD1, 0xB9)
AMBER = RGBColor(0xFF, 0xB0, 0x20)
CRIT = RGBColor(0xFF, 0x4D, 0x3D)


def slide(prs, eyebrow: str, title: str, notes: str, number: int):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = BG
    tb = s.shapes.add_textbox(Inches(0.6), Inches(0.45), Inches(9), Inches(0.4)).text_frame
    p = tb.paragraphs[0]
    p.text = eyebrow.upper()
    p.runs[0].font.size = Pt(11)
    p.runs[0].font.color.rgb = SIGNAL
    p.runs[0].font.bold = True
    tt = s.shapes.add_textbox(Inches(0.6), Inches(0.85), Inches(12), Inches(1.2)).text_frame
    tt.word_wrap = True
    p = tt.paragraphs[0]
    p.text = title
    p.runs[0].font.size = Pt(34)
    p.runs[0].font.color.rgb = INK
    p.runs[0].font.bold = True
    n = s.shapes.add_textbox(Inches(12.3), Inches(6.9), Inches(0.8), Inches(0.4)).text_frame
    n.paragraphs[0].text = f"{number:02d}"
    n.paragraphs[0].alignment = PP_ALIGN.RIGHT
    n.paragraphs[0].runs[0].font.size = Pt(11)
    n.paragraphs[0].runs[0].font.color.rgb = MUTED
    s.notes_slide.notes_text_frame.text = notes
    return s


def big_number(s, x, y, value: str, label: str, color=SIGNAL, size=60):
    tf = s.shapes.add_textbox(Inches(x), Inches(y), Inches(4), Inches(1.3)).text_frame
    p = tf.paragraphs[0]
    p.text = value
    p.runs[0].font.size = Pt(size)
    p.runs[0].font.bold = True
    p.runs[0].font.color.rgb = color
    lf = s.shapes.add_textbox(Inches(x), Inches(y + 1.25), Inches(4.2), Inches(0.8)).text_frame
    lf.word_wrap = True
    p = lf.paragraphs[0]
    p.text = label
    p.runs[0].font.size = Pt(13)
    p.runs[0].font.color.rgb = MUTED


def body(s, x, y, w, lines: list[str], size=16, color=INK):
    tf = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(4)).text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.runs[0].font.size = Pt(size)
        p.runs[0].font.color.rgb = color
        p.space_after = Pt(10)


def picture(s, path: Path, x, y, w):
    s.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w))


def main() -> None:
    k = load("kpis_retail.json")
    kf = load("kpis_factory.json")
    f = load("forecast_retail.json")
    w = load("workforce_retail.json")
    r = load("report_retail_en.json")
    e = load("edge_eval.json")
    figs = all_figures()
    p_ = e["pipeline"]
    y = e["detectors"]["yolo"]
    gov = r["governance"]
    ba = r["before_after"] or {}

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    s = slide(prs, "MAIB AI 218 · AI in Operations", "RAQIB · رقيب\nThe watcher on the floor", "Open with the name: RAQIB means the watcher. Existing cameras, an edge box, an agent that explains itself. Krishna Mathur, Term 4 deployed MVP.", 1)
    body(s, 0.6, 3.2, 8, ["A vision-driven operations control room for supermarket floors.", "Same engine, factory profile: MUSHRIF for the Greenlam pilot.", "Krishna Mathur · github.com/krish2105/RAQIB-AI-in-Operations"], size=18, color=MUTED)

    s = slide(prs, "The problem", "Every store has forty cameras and nobody watching them", "One picture: a checkout queue and an empty shelf. Queues over three cause walk-outs; out-of-stocks cost about 4% of sales. Cameras record both and act on neither.", 2)
    body(s, 0.6, 2.4, 11.5, ["Queues longer than three customers drive walk-outs. Shelf gaps cost ~4% of sales (Gruen et al., 2002).", "Both are counted by hand, by mystery shoppers, or not at all.", "The gap is not sensing. It is turning what the camera sees into a decision inside the shift."])

    s = slide(prs, "What RAQIB does", "Sees · Learns · Acts · Explains", "Four verbs. Sees: footfall, queues, checkout dwell, shelf gaps. Learns: queueing model, forecast, staffing plan. Acts: alerts, restock tasks, proposals for tills. Explains: rule, confidence, rationale on every action.", 3)
    body(s, 0.6, 2.4, 6, ["Sees — person tracks, queue zones, checkout dwell, shelf empty ratio", "Learns — M/M/c utilisation, next-24 h forecast, staffing integer program"], size=17)
    body(s, 6.9, 2.4, 6, ["Acts — templated alerts, restock work orders, proposals to open a till (only if ρ > 0.85)", "Explains — every action carries the rule id, the confidence, and a written rationale"], size=17)

    s = slide(prs, "Architecture", "Rules on the edge, judgement in the cloud, humans on the floor", "Edge: capture, blur faces, detect, track, rules, SQLite, sync. Cloud: events, analytics, bounded agent behind a policy. Web: the tape, KPIs, 3D floor, actions. Detector is behind an adapter; YOLO26 swaps for RT-DETR with one flag.", 4)
    body(s, 0.6, 2.4, 12, ["edge/  capture → blur every head → YOLO26n ⇄ RT-DETR → ByteTrack → zones → deterministic rules → SQLite → idempotent sync", "cloud/  events · SSE · M/M/c · OSA · forecast · MILP · agent: backend → Policy → 7 allow-listed tools → Greenlam tracker", "web/  the 24-hour tape · KPIs · 3D floor · event clip + decision · approve/reject · forecast · report EN/HI/AR"], size=15)

    s = slide(prs, "Live demo", "raqib-orcin.vercel.app", "Grader path in under ten minutes: dashboard → tape tick → event clip and decision → approve a proposal → executed and audited → forecast → report. QR on this slide when deployed.", 5)
    body(s, 0.6, 2.4, 12, ["1 · Dashboard: the tape, KPIs, 3D floor pulsing where events land", "2 · Click a tick: clip (faces blurred), confidence, rule R10, agent decision", "3 · Actions: approve 'open till 2' → Executed; restock work orders raised autonomously", "4 · Forecast and staffing plan · 5 · Weekly report, print to PDF"], size=16)

    s = slide(prs, "Detection", "Same pipeline, two detectors, one flag", "Adapter pattern exists for licensing: Ultralytics is AGPL; RT-DETR architecture is Apache. Numbers from edge_eval.json on the M4 Pro.", 6)
    big_number(s, 0.6, 2.4, f"{y['latency_ms_p50']} ms", "YOLO26n median latency per frame (MPS)")
    big_number(s, 5.0, 2.4, f"{p_['fps_end_to_end']} fps", "end-to-end: detect, track, blur, rules, store")
    big_number(s, 9.2, 2.4, f"{p_['frame_to_event_ms_p95']} ms", "frame → event, p95", color=MUTED, size=44)
    picture(s, figs["latency"], 0.6, 4.7, 7.5)

    s = slide(prs, "Queue model vs observed", f"Peak utilisation ρ {num(k['peak_rho'], 2)} · service level {pct(k['service_level'])}", "M/M/c with lambda from footfall ticks and mu from checkout dwell on video. The observed W_q via Little's law sits on the same chart as the model; the gap is the point, not a caveat.", 7)
    picture(s, figs["queue"], 0.6, 2.3, 8.2)
    body(s, 9.1, 2.4, 3.8, ["λ from entrance ticks per 15 min", f"μ ≈ {w['mu']:.0f}/h per till, estimated from video", "Observed W_q = queue length / λ (Little)", "Target: ρ ≤ 0.85, queue ≤ 3 in 90% of slots"], size=14, color=MUTED)

    s = slide(prs, "Forecast vs baseline", f"{f['improvement_pct']}% better than seasonal naive", f"Gradient boosting versus same-hour-last-week. MAE {f['mae']} vs {f['mae_naive']}, MAPE {f['mape']}%. Honest caveat: this is on the labelled simulator; real data with promotions and weather should widen the margin.", 8)
    picture(s, figs["forecast"], 0.6, 2.3, 8.2)
    big_number(s, 9.1, 2.4, str(f["mae"]), "MAE, gradient boosting")
    big_number(s, 9.1, 4.5, str(f["mae_naive"]), "MAE, seasonal naive", color=MUTED, size=44)

    s = slide(prs, "Workforce optimisation", f"{w['staff_hours']} staff-hours instead of {w['baseline_staff_hours']}", f"Integer program: minimise tills per slot subject to rho ≤ 0.85. Saves {w['savings_hours']} staff-hours a day; wait time before/after with proposals applied: {ba.get('reduction_pct', 'n/a')}% reduction.", 9)
    picture(s, figs["workforce"], 0.6, 2.3, 8.2)
    big_number(s, 9.1, 2.4, f"{w['savings_hours']} h", "saved per day vs three tills all day")
    big_number(s, 9.1, 4.5, f"{ba.get('reduction_pct', 'n/a')}%", "less customer wait with proposals applied", color=MUTED, size=44)

    s = slide(prs, "Agent governance", "Bounded autonomy, not blind autonomy", f"Seven allow-listed tools with strict schemas. Severity 3 always escalates and cannot be downgraded. One work order per machine per 4 hours. Proposals need a human. Seeded week: {gov['actions']} actions, {gov['tool_calls']} tool calls, {gov['failed_calls']} failed, ${gov['cost_usd']} model cost.", 10)
    body(s, 0.6, 2.4, 6, ["Autonomous: alert (templates), restock/work order ≤ sev 2, log downtime, escalate on sev 3, ask for review < 0.6 confidence", "Proposal: open till (must cite ρ > 0.85), staffing change, maintenance window"], size=16)
    body(s, 6.9, 2.4, 6, ["Policy cannot be bypassed by either backend (dry-run or Claude)", "Every call validated and logged: input, output, latency, cost", f"This week: {gov['actions']} actions · {gov['tool_calls']} calls · {gov['failed_calls']} failed · ${gov['cost_usd']}"], size=16)

    s = slide(prs, "Business case", "One Dubai hypermarket, 90 days", "Pilot on existing cameras and an owned edge box. Software under USD 50 a month. Gates: false alerts under 5 per camera per day, approval rate over 60%, then service level 90% and OSA 98%. MUSHRIF factory profile shares the engine.", 11)
    body(s, 0.6, 2.4, 12, ["Weeks 1–4 · one entrance, one checkout bank, three shelves · gate: false alerts < 5/camera/day, approval ≥ 60%", "Weeks 5–8 · all tills, POS import for μ, staffing plan into rosters · gate: service level ≥ 90%, forecast ≥ 20% better on real data", "Weeks 9–13 · aisle shelves, second store · gate: OSA ≥ 98%, < USD 150/store/month", f"Factory profile today: compliance {pct(kf['compliance'])}, {kf['downtime_min']} min downtime, {kf['breaches']} breach in 24 h on the Greenlam demo site"], size=15)

    a = load("ask_eval.json")["summary"]
    c = load("crew.json")
    tw = load("twin.json")
    se = load("security_eval.json")
    s = slide(prs, "v2 · Ask and Watch", f"Cited answers in three languages · {a['hallucinations']} hallucinations on {a['cases']} cases", f"Ask: deterministic router, hybrid retrieval, a citation on every factual sentence or a template. Eval: recall@5 {a['recall_at_5']:.2f}, faithfulness {a['faithfulness']:.2f}, language match {a['language_match']:.2f}. Watch: blurred wall, VLM opinion that can ask for a human but never lowers severity. Inference cost zero: Ollama, then Gemini and Groq free tiers.", 12)
    big_number(s, 0.6, 2.4, f"{a['recall_at_5']:.2f}", "recall@5, 30 EN/HI/AR questions")
    big_number(s, 5.0, 2.4, f"{a['faithfulness']:.2f}", "faithfulness, judged by a second local model")
    big_number(s, 9.2, 2.4, f"${c['measured']['cost_usd']:.0f}", "inference spend (Ollama → Gemini free → Groq free)", color=MUTED, size=44)
    body(s, 0.6, 4.8, 12, ["Every factual sentence carries [c:ID]; uncited sentences are trimmed; nothing citable → localized template", "Watch: heads blurred before the stream; a VLM second opinion is a metric and a review request, never a severity"], size=15)

    s = slide(prs, "v2 · Crew and Twin", "Six narrow agents, one policy, a twin to test decisions first", f"Crew: allow-lists before Policy, budgets, HMAC bus, Auditor after every run, guarded memory with rollback, kill switch with deterministic fallback. FloorOps runs in {c['measured']['floorops_run_seconds']} s. Twin: {tw['replay_bins']} one-minute bins, {tw['playback_fps_headless_60x']} fps at 60x, what-if re-runs M/M/c and the MILP.", 13)
    body(s, 0.6, 2.4, 6, ["FloorOps · ShelfOps · Workforce · Safety · Analyst (no tools) · Auditor (mandatory)", f"Budget per run: {c['envelope']['budget_default']['max_tool_calls']} calls · ${c['envelope']['budget_default']['max_usd']} · {c['envelope']['budget_default']['max_seconds']} s", "Signed, typed messages; proposals must cite evidence; KILL returns 503 on agent routes, severity 3 still escalates"], size=15)
    body(s, 6.9, 2.4, 6, [f"Replay any day in {tw['replay_bins']} bins on the 3D floor, scrub at up to 600x", "What-if: one more till → wait and staff-hour delta before opening it", "Fleet: four roles, site scoping, PSI drift with a suggested fix, edge heartbeats, retention job, cost per day"], size=15)

    s = slide(prs, "v2 · Security", f"{se['passed']} of {se['total']} OWASP agentic attacks defended, gated in CI", "OWASP Top 10 for Agentic Applications: one control and one executable attack per risk. The harness runs against an in-process API on every push with pip-audit, npm audit and a secret scan. Policy edits are diffed, confirmed and attributed; Operators see them read-only.", 14)
    body(s, 0.6, 2.3, 12, [f"{r['asi']} {r['risk']}: {r['test']}" for r in se["results"][:5]], size=13)
    body(s, 0.6, 4.6, 12, [f"{r['asi']} {r['risk']}: {r['test']}" for r in se["results"][5:]], size=13)

    s = slide(prs, "Limitations · next steps · thank you", "Data is the risk. Trust is the product.", "Say the limits plainly: public clips not a store; simulator history; AGPL; free-tier database is ephemeral until Supabase is wired; weights pin enforced only where set. Next: a real store, Supabase Auth providers on, Gemini key for the semantic leg on the free-tier API, 24-hour soak. Thank you.", 15)
    body(s, 0.6, 2.4, 6, ["Public clips, not a store · 21-day labelled simulator · COCO weights, PPE mAP not measured · AGPL detector · free-tier API on ephemeral SQLite until the Supabase URL is set"], size=15, color=MUTED)
    body(s, 6.9, 2.4, 6, ["Next: a pilot store · Supabase Auth providers on · a Gemini key for the semantic leg on the free tier · two hours of labelled site footage · 24-hour unattended soak", "شكرًا · धन्यवाद · Thank you"], size=15)

    prs.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
