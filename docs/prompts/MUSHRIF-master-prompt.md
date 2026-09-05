# MUSHRIF — Master Build Prompt for Claude Code
### Vision-driven operations agent for factories and retail floors (RAQIB = retail profile of the same system)

> Paste everything below the line into a fresh Claude Code session inside an empty repo `mushrif`.
> Owner: Krishna Mathur · GitHub: krish2105 · Dev machine: MacBook Pro M4 Pro · First pilot site: one Greenlam Laminates plant unit (existing [[greenlam-tracker]] project supplies the work-order backend).

---

## 0. How to work in this repo

1. **Plan, then build.** Before each phase print a numbered plan with a verifiable check per step. Wait for "go" at phase boundaries only.
2. **Simplest thing that works.** No speculative abstraction. One model, one queue, one DB until a test proves we need more.
3. **Tests define done.** `pytest` for Python, `vitest` for the web app. Every phase ends green plus a one-paragraph verification note.
4. **State assumptions out loud.** Camera formats, dataset licences, frame rates — write them in comments and in your reply.
5. **Secrets via env only.** Never printed, never committed.
6. **Licences matter.** Ultralytics YOLO is AGPL-3.0; that is acceptable for a portfolio/pilot but must be stated in README. If a paying customer appears, swap to RT-DETR (Apache-2.0) via the model adapter in Section 4.3 — the adapter exists for exactly this reason.
7. **Privacy by default.** Faces are blurred at ingestion. No identity recognition, ever. Only counts, positions, classes, and events leave the edge box.

---

## 1. Problem statement

Factories and retail floors already have cameras, but the cameras only record. Nobody watches 40 feeds. Safety violations (no helmet, no vest, person inside a machine exclusion zone) are found after an incident; machine stoppages are logged by hand hours later; retail managers guess at footfall and queue length.

MUSHRIF turns existing cameras into an operations agent:

- **Sees**: PPE compliance, exclusion-zone breaches, machine running/idle/stopped state, footfall, queue length, shelf gaps.
- **Learns**: forecasts stoppages and queue peaks from the last 30 days of events.
- **Acts**: raises work orders (into the Greenlam tracker), proposes shift/staffing changes, sends bilingual (Hindi/English/Arabic) alerts, and escalates to a human with a clip attached.
- **Explains**: every action carries the frames, the model confidence, and the rule that fired.

Two site profiles ship from day one on the same pipeline:

| Profile | Detections | Agent actions |
|---|---|---|
| `factory` (MUSHRIF) | helmet, vest, person, exclusion zone, machine state | safety alert, work order, downtime log, shift note |
| `retail` (RAQIB) | person, queue region, shelf region, checkout | footfall heatmap, queue alert, restock task, staffing suggestion |

Goals: portfolio piece, Term 4 AI-in-Operations submission, and a real pilot at Greenlam that can become a product.

---

## 2. Tech stack (verified free / already owned)

| Layer | Choice | Notes |
|---|---|---|
| Edge inference | Python 3.12, PyTorch with MPS on the M4 Pro (dev) → same code on any Linux box/Jetson (pilot) | Export to CoreML/ONNX in Phase 6 |
| Detection | Ultralytics YOLOv8/11 (dev) behind a `Detector` adapter; RT-DETR as second implementation | Adapter = 1 file, 2 methods |
| Tracking | ByteTrack (bundled with Ultralytics) | IDs are per-session only, never persisted |
| Anomaly / machine state | Lightweight classifier on cropped machine ROI; MVTec-AD used for dev tests | Real plant crops replace it in pilot |
| Forecasting | scikit-learn GradientBoosting on hourly event counts; Prophet optional | Term 4 AI-in-Ops deliverable |
| Agent layer | Anthropic Python SDK, tool-use with a strict tool allow-list (Section 5) | Model: `claude-sonnet-4-6` for routine, Opus for weekly report |
| Event bus | SQLite on edge → Supabase Postgres in cloud (Krishna's existing account) | Offline-first, sync when online |
| API | FastAPI on Render free tier | Same host style as Greenlam tracker |
| Web app | Next.js 15, React 19, Tailwind, Motion, React Three Fiber for the 3D floor plan, Recharts | Deployed on Vercel |
| Mobile alerts | PWA push + WhatsApp Cloud API (free tier) | Hindi/English/Arabic templates |
| Tests | pytest, vitest, Playwright for one smoke flow | |

Secrets: `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `WHATSAPP_TOKEN` (optional).

---

## 3. Real data sources (no mocks in the final demo)

**Live cameras**
- Dev: iPhone as an RTSP/HTTP camera (any free "IP camera" app) pointed at a desk mock-up; plus the Mac webcam.
- Pilot: the plant's existing CCTV via RTSP. Ask the Greenlam site engineer for one camera URL and one machine to start. Record 2 hours of footage with permission for the labelled set.

**Public datasets for training/eval (state licence in README)**
- PPE: Roboflow "Hard Hat Workers" / construction-safety datasets; SH17 (safety equipment, 17 classes).
- Anomaly / machine state: MVTec-AD for unit tests; plant crops for real training.
- Tracking/footfall: MOT17/MOT20 for tracker tests.
- Retail: any CC-licensed retail-store video from Roboflow Universe for queue and shelf-gap evaluation.

**Business data**
- Greenlam tracker API (existing): machines, tickets, production logs — MUSHRIF writes tickets *into* it, never duplicates its schema.
- Shift roster: CSV upload in Phase 5.

Rule: if a public dataset is unreachable, the run fails loudly with the dataset name and licence URL. No silent synthetic fallback.

---

## 4. Architecture

```
mushrif/
├── edge/                         # runs next to the cameras
│   ├── mushrif_edge/
│   │   ├── capture.py            # RTSP/webcam → frames (OpenCV), face blur here
│   │   ├── detectors/
│   │   │   ├── base.py           # Detector adapter: load(), detect(frame) -> list[Det]
│   │   │   ├── yolo.py
│   │   │   └── rtdetr.py
│   │   ├── track.py              # ByteTrack wrapper → tracks
│   │   ├── zones.py              # polygon zones from site config (exclusion, queue, shelf)
│   │   ├── rules.py              # rule engine: detections+zones → Events (deterministic)
│   │   ├── machine_state.py      # ROI classifier: running/idle/stopped
│   │   ├── store.py              # SQLite event log + clip writer (10 s around each event)
│   │   ├── sync.py               # push events/clips to Supabase when online
│   │   └── main.py               # CLI: mushrif-edge run --site sites/greenlam_unit1.yaml
│   ├── sites/
│   │   ├── greenlam_unit1.yaml   # cameras, zones, machines, thresholds
│   │   └── retail_demo.yaml
│   ├── training/
│   │   ├── prepare_data.py       # download + split datasets, record licence
│   │   ├── train_ppe.py
│   │   ├── train_machine_state.py
│   │   └── eval.py               # mAP, per-class precision/recall, latency table
│   └── tests/
├── cloud/                        # FastAPI on Render
│   ├── mushrif_api/
│   │   ├── main.py
│   │   ├── models.py             # SQLModel: Site, Camera, Zone, Event, Clip, Action, Forecast
│   │   ├── routers/{events,actions,forecast,report}.py
│   │   ├── agent/
│   │   │   ├── tools.py          # allow-listed tools (Section 5)
│   │   │   ├── policies.py       # what the agent may do alone vs must escalate
│   │   │   ├── ops_agent.py      # per-event reasoning loop
│   │   │   └── weekly_agent.py   # Monday 07:00 report + staffing/maintenance plan
│   │   ├── forecast.py           # hourly event-count models per machine/zone
│   │   └── notify.py             # PWA push + WhatsApp, trilingual templates
│   └── tests/
├── web/                          # Next.js on Vercel
│   ├── app/
│   │   ├── (dashboard)/page.tsx          # live KPIs, event stream
│   │   ├── floor/page.tsx                # R3F 3D floor plan with live overlays
│   │   ├── events/[id]/page.tsx          # clip, frames, confidence, rule, agent decision
│   │   ├── actions/page.tsx              # approve / reject agent proposals
│   │   └── report/page.tsx               # weekly report, exportable PDF
│   ├── components/
│   └── tests/
├── docs/                         # architecture, dataset licences, pilot SOP, Term 4 write-up
├── CLAUDE.md
├── README.md
└── docker-compose.yml            # edge + api locally
```

### 4.1 Event model (single source of truth)

```python
@dataclass
class Event:
    id: str
    site: str
    camera: str
    ts: datetime
    kind: str          # "ppe_violation" | "zone_breach" | "machine_stopped" | "queue_over" | "shelf_gap" | "footfall_tick"
    severity: int      # 1 info, 2 warn, 3 critical
    payload: dict      # class, confidence, zone, track_id (session-only), count, machine_id
    clip_path: str | None
    rule_id: str       # which rule in rules.py fired
```

### 4.2 Rule engine (deterministic, no LLM)

Examples in `rules.py`, each a pure function `(tracks, zones, state) -> list[Event]`:
- `R01_no_helmet`: person track inside `work_area` zone with no helmet box overlapping head region for ≥ 2 s → severity 3.
- `R02_zone_breach`: person centroid inside `exclusion` zone → severity 3, immediate.
- `R03_machine_stopped`: machine_state == stopped for ≥ 120 s during scheduled run → severity 2.
- `R10_queue_over`: ≥ N persons inside `queue` zone for ≥ 60 s → severity 2 (retail).
- `R11_shelf_gap`: shelf ROI empty-ratio > 0.4 for ≥ 5 min → severity 1 (retail).

Thresholds live in the site YAML. Rules are unit-tested with synthetic track lists.

### 4.3 Detector adapter

```python
class Detector(Protocol):
    def load(self, weights: str, device: str) -> None: ...
    def detect(self, frame: np.ndarray) -> list[Det]: ...   # Det(cls, conf, xyxy)
```
Swapping YOLO ↔ RT-DETR must require zero changes outside `detectors/`.

---

## 5. Agent layer — bounded autonomy

The agent never sees raw video. It receives Events, site context, and recent history, and can call only these tools:

| Tool | Autonomous? | Notes |
|---|---|---|
| `create_work_order(machine_id, summary, severity)` | Yes, severity ≤ 2 | Calls Greenlam tracker API |
| `send_alert(channel, lang, template, vars)` | Yes | Trilingual templates only, no free text to WhatsApp |
| `log_downtime(machine_id, start, end, reason)` | Yes | |
| `propose_staffing_change(zone, delta, window)` | Proposal only | Human approves in `/actions` |
| `propose_maintenance_window(machine_id, window)` | Proposal only | |
| `escalate(event_id, to_role, note)` | Yes, severity 3 | Always attaches clip |
| `request_human_review(event_id, question)` | Yes | Used when confidence < 0.6 |

Policies in `policies.py`: severity-3 events always escalate to a human *and* alert; the agent may not suppress or downgrade a severity-3 event; the same machine gets at most one work order per 4 hours unless a human overrides.

Prompt files: `prompts/ops_agent.md` (per event: decide action, cite rule and confidence, output strict JSON tool calls) and `prompts/weekly_agent.md` (Monday: read 7 days of events and forecasts, produce a bilingual report with 3 recommended actions, each with expected downtime/queue reduction).

Safety: every prompt input is wrapped as untrusted data; tool schemas are strict; tool-call arguments are validated before execution. Log every call with input, output, and cost.

---

## 6. Forecasting (Term 4 AI-in-Operations deliverable)

- Aggregate events hourly per machine/zone.
- Features: hour, weekday, shift, last-24h counts, production volume from Greenlam tracker.
- Model: GradientBoostingRegressor baseline vs seasonal naive; report MAE and MAPE on the last 7 days.
- Outputs: next-24h stoppage risk per machine, next-day queue-peak windows per zone.
- Deliver a notebook `docs/term4_forecasting.ipynb` with plots, plus the same logic in `forecast.py`.

---

## 7. Web app (premium, but functional first)

- **Dashboard**: live KPIs (compliance %, downtime today, footfall/hour, avg queue), event stream with severity colours, one-click "open clip".
- **3D floor**: R3F scene from a simple floor-plan JSON; cameras, zones, and machines as meshes; live event pulses at their location; hover shows last event. Keep it under 60 fps on a phone — instanced meshes, no post-processing.
- **Event detail**: clip player, detection overlay, confidence, rule text, the agent's JSON decision, approve/override buttons.
- **Actions**: queue of agent proposals with reasoning; approve triggers the tool for real.
- **Report**: weekly bilingual report, export to PDF.
- Motion: subtle; page transitions and KPI count-ups only. No decorative animation on the event stream.
- Languages: EN, HI, AR (RTL) via `next-intl`.

---

## 8. Build phases (20+ hrs/week → about 8 weeks)

**Phase 1 — Edge capture and detection (week 1).** `capture.py` with webcam + RTSP, face blur, `Detector` adapter with YOLO, `Det` tests on 5 fixture frames. Verify: `mushrif-edge run --site sites/retail_demo.yaml --preview` shows boxes live at ≥ 15 fps on the M4 Pro.

**Phase 2 — Zones, tracking, rules, local store (week 2).** ByteTrack, polygon zones, rules R01–R03 and R10–R11, SQLite store, clip writer. Verify: synthetic-track unit tests pass; walking into a taped "exclusion zone" on the desk mock-up produces a severity-3 event with a 10 s clip.

**Phase 3 — Training and evaluation (week 3).** `prepare_data.py` downloads PPE + MVTec, records licences; `train_ppe.py` fine-tunes; `eval.py` outputs mAP table and latency. Verify: PPE model ≥ 0.80 mAP50 on held-out set; machine-state classifier ≥ 0.90 accuracy on MVTec proxy.

**Phase 4 — Cloud API and sync (week 4).** FastAPI models and routers, Supabase schema, `sync.py` with offline queue. Verify: kill Wi-Fi for 5 minutes, events still captured, all synced within 30 s of reconnect.

**Phase 5 — Agent layer (week 5).** Tools, policies, ops agent, notify with trilingual templates, Greenlam tracker integration. Verify: a machine_stopped event creates a real work order in the tracker sandbox; a severity-3 event cannot be suppressed (test asserts).

**Phase 6 — Forecasting + weekly agent (week 6).** `forecast.py`, notebook, weekly report generator. Verify: MAE beats seasonal naive on 7-day holdout; Monday report renders in EN/HI/AR.

**Phase 7 — Web app (week 7).** Dashboard, 3D floor, event detail, actions, report. Verify: Playwright smoke: event appears → open clip → approve proposal → work order visible.

**Phase 8 — Pilot hardening (week 8).** CoreML/ONNX export, Docker for edge, health checks, cost dashboard, pilot SOP in `docs/pilot_sop.md`, privacy notice, demo video. Verify: 24-hour unattended run on one real camera with zero crashes.

---

## 9. CLAUDE.md (write into the repo)

```
# MUSHRIF project rules
- Python 3.12 (edge, cloud), Node 20 (web). ruff + pytest; eslint + vitest.
- Faces are blurred in capture.py before any frame is stored or sent. Never remove this.
- No identity recognition, no track IDs persisted across sessions.
- Rules engine is deterministic and LLM-free. The agent acts on Events only.
- Every agent tool call is validated against its schema and logged with cost.
- Severity-3 events always escalate; the agent cannot downgrade them.
- Detector implementations live only in edge/mushrif_edge/detectors/.
- Dataset licences are recorded in docs/datasets.md on download.
- Secrets via env only.
```

---

## 10. Expected output (end of Phase 8)

- Edge box running on one Greenlam camera, events flowing to Supabase.
- Live dashboard at `mushrif.vercel.app` with the 3D floor showing real events.
- At least one real work order created by the agent and approved by a human.
- Eval report: PPE mAP, machine-state accuracy, forecast MAE vs baseline, end-to-end latency (frame → alert) under 3 s.
- Weekly bilingual ops report PDF.
- 2-minute demo video: violation on camera → alert on phone → work order in tracker → forecast on dashboard.

---

## 11. Evaluation

| Metric | Target |
|---|---|
| PPE detection mAP50 (held-out) | ≥ 0.80 |
| Zone-breach precision (manual review of 50 events) | ≥ 0.90 |
| Machine-state accuracy (plant crops) | ≥ 0.85 |
| Frame → alert latency | < 3 s |
| Forecast MAE vs seasonal naive | ≥ 20% better |
| False alerts per camera per day (after tuning) | < 5 |
| Human approval rate of agent proposals | ≥ 60% |

---

## 12. Limitations (say them plainly)

- Detection quality on the real plant depends on labelling ~2 hours of site footage; public datasets alone will not reach the targets.
- Free-tier Render sleeps; the edge box must buffer. Pilot should move to a small paid instance.
- Ultralytics AGPL licence must be replaced before commercial sale.
- Forecasts need ≥ 30 days of events to be meaningful.
- Camera placement and lighting matter more than model choice.

---

## 13. Future improvements

1. Multi-camera re-identification without identity (colour/geometry embeddings, session-scoped).
2. Edge-only mode with on-device LLM for sites with no internet.
3. Digital-twin playback: scrub a day on the 3D floor.
4. Retail: shelf planogram compliance and price-tag OCR.
5. Multi-plant rollout matching the Greenlam tracker roadmap.

---

## 14. Viva / interview Q&A

**Why a deterministic rule engine plus an LLM agent, not an LLM on video?** Rules give auditable, cheap, low-latency safety decisions; the LLM adds judgement on what to *do* about them. Separating the two is what makes the system explainable and testable.

**How do you prevent the agent from causing harm?** Allow-listed tools with strict schemas, severity-3 cannot be suppressed, proposals for anything that changes staffing, full logging. Bounded autonomy, not blind autonomy.

**Privacy?** Faces blurred at capture, no identity recognition, track IDs never persist. Only counts and events leave the edge.

**What did the forecasting show?** Answer from the Phase 6 MAE table and the notebook plots.

**Why not a cloud vision API?** Latency, cost per frame, and privacy. Edge inference on a $200 box beats streaming 40 cameras to the cloud.

**Biggest risk?** Data. The model is only as good as the two hours of site footage you label in week 3.

---

## 15. What to submit / show

- Repo with README (problem, architecture diagram, dataset licences, how to run edge + cloud + web).
- Live dashboard link and demo video.
- Eval report and forecasting notebook (Term 4 AI-in-Operations).
- Pilot SOP and privacy notice (shows product thinking for the Greenlam rollout).
- One-page "MUSHRIF for Greenlam" proposal: cost of a pilot box, expected downtime reduction, rollout plan.

---

## First instruction to Claude Code

"Read this whole document. Confirm the dev environment (Python 3.12, PyTorch MPS available, Node 20). Print your Phase 1 plan with a verifiable check per step and list every assumption you are making about cameras and datasets. Then wait for my 'go'."
