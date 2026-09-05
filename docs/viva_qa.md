# Viva Q&A — RAQIB (AI 218, AI in Operations)

Numbers below are read from `docs/results/` at build time (`docs/term4/build_docs.py`). Regenerate after every eval run.

## 1. Why is this an operations project and not a computer-vision project?

The detector is a commodity: COCO-pretrained YOLO26n finds people at 8.9 ms per frame. The work is what happens after: a deterministic rule engine turns tracks into operational events (queue over limit, shelf gap, service completion), queueing theory turns those into utilisation and expected wait per 15-minute slot, an integer program turns utilisation into a staffing plan, and a bounded agent turns that into proposals a floor manager approves. The KPIs are operations KPIs: service level 98.9%, on-shelf availability 97.3%, peak utilisation ρ 0.95. Vision is the sensor.

## 2. Explain M/M/c and why you chose it; what assumptions does it violate here?

M/M/c: Poisson arrivals at rate λ, exponential service at rate μ per server, c identical servers, one FCFS queue. Erlang-C gives P(wait), L_q, W_q closed-form, so the dashboard can compute expected wait per slot instantly and compare it with the observed queue. Violations: service times at a checkout are closer to log-normal than exponential; arrivals are non-stationary within a slot; customers jockey between tills (c parallel queues, not one). That is exactly why the "model vs observed" card exists: the gap between W_q(model) and W_q(observed via Little's law) is displayed, not hidden. In the demo the last observed slots show ρ up to 0.95.

## 3. How did you estimate arrival and service rates from video and POS?

λ per slot = footfall ticks (a track's first entry into the entrance zone) per 15 minutes × 4. μ per till = 3600 / mean dwell of tracks that left a checkout zone after ≥ 20 s (rule R13). There is no POS in the demo, so μ is labelled `estimated_from_video` everywhere it appears; in the pilot a POS CSV importer replaces it. Current estimate: μ ≈ 38 customers per hour per till.

## 4. What is on-shelf availability and how is it measured here?

OSA = 1 − (time a shelf face is in a gap state) / (window). A gap opens when the shelf ROI's empty ratio (Canny edge density + colour variance heuristic, later a trained classifier) exceeds 0.4 for 5 minutes (rule R11) and closes when the signal stops. Store OSA over the last 24 h: 97.3%; per shelf: A1 100.0%, B3 94.5%. Time to restock (mean gap episode): B3 40 min.

## 5. Why deterministic rules plus an LLM agent, not an LLM end-to-end?

Rules are auditable (each event carries its rule id and threshold), cheap (microseconds), and testable (12 synthetic-track tests). A language model on video would be slow, expensive per frame, and impossible to certify for a safety decision. The LLM adds judgement about what to do, and only via seven allow-listed tools with strict schemas. Both backends (DryRun policy table and Claude) go through the same Policy layer, so the model can be swapped without changing what is allowed.

## 6. Which decisions are autonomous and which are proposals, and why?

Autonomous: `send_alert` (templates only), `create_work_order` for severity ≤ 2, `log_downtime`, `escalate` (mandatory on severity 3), `request_human_review` (mandatory below 0.6 confidence). Proposals: `propose_open_till`, `propose_staffing_change`, `propose_maintenance_window`, because they move people or stop machines. In the seeded week the agent took 1 actions (1 autonomous, 0 proposals), 1 tool calls, 0 failed, model cost $0.0.

## 7. How does the workforce MILP work and what did it save?

Minimise Σ tills per slot subject to λ_s / (tills_s · μ) ≤ 0.85 and 1 ≤ tills_s ≤ max, integer; solved with HiGHS via `scipy.optimize.milp`. The problem separates per slot today, but the MILP form lets us add adjacency and minimum-shift constraints without a rewrite (`max_step` is already implemented). One day: 24.25 staff-hours vs 36.0 with three tills open all day, saving 11.75 hours. Over the week the plan peaks at 4 tills with a mean of 1.76.

## 8. How did forecasting perform against the naive baseline?

Hourly footfall, GradientBoostingRegressor with hour, weekday, lag-24, lag-168, rolling means, and a leak-free hour-of-week profile, versus seasonal naive (same hour last week). Seven-day holdout: MAE 4.341 vs 4.917 (11.7% better, MAPE 16.4%). This is on the labelled simulator, which is close to the naive model's assumptions, so the margin understates what real data with promotions and weather would show. The spec target of 20% is a pilot deliverable.

## 9. What would change in a real store with real POS data?

μ becomes exact per till and per hour; basket size and payment method explain service-time variance; λ can be validated against transaction counts; OSA can be cross-checked with sales drop-offs per SKU. The model-vs-observed gap becomes a calibration signal rather than a caveat.

## 10. Privacy and ethics: what leaves the camera?

Events (timestamp, camera, zone, class, confidence, count) and 10-second clips in which every detected person's head band is pixelated and blurred before storage. No face recognition, no cross-camera identity, track ids reset per session. The agent never sees video. Simulated history is flagged in every payload and labelled in the UI.

## 11. What does the pilot cost and what KPIs prove it?

Under USD 50 per month for the software stack (Render small instance, Supabase free, Vercel hobby, Claude API at ~50 actionable events a day) plus an edge box the site already owns. KPIs: service level ≥ 90% of slots, OSA ≥ 98%, false alerts per camera per day < 5, human approval rate ≥ 60%, frame-to-alert latency < 3 s (measured now: 56.1 ms p95 frame-to-event on the edge).

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
| YOLO26n p50 latency / detect fps | 8.9 ms / 111.9 | edge_eval.json |
| RT-DETR-L p50 latency / detect fps | 108.2 ms / 8.9 | edge_eval.json |
| Pipeline fps / frame→event p50 / p95 | 30.5 / 27.7 ms / 56.1 ms | edge_eval.json |
| Service level / OSA / peak ρ (24 h) | 98.9% / 97.3% / 0.95 | kpis_retail.json |
| Forecast MAE / naive / improvement | 4.341 / 4.917 / 11.7% | forecast_retail.json |
| Staff-hours plan / baseline / saved | 24.25 / 36.0 / 11.75 | workforce_retail.json |
| Customer wait before / after / reduction | 1583.2 / 1310.6 / 17.2% | report_retail_en.json |
| Factory compliance / downtime / breaches (24 h) | 100.0% / 3.0 min / 1 | kpis_factory.json |
