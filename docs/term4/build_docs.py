"""Generate docs/viva_qa.md and docs/demo_script.md from docs/results/*.json.

Every number in the two documents comes from a results file. Run after
scripts/export_results.py and edge/training/eval.py:

  python3 docs/term4/build_docs.py
"""

from __future__ import annotations

import json
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1]
R = DOCS / "results"


def load(name: str) -> dict:
    return json.loads((R / name).read_text())


def pct(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def v2_sections() -> dict[str, str]:
    """v2 (Phases E-K) additions, all numbers read from docs/results/*.json."""
    a = load("ask_eval.json")["summary"]
    em = load("embed_spike.json")
    c = load("crew.json")
    tw = load("twin.json")
    fl = load("fleet.json")
    wa = load("watch.json")
    ig = load("integrations.json")
    se = load("security_eval.json")
    best = max(em["results"], key=lambda m: m.get("recall_at_5", 0)) if isinstance(em.get("results"), list) else None
    embed_line = f"{best['model']} (recall@5 {best['recall_at_5']:.2f})" if best else "bge-m3 (see embed_spike.json)"
    asi_rows = "\n".join(f"| {r['asi']} | {r['risk']} | {r['test']} | {'pass' if r['passed'] else 'FAIL'} |" for r in se["results"])
    viva = f"""

# v2 questions (Phases E-K: Ask, Watch, Crew, Twin, integrations, fleet, security)

## 16. How does Ask answer without making things up, and how do you know?

Retrieval first: a deterministic router (EN/HI/AR) decides the record kind, time window and any superlative; SQL prefilters, then structured ranking, BM25 and a vector leg ({embed_line}) are fused with reciprocal rank fusion. The model only writes sentences, and every factual sentence must carry a `[c:ID]` citation to a retrieved chunk or it is trimmed; if nothing is citable the answer is a localized template. An eval of {a['cases']} trilingual cases scored recall@5 {a['recall_at_5']:.2f}, faithfulness {a['faithfulness']:.2f}, citation coverage {a['citation_coverage']:.2f}, language match {a['language_match']:.2f}, {a['hallucinations']} hallucinations (judge: a second local model). Latency on the laptop: mean {a['latency_mean_ms']/1000:.1f} s, p95 {a['latency_p95_ms']/1000:.1f} s.

## 17. What does inference cost, and why is it zero?

Every model call goes through one adapter with the order Ollama (on the laptop or site box) then Gemini free tier then Groq free tier; the Anthropic client stays in code but off. Quotas are request counters per provider per day; when a provider is exhausted or unreachable the chain moves on, and when none is reachable each feature degrades to its deterministic path (Ask answers from records, the crew uses rule-based plans, the VLM opinion is skipped). One OpenTelemetry span per call records model, tokens, latency, prompt hash and cost; the dashboard's cost tile is the sum of spans per site per day and reads ${c['measured']['cost_usd']:.2f}.

## 18. Why a crew of six agents rather than one bigger agent?

Each agent owns a narrow trigger and a short allow-list, so a compromised or confused agent has a small blast radius: FloorOps cannot raise a work order, Safety cannot open a till, Analyst has no tools at all. They share one runtime, so every call still passes the Phase B Policy and ToolRunner; nothing gained a second execution path. Messages between agents are typed, schema-validated and signed with a per-agent HMAC ({c['envelope']['bus']}). Each run has a budget ({c['envelope']['budget_default']['max_tool_calls']} calls, ${c['envelope']['budget_default']['max_usd']}, {c['envelope']['budget_default']['max_seconds']} s), and the Auditor runs after every run. A FloorOps run takes {c['measured']['floorops_run_seconds']} s.

## 19. What can the vision-language model change?

Nothing that matters for safety. It sees at most a few blurred keyframes per event and returns agree/disagree with a confidence and a suggested severity. The suggestion is stored as a metric; the event's severity is never written by that path, which is asserted after every write and tested on a severity-3 event with a suggested severity of 1. At disagreement confidence at or above {wa['policy'].split('>= ')[1].split(';')[0] if '>= ' in wa['policy'] else '0.8'} it may add a human-review request, which is the one thing a rule-agreeing opinion can do. Measured: qwen2.5vl:7b answers in {wa['opinion']['warm_s']} s warm on {wa['opinion']['frames']} frames.

## 20. What is the digital twin for?

Replay and counterfactuals on the same records. A day is binned into {tw['replay_bins']} one-minute bins from events alone and played on the 3D floor at up to 600x ({tw['playback_fps_headless_60x']} fps headless at 60x); what-if sliders re-run the M/M/c model and the staffing MILP on the day's real arrivals, so a manager sees the wait and staff-hour delta of one more till before opening it. Scenarios are saved as documents Ask can cite.

## 21. What changed when POS data arrived?

The service rate. With transactions in a slot, mu is throughput per open till and is labelled `pos`; otherwise it stays `estimated_from_video`. POS lag features enter the forecast only when they lower holdout MAE. Shelf intelligence added two deterministic rules on the edge: R14 price mismatch (OCR of the tag against the price list) and R15 planogram drift (missing and misplaced cells against a reference). WhatsApp sends approved templates only ({ig['whatsapp']['templates']} templates in {len(ig['whatsapp']['languages'])} languages) to an opt-in roster; free text is refused by design.

## 22. How do you run many stores, and what tells you a model has gone stale?

One API, sites scoped per user, four roles ({', '.join(fl['auth']['roles'])}) verified from Supabase JWTs server-side. Every edge box sends a heartbeat per minute and a detection-confidence sample every {fl['drift']['sample_every_s']} s; a population stability index over a {fl['drift']['window_h']}-hour window against a {fl['drift']['baseline_days']}-day baseline flags drift after {fl['drift']['hours_over']} hours over {fl['drift']['threshold_psi']} with a suggested fix (healthy PSI measured {fl['drift']['healthy_psi_measured']}, an injected confidence drop {fl['drift']['injected_confidence_drop_psi']}); five silent minutes raise `edge_offline`. Retention is enforced by a job (clips {fl['retention']['clips_days']} d, events {fl['retention']['events_days']} d, memories {fl['retention']['memories_days']} d unless pinned) that logs what it deleted.

## 23. How do you know the agents are safe to run?

By attacking them. The OWASP Top 10 for Agentic Applications maps one control and one executable attack to each risk, and CI fails on any regression ({se['passed']}/{se['total']} passing on {se['date'][:10]}):

| ASI | Risk | Attack | Result |
|---|---|---|---|
{asi_rows}

Also: defensive headers and a CSP on both the API and the web app, an SSRF guard on URL ingest, a weights hash pin that stops the edge box from starting on a mismatch, lockfiles with pip-audit, npm audit and a secret scan in CI. Full model: docs/security/threat_model.md.
"""

    demo = f"""# Demo video script v2 — 4 minutes, English, narrated

Continues docs/demo_script.md (the three-minute v1 cut). Numbers are read from docs/results/ at build time.

**0:00–0:25 · Ask.** Press `/`, type "Which till had the longest queue last Friday evening?" Watch the stages stream: route, retrieve, answer. Click a citation chip; the event page opens. Switch to Hindi, ask the same. "Every sentence cites a record. {a['cases']} trilingual cases, {a['hallucinations']} hallucinations, ${c['measured']['cost_usd']:.0f} of inference."

**0:25–0:55 · Watch.** The camera wall, heads blurred before the stream ({wa['stream']['client_fps_measured']} fps at the client). Open a queue event, press Request opinion: the VLM agrees at 0.9. Open a severity-3 breach where it disagreed: the severity did not move. "A second opinion can ask for a human. It cannot lower a severity."

**0:55–1:35 · Crew.** Roster with budgets, the run graph, the signed message log. Post a queue event: FloorOps lights, proposes till 2 with evidence, the Auditor checks it in {c['measured']['auditor_run_seconds']} s. Type KILL: every agent route returns 503, the deterministic path still escalates severity 3. Resume.

**1:35–2:05 · Twin.** Pick yesterday, Play at 60x; the floor breathes with the day ({tw['replay_bins']} bins). Move the tills slider: the wait and staff-hour delta update. Save as scenario, then ask Ask about it.

**2:05–2:35 · Settings, Shelves, Fleet.** Import the labelled POS sample; the queue model's mu switches to POS. Shelves: planogram compliance and a price-tag mismatch. Fleet: the leaderboard, a drift panel that suggests a fix, edge health from heartbeats.

**2:35–3:20 · Security.** The ASI scorecard: {se['passed']} of {se['total']} attacks defended, each with its evidence. Edit the till-proposal threshold as Admin: the diff, the note, the confirmation, the attribution. Sign in as an Operator: read-only. The memory-guard log shows what was quarantined.

**3:20–4:00 · Close.** "Same cameras, same events, same policy. v2 adds judgement in six narrow agents, a memory that can be rolled back, a twin to test decisions before making them, and a red-team gate that runs on every push. Cost of inference: zero. RAQIB."
"""

    onepager = f"""# RAQIB v2 — one page

**What.** A vision-operations control room for supermarkets (RAQIB) and factories (MUSHRIF) that runs on the cameras a site already owns. Deterministic rules turn detections into events; queueing theory, a forecast and an integer program turn events into staffing decisions; a bounded crew of agents proposes or acts through one policy; people approve from a trilingual console.

**What is new in v2.**
- **Ask:** cited answers over events, KPIs and documents in EN/HI/AR. {a['cases']} eval cases: recall@5 {a['recall_at_5']:.2f}, faithfulness {a['faithfulness']:.2f}, {a['hallucinations']} hallucinations.
- **Watch:** blurred camera wall with live boxes, captions, and VLM second opinions that can ask for a human but never lower a severity.
- **Crew:** six narrow agents on one runtime with allow-lists, budgets, signed messages, an Auditor after every run, guarded memory with rollback, and a kill switch.
- **Twin:** replay any day at one-minute resolution and test "one more till" before opening it.
- **Integrations:** POS import (mu from POS), planogram and price-tag rules on the edge, WhatsApp templates to an opt-in roster, Greenlam tracker with a circuit breaker.
- **Fleet and ops:** Supabase Auth with four roles and site scoping, drift detection (PSI) with a suggested fix, edge health, retention, one span per model call and a cost KPI.
- **Security:** OWASP ASI01-ASI10 mapped to controls and executable attacks; {se['passed']}/{se['total']} defended; CI gate with pip-audit, npm audit and a secret scan.

**Numbers that matter.**

| | |
|---|---|
| Inference spend | ${c['measured']['cost_usd']:.2f} (Ollama, then Gemini and Groq free tiers) |
| Ask latency (laptop, 8B model) | mean {a['latency_mean_ms']/1000:.1f} s, p95 {a['latency_p95_ms']/1000:.1f} s |
| Crew run | FloorOps {c['measured']['floorops_run_seconds']} s, Auditor {c['measured']['auditor_run_seconds']} s |
| Twin playback | {tw['playback_fps_headless_60x']} fps headless at 60x |
| Drift alert | PSI > {fl['drift']['threshold_psi']} for {fl['drift']['hours_over']} h vs a {fl['drift']['baseline_days']}-day baseline |
| Red team | {se['passed']} of {se['total']} ASI attacks defended |

**Ask of a pilot site.** One entrance, one checkout bank, three shelves, an edge box the site owns, four weeks; gates: false alerts < 5 per camera per day, approval rate >= 60 %, then service level >= 90 % and OSA >= 98 %. Software stays under USD 50 a month; inference stays at zero on-prem.

**Links.** Live: https://raqib-orcin.vercel.app · API: https://raqib-backend-7qdg.onrender.com/docs · Repo: https://github.com/krish2105/RAQIB-AI-in-Operations · Threat model: docs/security/threat_model.md
"""
    return {"viva": viva, "demo": demo, "onepager": onepager}


def main() -> None:
    k = load("kpis_retail.json")
    kf = load("kpis_factory.json")
    f = load("forecast_retail.json")
    w = load("workforce_retail.json")
    r = load("report_retail_en.json")
    e = load("edge_eval.json")
    y = e["detectors"]["yolo"]
    rt = e["detectors"].get("rtdetr", {})
    p = e["pipeline"]
    ba = r["before_after"] or {}
    st = r["staffing"] or {}
    gov = r["governance"]

    viva = f"""# Viva Q&A — RAQIB (AI 218, AI in Operations)

Numbers below are read from `docs/results/` at build time (`docs/term4/build_docs.py`). Regenerate after every eval run.

## 1. Why is this an operations project and not a computer-vision project?

The detector is a commodity: COCO-pretrained YOLO26n finds people at {y['latency_ms_p50']} ms per frame. The work is what happens after: a deterministic rule engine turns tracks into operational events (queue over limit, shelf gap, service completion), queueing theory turns those into utilisation and expected wait per 15-minute slot, an integer program turns utilisation into a staffing plan, and a bounded agent turns that into proposals a floor manager approves. The KPIs are operations KPIs: service level {pct(k['service_level'])}, on-shelf availability {pct(k['osa_store'])}, peak utilisation ρ {k['peak_rho']:.2f}. Vision is the sensor.

## 2. Explain M/M/c and why you chose it; what assumptions does it violate here?

M/M/c: Poisson arrivals at rate λ, exponential service at rate μ per server, c identical servers, one FCFS queue. Erlang-C gives P(wait), L_q, W_q closed-form, so the dashboard can compute expected wait per slot instantly and compare it with the observed queue. Violations: service times at a checkout are closer to log-normal than exponential; arrivals are non-stationary within a slot; customers jockey between tills (c parallel queues, not one). That is exactly why the "model vs observed" card exists: the gap between W_q(model) and W_q(observed via Little's law) is displayed, not hidden. In the demo the last observed slots show ρ up to {k['peak_rho']:.2f}.

## 3. How did you estimate arrival and service rates from video and POS?

λ per slot = footfall ticks (a track's first entry into the entrance zone) per 15 minutes × 4. μ per till = 3600 / mean dwell of tracks that left a checkout zone after ≥ 20 s (rule R13). There is no POS in the demo, so μ is labelled `estimated_from_video` everywhere it appears; in the pilot a POS CSV importer replaces it. Current estimate: μ ≈ {w['mu']:.0f} customers per hour per till.

## 4. What is on-shelf availability and how is it measured here?

OSA = 1 − (time a shelf face is in a gap state) / (window). A gap opens when the shelf ROI's empty ratio (Canny edge density + colour variance heuristic, later a trained classifier) exceeds 0.4 for 5 minutes (rule R11) and closes when the signal stops. Store OSA over the last 24 h: {pct(k['osa_store'])}; per shelf: {', '.join(f"{s} {pct(v)}" for s, v in k['osa'].items())}. Time to restock (mean gap episode): {', '.join(f"{s} {v:.0f} min" for s, v in k['time_to_restock_min'].items()) or 'no gaps'}.

## 5. Why deterministic rules plus an LLM agent, not an LLM end-to-end?

Rules are auditable (each event carries its rule id and threshold), cheap (microseconds), and testable (12 synthetic-track tests). A language model on video would be slow, expensive per frame, and impossible to certify for a safety decision. The LLM adds judgement about what to do, and only via seven allow-listed tools with strict schemas. Both backends (DryRun policy table and Claude) go through the same Policy layer, so the model can be swapped without changing what is allowed.

## 6. Which decisions are autonomous and which are proposals, and why?

Autonomous: `send_alert` (templates only), `create_work_order` for severity ≤ 2, `log_downtime`, `escalate` (mandatory on severity 3), `request_human_review` (mandatory below 0.6 confidence). Proposals: `propose_open_till`, `propose_staffing_change`, `propose_maintenance_window`, because they move people or stop machines. In the seeded week the agent took {gov['actions']} actions ({gov['autonomous']} autonomous, {gov['proposals']} proposals), {gov['tool_calls']} tool calls, {gov['failed_calls']} failed, model cost ${gov['cost_usd']}.

## 7. How does the workforce MILP work and what did it save?

Minimise Σ tills per slot subject to λ_s / (tills_s · μ) ≤ 0.85 and 1 ≤ tills_s ≤ max, integer; solved with HiGHS via `scipy.optimize.milp`. The problem separates per slot today, but the MILP form lets us add adjacency and minimum-shift constraints without a rewrite (`max_step` is already implemented). One day: {w['staff_hours']} staff-hours vs {w['baseline_staff_hours']} with three tills open all day, saving {w['savings_hours']} hours. Over the week the plan peaks at {st.get('peak_tills', 'n/a')} tills with a mean of {st.get('mean_tills', 'n/a')}.

## 8. How did forecasting perform against the naive baseline?

Hourly footfall, GradientBoostingRegressor with hour, weekday, lag-24, lag-168, rolling means, and a leak-free hour-of-week profile, versus seasonal naive (same hour last week). Seven-day holdout: MAE {f['mae']} vs {f['mae_naive']} ({f['improvement_pct']}% better, MAPE {f['mape']}%). This is on the labelled simulator, which is close to the naive model's assumptions, so the margin understates what real data with promotions and weather would show. The spec target of 20% is a pilot deliverable.

## 9. What would change in a real store with real POS data?

μ becomes exact per till and per hour; basket size and payment method explain service-time variance; λ can be validated against transaction counts; OSA can be cross-checked with sales drop-offs per SKU. The model-vs-observed gap becomes a calibration signal rather than a caveat.

## 10. Privacy and ethics: what leaves the camera?

Events (timestamp, camera, zone, class, confidence, count) and 10-second clips in which every detected person's head band is pixelated and blurred before storage. No face recognition, no cross-camera identity, track ids reset per session. The agent never sees video. Simulated history is flagged in every payload and labelled in the UI.

## 11. What does the pilot cost and what KPIs prove it?

Under USD 50 per month for the software stack (Render small instance, Supabase free, Vercel hobby, Claude API at ~50 actionable events a day) plus an edge box the site already owns. KPIs: service level ≥ 90% of slots, OSA ≥ 98%, false alerts per camera per day < 5, human approval rate ≥ 60%, frame-to-alert latency < 3 s (measured now: {p['frame_to_event_ms_p95']} ms p95 frame-to-event on the edge).

## 12. Biggest technical risk and biggest business risk?

Technical: data. PPE and shelf models need about two hours of labelled site footage; COCO weights only see persons. Business: trust. If the first week produces noisy alerts, staff ignore the system. The pilot SOP therefore tunes thresholds before turning on real work orders.

## 13. How is RAQIB different from existing queue-management vendors?

Vendors sell people counters and a dashboard. RAQIB adds the operations layer: a queueing model that says how many tills the arrivals justify, a forecast of when, an integer program for the roster, and an agent that files the task. It also runs on existing cameras and an edge box instead of proprietary sensors.

## 14. What did you learn about operations management from building it?

That utilisation, not headcount, is the lever: at ρ ≈ 0.9 a single extra till cuts expected wait by an order of magnitude, while off-peak the same store runs fine on one. That service level is a scheduling problem before it is a staffing problem. And that every model needs an observed counterpart on the same chart or nobody trusts it.

## 15. If you had one more month, what would you build?

POS import and per-till μ; a labelled site dataset and fine-tuned PPE weights; a planogram check for shelves; digital-twin playback on the 3D floor (scrub a day); and the 24-hour unattended soak test on a real camera.

## Appendix: measured numbers used above

| Metric | Value | File |
|---|---|---|
| YOLO26n p50 latency / detect fps | {y['latency_ms_p50']} ms / {y['fps_detect_only']} | edge_eval.json |
| RT-DETR-L p50 latency / detect fps | {rt.get('latency_ms_p50', 'n/a')} ms / {rt.get('fps_detect_only', 'n/a')} | edge_eval.json |
| Pipeline fps / frame→event p50 / p95 | {p['fps_end_to_end']} / {p['frame_to_event_ms_p50']} ms / {p['frame_to_event_ms_p95']} ms | edge_eval.json |
| Service level / OSA / peak ρ (24 h) | {pct(k['service_level'])} / {pct(k['osa_store'])} / {k['peak_rho']:.2f} | kpis_retail.json |
| Forecast MAE / naive / improvement | {f['mae']} / {f['mae_naive']} / {f['improvement_pct']}% | forecast_retail.json |
| Staff-hours plan / baseline / saved | {w['staff_hours']} / {w['baseline_staff_hours']} / {w['savings_hours']} | workforce_retail.json |
| Customer wait before / after / reduction | {ba.get('baseline_customer_wait_min', 'n/a')} / {ba.get('with_plan_customer_wait_min', 'n/a')} / {ba.get('reduction_pct', 'n/a')}% | report_retail_en.json |
| Factory compliance / downtime / breaches (24 h) | {pct(kf['compliance'])} / {kf['downtime_min']} min / {kf['breaches']} | kpis_factory.json |
"""
    v2 = v2_sections()
    (DOCS / "viva_qa.md").write_text(viva + v2["viva"])
    (DOCS / "demo_script_v2.md").write_text(v2["demo"])
    (DOCS / "pitch").mkdir(exist_ok=True)
    (DOCS / "pitch" / "onepager_v2.md").write_text(v2["onepager"])

    demo = f"""# Demo video script — 3 minutes, English, narrated

Screen recording of the live dashboard with the edge preview window picture-in-picture. Talking points, not a script; Krishna is a trained anchor.

**0:00–0:20 · The problem in one picture.** Edge preview on the Pexels checkout clip: boxes, blurred heads, zones drawn. "Every store already has cameras. Nobody watches forty feeds. RAQIB does, and it only ever reports counts and events."

**0:20–0:50 · The tape.** Dashboard, dark theme. Point at the 24-hour strip: footfall trace, ticks coloured by severity, the pen at the right edge. Hover to scrub. "Everything the watcher saw today, on one line. Click a tick and you are at the event."

**0:50–1:20 · An event.** Click a queue-over tick. Clip plays (heads blurred), confidence bar, rule R10 text, the agent's decision: alert sent, and a proposal to open till 2 because ρ was above 0.85. "The rule is deterministic. The agent explains itself. The human decides."

**1:20–1:45 · Approve.** Actions page. Approve the till proposal; status flips to Executed; audit table increments. Show a restock work order raised autonomously for a shelf gap. "Autonomy is bounded: severity three always escalates, nothing can be downgraded, one work order per machine per four hours."

**1:45–2:15 · The operations layer.** Forecast page: next 24 h vs seasonal naive, MAE {f['mae']} vs {f['mae_naive']} ({f['improvement_pct']}% better). Staffing plan: {w['staff_hours']} staff-hours vs {w['baseline_staff_hours']} flat, saving {w['savings_hours']} hours, utilisation capped at 0.85. "Queueing theory tells us how many tills; the integer program tells us when."

**2:15–2:40 · Profile switch and languages.** Switch site to greenlam_unit1: MUSHRIF, amber, PPE compliance {pct(kf['compliance'])}, exclusion-zone breach on the 3D floor. Switch to Arabic: RTL, report in Arabic. Toggle light theme.

**2:40–3:00 · Numbers and close.** Edge runs at {p['fps_end_to_end']} fps end to end on a laptop, {p['frame_to_event_ms_p50']} ms from frame to event. "Existing cameras, an edge box, and a watcher that explains itself. RAQIB."
"""
    (DOCS / "demo_script.md").write_text(demo)
    print("wrote docs/viva_qa.md, docs/demo_script.md, docs/demo_script_v2.md, docs/pitch/onepager_v2.md")


if __name__ == "__main__":
    main()
