# RAQIB — Term 4 Kickoff Prompt (MAIB AI 218: AI in Operations)

> Companion to `RAQIB-master-prompt.md`. Paste this into Claude Code **after** the master prompt, in the same session, once Phase 1 of RAQIB is green.
> Workspace: `~/Desktop/MAIB-Term4` · Repo: `krish2105/RAQIB-AI-in-Operations` · Toolchain: uv, pytest, ruff · Solo project.

**Decision baked into this doc:** RAQIB replaces MASAR as the AI 218 deployed MVP. MASAR has not been started; RAQIB is already being built for portfolio and startup, so one build now serves three goals. If you later want MASAR too, it becomes an optional extension, not a requirement.

---

## 0. Grading context (drive every decision)

Term 4 internals are 60% and reward: a **live, deployed, end-to-end MVP**, a **professional presentation**, quizzes and participation. So the course deliverables are not a separate notebook — they are the deployed RAQIB app plus a report and deck that explain it in operations-management language. Every artefact below must map to something a grader can click, run, or read in under 10 minutes.

---

## 1. Academic framing to add on top of the build

RAQIB is a supermarket operations control system. Frame it with the operations theory the course expects, and compute these from RAQIB's own data:

| Ops concept | How RAQIB implements it | Where it appears |
|---|---|---|
| Queueing theory (M/M/c) | Arrival rate λ from entrance footfall, service rate μ from POS transactions per open till; compute expected wait W_q and utilisation ρ per 15-min slot; compare to measured queue length | `cloud/raqib_api/ops_theory.py`, dashboard "Queue model vs observed" card |
| Capacity planning | Agent's `propose_open_till` justified by ρ > 0.85 threshold, not just a count | Agent prompt + report |
| Service level | % of 15-min slots with queue ≤ 3; target 90% | KPI on dashboard |
| Inventory availability / OSA | Shelf availability % (on-shelf availability) per shelf and store; time-to-restock | Shelves page, weekly report |
| Forecasting & demand planning | Queue-peak and shelf-out forecasts, MAE vs seasonal naive | Forecast page + notebook |
| Workforce scheduling | Weekly staffing proposal as a small integer program (min staff-hours s.t. ρ ≤ 0.85 in every slot) using `scipy.optimize.milp` | `workforce.py`, report |
| Continuous improvement | Before/after comparison: simulated week with agent proposals applied vs baseline | Report Section 6 |

Add `ops_theory.py` and `workforce.py` as small, tested modules. No new services.

---

## 2. Deliverables checklist (what to submit)

1. **Live MVP** — RAQIB dashboard on Vercel with the edge pipeline running on looped public video and the API on Render. Grader path: open link → see live KPIs → open one event clip → approve one agent proposal → see restock task.
2. **Repo** `krish2105/RAQIB-AI-in-Operations` with README (problem, ops framing, architecture diagram, how to run, licences, limitations).
3. **Report** `docs/AI218_RAQIB_report.docx` (10–12 pages) — structure in Section 3.
4. **Deck** `docs/AI218_RAQIB_deck.pptx` (12 slides) — structure in Section 4.
5. **Notebook** `docs/term4_raqib.ipynb` — forecasting, queueing model validation, workforce optimisation, with plots.
6. **Demo video** 3 minutes, narrated, EN.
7. **Viva sheet** `docs/viva_qa.md` — 15 questions and answers (Section 6).

Generate the .docx and .pptx with Claude Code using python-docx and python-pptx; no placeholders — pull numbers from `eval.py` output and the notebook.

---

## 3. Report structure (write it, do not outline it)

1. Executive summary (half page): problem, solution, three measured results.
2. Problem and operations context: hypermarket floor ops, cost of queues and shelf-outs, why cameras are an untapped sensor.
3. Literature and practice (1 page): queue management systems, on-shelf availability studies, computer vision in retail; 6–8 citations, real and verifiable, in APA.
4. System design: architecture diagram, edge/cloud split, deterministic rules vs bounded agent, privacy design.
5. Data and models: datasets with licences, detector and shelf-model training, evaluation tables.
6. Operations analytics: M/M/c model vs observed, service level, OSA, forecasts vs baseline, workforce optimisation result, before/after simulation.
7. Agent design and governance: tools, policies, what is autonomous vs proposed, logging, cost.
8. Deployment: Vercel/Render/Supabase, offline behaviour, monitoring.
9. Limitations and ethics: public video not a store, sample POS, AGPL, privacy.
10. Business case and rollout: pilot scope for one Dubai hypermarket, KPIs, 90-day plan.
11. Conclusion and future work.
Appendix: site YAML, rule table, tool schemas, test coverage summary.

---

## 4. Deck (12 slides)

1 Title · 2 The problem in one picture (queue photo + shelf gap) · 3 What RAQIB does (sees/learns/acts/explains) · 4 Architecture · 5 Live demo slide (screenshot + link + QR) · 6 Detection and shelf results · 7 Queue model vs observed · 8 Forecast vs baseline · 9 Workforce optimisation · 10 Agent governance · 11 Business case for a Dubai hypermarket · 12 Limitations, next steps, thank you.

Design: dark, one idea per slide, numbers large, no bullet walls. Speaker notes for every slide (Krishna is a trained anchor — write notes as talking points, not scripts).

---

## 5. Build additions and order (fits inside the RAQIB phases)

- After RAQIB Phase 2: add `ops_theory.py` (λ, μ, ρ, W_q per slot) with tests against hand-computed M/M/c examples.
- After Phase 6: add `workforce.py` (MILP) with a test on a 3-till toy problem; extend the notebook with model-vs-observed and optimisation sections.
- After Phase 7: generate report, deck, viva sheet, demo video script; run `eval.py` and inject real numbers.
- Final check: every number in report and deck traces to a file in `docs/results/`. Fail the build if any placeholder remains (`grep -r "TODO\|XX\|\[insert" docs/` must return nothing).

---

## 6. Viva Q&A (write full answers in `docs/viva_qa.md`)

1. Why is this an *operations* project and not a computer-vision project?
2. Explain M/M/c and why you chose it; what assumptions does it violate here?
3. How did you estimate arrival and service rates from video and POS?
4. What is on-shelf availability and how is it measured here?
5. Why deterministic rules plus an LLM agent, not an LLM end-to-end?
6. Which decisions are autonomous and which are proposals, and why?
7. How does the workforce MILP work and what did it save?
8. How did forecasting perform against the naive baseline?
9. What would change in a real store with real POS data?
10. Privacy and ethics: what leaves the camera?
11. What does the pilot cost and what KPIs prove it?
12. Biggest technical risk and biggest business risk?
13. How is RAQIB different from existing queue-management vendors?
14. What did you learn about operations management from building it?
15. If you had one more month, what would you build?

---

## 7. First instruction to Claude Code (this doc)

"Read this kickoff document alongside the RAQIB master prompt. Confirm RAQIB Phase 1 is green. Print the list of additions from Section 5 mapped to the RAQIB phase they attach to, with a verifiable check for each, and state any assumption about POS data or course rubric. Then wait for my 'go'."
