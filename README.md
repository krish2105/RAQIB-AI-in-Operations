# RAQIB · رقيب — vision-driven operations control room

**RAQIB** ("the watcher") turns a supermarket's existing cameras into an operations agent: it counts footfall, measures queues and shelf gaps, models the checkout line with queueing theory, forecasts tomorrow's peaks, and proposes or takes bounded actions — every one explained with the frames, the confidence, and the rule that fired. **MUSHRIF** (مشرف, "supervisor") is the factory profile of the same system for the Greenlam Laminates pilot: PPE compliance, exclusion-zone breaches, machine downtime, work orders into the existing tracker.

One engine, two site profiles, three languages (EN / HI / AR), faces blurred before anything is stored.

> Term 4 · MAIB AI 218 *AI in Operations* deployed MVP · Portfolio · Greenlam pilot candidate.
> Owner: Krishna Mathur (`krish2105`). Spec: `docs/superpowers/specs/2026-09-06-raqib-design.md`.

## Live

- **Dashboard:** https://raqib-orcin.vercel.app
- **API:** https://raqib-backend-7qdg.onrender.com (docs at `/docs`)
- **Repo:** https://github.com/krish2105/RAQIB-AI-in-Operations
- **Watch (v2, Phase F):** https://raqib-orcin.vercel.app/en/watch — blurred camera wall with live detection boxes and zone overlays, caption ticker, and VLM second opinions that can request a review but never lower a severity. The live demo has no edge box attached, so tiles show detections only; run `raqib-edge run --stream 8554 --detections 1` on a LAN box and set `STREAM_UPSTREAM` to see the feed.
- **Ask (v2, Phase E):** https://raqib-orcin.vercel.app/en/ask — trilingual questions over events, KPIs and documents with a citation on every fact; `POST /ask` on the API. Model calls run through a zero-cost provider chain (`docs/models.md`); on the free-tier API with no model reachable, answers come from records only and stay cited.

The API is a Render free-tier instance: it sleeps after 15 minutes idle (first request wakes it, ~30–60 s) and runs a single worker, so the weekly report (which aggregates the full seeded history) can take 20–35 s under load — a real free-tier CPU constraint, not a bug; `/kpis`, `/forecast` and `/workforce` are bounded to the window they need and stay fast. A paid instance removes both limits.

## The grader path (under 10 minutes)

1. Open the dashboard → the **tape** across the top shows the last 24 hours of footfall with event ticks; KPIs show service level, on-shelf availability, queue, footfall; the **3D floor** pulses where events land.
2. Click a tick or an event in the stream → the **event page** shows the clip, detection confidence, the rule text, and the agent's decision JSON.
3. Open **Actions** → approve a `propose_open_till` proposal → it executes, the audit table logs the tool call, and restock work orders raised autonomously for shelf gaps appear under *Executed*.
4. Open **Forecast** → next-24h footfall vs seasonal-naive baseline (MAE table), and the **staffing plan** integer program.
5. Open **Report** → the Monday report in English, Hindi, or Arabic. Print to PDF. The "What the records say" section is written by Ask and cites record ids.
6. Open **Watch** → the camera wall (detections only without an edge box), the second-opinion list with agree/disagree and the rule severity that never changes; open any event → the **Second opinion** panel and "Request opinion".
7. Open **Ask** → press `/`, type "Which till had the longest queue last Friday evening?" (or pick an example, in Hindi or Arabic) → a cited answer; click a citation chip to open the event or the SOP section it came from.

## What it does

| | RAQIB (retail) | MUSHRIF (factory) |
|---|---|---|
| **Sees** | person, queue zones, checkout dwell, shelf empty-ratio | person, helmet/vest (fine-tuned weights), exclusion zones, machine ROI motion |
| **Rules** (deterministic, LLM-free) | R10 queue over · R11 shelf gap · R12 footfall · R13 checkout served | R01 no helmet · R02 zone breach · R03 machine stopped · R12 footfall |
| **Learns** | M/M/c model vs observed, GradientBoosting forecast vs seasonal naive, staffing MILP | downtime forecast, compliance trend |
| **Acts** (bounded) | alert, restock work order, *propose* open till (only if ρ > 0.85) | escalate + alert on severity 3, work order into the Greenlam tracker, log downtime, *propose* maintenance window |
| **Explains** | every action carries event id, rule, confidence, ρ, and a written rationale | same |

## Architecture

```
cameras ─► edge/ (Python 3.12, uv)                cloud/ (FastAPI)                     web/ (Next.js 16)
  webcam    capture ─► blur faces ─► YOLO26n ─►    POST /events/batch (idempotent)      the tape · KPIs · 3D floor
  file loop ByteTrack ─► zones ─► rules ─► SQLite  agent: backend ─► Policy ─► tools     event · actions · shelves
  RTSP      clips (10 s) ─► sync (offline queue) ─► M/M/c · OSA · forecast · MILP        forecast · report (EN/HI/AR)
                                                    SSE /stream ─────────────────────►   live, dark/light, RTL
```

- **Edge** (`edge/raqib_edge/`): `Detector` adapter (YOLO26n default, RT-DETR second implementation, swap = one flag), ByteTrack session-scoped ids, polygon zones from site YAML, pure rule functions with injected clock, SQLite outbox, clip ring buffer.
- **Cloud** (`cloud/raqib_api/`): SQLModel tables mirroring the edge `Event`, allow-listed agent tools with strict schemas, `Policy` that cannot be bypassed (severity 3 always escalates, no downgrades, 4-hour work-order cooldown, ρ > 0.85 for till proposals, low confidence → human review), `DryRunBackend` (deterministic) or `ClaudeBackend` (Anthropic tool use), `ops_theory.py` (Erlang-C), `forecast.py`, `workforce.py` (scipy `milp`), weekly report in three languages, labelled simulator.
- **Web** (`web/`): Control Room design — graphite dark first with a "blueprint on paper" light theme, teal signal for retail / hazard amber for factory, IBM Plex (Sans, Arabic, Devanagari, Mono) + Archivo display, the 24-hour tape as the spine of every page, React Three Fiber floor with progressive fallback to SVG.

Full design and decisions: `docs/superpowers/specs/2026-09-06-raqib-design.md`. Diagram: `docs/architecture.md`.

## Run it

Prereqs: Python 3.12 via [uv](https://docs.astral.sh/uv/), Node 20+, ffmpeg. Weights and demo video are not in git — see `docs/datasets.md` for the four files and their licences (`edge/data/weights/yolo26n.pt`, `rtdetr-l.pt`, `edge/data/video/*.mp4`).

```bash
cp .env.example .env                 # all optional for local dev
(cd edge  && uv sync --extra dev --extra train)
(cd cloud && uv sync --extra dev --extra docs)
(cd web   && npm ci)
scripts/dev.sh                       # API :8000 (seeded) + edge loop on the demo clip + web :3000
```

Individually:

```bash
cd edge  && uv run raqib-edge run --site sites/retail_demo.yaml --preview          # boxes, zones, blurred heads
cd edge  && uv run raqib-edge run --site sites/greenlam_unit1.yaml --source webcam --api http://localhost:8000
cd cloud && uv run uvicorn raqib_api.main:app --reload                               # docs at /docs
curl -X POST 'localhost:8000/admin/seed?site=raqib_demo_store&days=21'               # labelled demo history
cd web   && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Docker (edge + API): `docker compose up --build`. Deploy: `render.yaml` (API), `web/vercel.json` (web), `cloud/supabase/schema.sql` (Postgres). Live URLs above.

## Tests

```bash
cd edge  && uv run pytest        # 47: rules with synthetic tracks, adapter on real frames, blur, store, sync, pipeline
cd cloud && uv run pytest        # 44: routers, M/M/c textbook cases, policies (sev-3 cannot be downgraded), tools, forecast beats naive, MILP toy, report EN/HI/AR, session-safe tz normalisation
cd web   && npm test             # 15: severity tokens, message catalogues complete in 3 languages, tape binning, live buffer
cd web   && npm run e2e          # Playwright: event → clip → approve proposal → executed + audit; theme toggle + RTL
```

## Measured results (this machine, `docs/results/`)

All numbers below are read from files produced by `edge/training/eval.py` and `scripts/export_results.py`; nothing is typed by hand.

| Metric | Value | Source |
|---|---|---|
| YOLO26n detect latency, M4 Pro MPS | 8.9 ms p50 · 112 fps detect-only | `edge_eval.json` |
| RT-DETR-L (adapter swap) | 108 ms p50 · 8.9 fps | `edge_eval.json` |
| Frame → event, full pipeline | 27.7 ms p50 · 56 ms p95 · 30.5 fps end-to-end | `edge_eval.json` |
| Forecast MAE vs seasonal naive (footfall, 7-day holdout, simulated history) | 4.34 vs 4.92 (11.7 % better) | `forecast_retail.json` |
| Staffing MILP vs flat 3 tills (one day) | 24.25 vs 36.0 staff-hours (11.75 saved) | `workforce_retail.json` |
| Staffing MILP over the week; customer wait with till proposals applied | 184.0 vs 313.5 staff-hours; wait −17.2 % | `report_retail_en.json` |
| Service level (queue ≤ 3) / store OSA, last 24 h, simulated history | 98.9 % / 97.3 % | `kpis_retail.json` |
| PPE mAP50 | not run — needs SH17 (CC BY-NC-SA, manual download) and fine-tuning | `edge_eval.json` |

The spec targets (mAP50 ≥ 0.80, forecast ≥ 20 % better than naive, zone-breach precision ≥ 0.90, human approval ≥ 60 %) are pilot deliverables that need site footage and ≥ 30 days of real events. The forecast figure above is on the labelled simulator and is reported as such.

### Ask (v2 Phase E)

| Measure | Value | Source |
|---|---|---|
| Embedding choice | bge-m3, recall@5 0.65 on a 20-query trilingual spike (nomic 0.46, ONNX MiniLM 0.47 and 940 MB RSS) | `docs/results/embed_spike.json` |
| Ask eval, 30 cases EN/HI/AR, live local models | recall@5 1.00 · faithfulness 0.93 · citation coverage 1.00 · language match 1.00 · hallucinations 0 | `docs/results/ask_eval.json` |
| Ask latency (M4 Pro, qwen3:8b) | mean 18.1 s, p95 24.0 s, 1488 tokens per query | same |
| Ask on the live API (no model) | 0.2 s, records-only cited answers | measured 2026-09-06 |
| Inference spend | $0 | `docs/models.md` |

### Watch (v2 Phase F)

| Measure | Value | Source |
|---|---|---|
| Blurred MJPEG stream | 10.8 fps at the client (12 fps cap), 960×540 JPEG, head bands blurred before the stream | `docs/results/watch.json` |
| VLM second opinion (qwen2.5vl:7b, 3 keyframes) | 2.7 s warm, 29.6 s cold; agreed 0.9 on a queue clip, disagreed 0.7 when the scene was labelled a PPE violation | same |
| Policy | opinions can request review, never lower severity; tested on a severity-3 event with a suggested severity of 1 | `cloud/tests/test_vlm.py` |

## Term 4 artefacts

`docs/AI218_RAQIB_report.docx`, `docs/AI218_RAQIB_deck.pptx`, `docs/term4_raqib.ipynb`, `docs/viva_qa.md`, `docs/demo_script.md` — generated by `docs/term4/build_*.py` from `docs/results/`.

```bash
python3 scripts/export_results.py                      # pull numbers from the running API
cd cloud && uv run python ../docs/term4/build_docs.py && uv run python ../docs/term4/build_report.py \
         && uv run python ../docs/term4/build_deck.py && uv run python ../docs/term4/build_notebook.py
grep -rEn "TODO|\bXX\b|\[insert" docs --exclude-dir=prompts --exclude-dir=superpowers   # must print nothing
```

## Privacy and governance

- Faces: every detected person's head band is pixelated and blurred in `capture.py` before a frame is drawn, stored in a clip, or sent. No face detector is trusted to find every face; the head band always is.
- No identity recognition. Track ids are per-session integers and never leave as identity.
- The agent never sees video. It receives Events and site context, and may call only the seven allow-listed tools. Severity-3 events always escalate and cannot be downgraded. Every call is logged with input, output, latency, and model cost.
- Simulated history carries `payload.simulated = true` and is labelled in the UI and the report.

## Licences

Ultralytics (YOLO26, RT-DETR checkpoint) is **AGPL-3.0**: fine for this portfolio, the Term 4 submission, and the Greenlam pilot; before commercial sale swap the detector via the adapter or buy an Enterprise licence. SH17, MVTec-AD, MOT17 are CC BY-NC-SA (non-commercial). Pexels demo clips are free to use. Details: `docs/datasets.md`. Project code: MIT.

## Limitations

- Detection quality on a real plant depends on ~2 hours of labelled site footage; COCO weights detect persons only.
- Render free tier sleeps; the edge box buffers and syncs on reconnect (tested). A pilot should use a small paid instance.
- Forecasts need ≥ 14 days of events; the demo uses a labelled simulator.
- μ (service rate) is estimated from checkout dwell on video, not POS. A CSV importer for real POS is the first pilot task.
- Camera placement and lighting matter more than model choice.
- Ask on the live API (Render free tier, no Ollama) answers from SQL filters and BM25 only: the semantic leg needs the same embedding model that indexed the corpus (`bge-m3` on the Mac). A Gemini key lets both sides use `gemini-embedding-001` and restores it; see `docs/models.md`.
- Answer latency with local models is 9–20 s per question on an M4 Pro; the UI streams the stages so the wait is visible, not silent.
