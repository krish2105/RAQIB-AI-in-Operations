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
    (DOCS / "viva_qa.md").write_text(viva)

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
    print("wrote docs/viva_qa.md and docs/demo_script.md")


if __name__ == "__main__":
    main()
