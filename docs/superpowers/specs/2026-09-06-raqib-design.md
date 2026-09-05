# RAQIB / MUSHRIF — Design Spec

Date: 2026-09-06 · Owner: Krishna Mathur · Status: approved by owner in session

RAQIB ("the watcher") turns a supermarket's existing cameras into an operations control room. MUSHRIF is the factory profile of the same system for the Greenlam Laminates pilot. One engine, two site profiles. RAQIB leads because it is the graded Term 4 (AI 218, AI in Operations) MVP.

Source briefs: `docs/prompts/MUSHRIF-master-prompt.md`, `docs/prompts/RAQIB-Term4-kickoff.md`. This spec resolves the decisions those briefs left open and is the contract for the implementation plan.

## 1. Decisions taken

| Question | Decision |
|---|---|
| Scope of first build | Full stack runnable locally: edge, cloud API, agent, forecasting, web. Deploy at the end. |
| Lead profile | RAQIB retail. MUSHRIF factory is a site-profile switch (`profile: retail | factory` in site YAML). |
| Deployment | Supabase (new project) + Render (API) + Vercel (web) after tests are green; each outward step confirmed by owner first. |
| LLM | Anthropic SDK behind an `AgentBackend` interface. No key yet, so `DryRunBackend` (deterministic policy table) is default; `ClaudeBackend` activates when `ANTHROPIC_API_KEY` is set. |
| Visual direction | "Control Room" (Section 6). Light/dark toggle. EN / HI / AR with RTL. |
| Repo | `~/Desktop/MUSHRIF` is the repo root. GitHub remote `krish2105/RAQIB-AI-in-Operations` created only on confirmation. |
| Demo camera | Mac webcam and two looped Pexels CC0 clips (ids 39221979, 854634). |
| Datasets | SH17 (CC BY-NC-SA 4.0, Kaggle) and MVTec-AD need manual download; `prepare_data.py` fails loudly with URL and licence when missing. Tests use synthetic tracks and fixture frames, never silent synthetic fallback in the demo. |
| POS data | Not available. Service rate μ is estimated from checkout-zone dwell; the UI and report label it "estimated from video". A CSV importer accepts real POS later. |

## 2. Non-negotiable rules (go into CLAUDE.md)

- Faces blurred in `capture.py` before any frame is stored or sent. Never removed.
- No identity recognition. Track IDs are per-session and never persisted.
- Rules engine is deterministic and LLM-free. The agent acts on Events only.
- Every agent tool call is validated against its schema and logged with cost.
- Severity-3 events always escalate; the agent cannot suppress or downgrade them.
- Detector implementations live only in `edge/raqib_edge/detectors/`.
- Dataset licences recorded in `docs/datasets.md` at download time.
- Secrets via env only. Ultralytics is AGPL-3.0; stated in README; RT-DETR adapter exists for the commercial swap.

## 3. Repository layout

```
MUSHRIF/                          (repo root, GitHub name RAQIB-AI-in-Operations)
├── edge/                         Python 3.12, uv, runs next to cameras
│   ├── raqib_edge/
│   │   ├── capture.py            webcam | file loop | RTSP → frames; face blur
│   │   ├── detectors/{base,yolo,rtdetr}.py
│   │   ├── track.py              ByteTrack via ultralytics; session-scoped ids
│   │   ├── zones.py              polygon zones from site YAML
│   │   ├── rules.py              R01-R03 factory, R10-R12 retail; pure functions
│   │   ├── shelf.py              shelf ROI empty-ratio estimator
│   │   ├── machine_state.py      ROI classifier running/idle/stopped
│   │   ├── events.py             Event dataclass (single source of truth)
│   │   ├── store.py              SQLite event log + clip ring buffer writer
│   │   ├── sync.py               offline queue → POST /events, /clips
│   │   ├── preview.py            OpenCV overlay window
│   │   └── main.py               CLI: raqib-edge run --site sites/retail_demo.yaml [--preview] [--source webcam|file]
│   ├── sites/{retail_demo,greenlam_unit1}.yaml
│   ├── training/{prepare_data,train_ppe,train_shelf,eval}.py
│   ├── data/{video,weights,clips,datasets}/   (gitignored)
│   └── tests/
├── cloud/                        FastAPI, SQLModel, Python 3.12
│   ├── raqib_api/
│   │   ├── main.py, db.py, config.py
│   │   ├── models.py             Site, Camera, Zone, Event, Clip, Action, Forecast, ToolCall
│   │   ├── routers/{events,actions,forecast,report,sites,stream,health}.py
│   │   ├── agent/{tools,policies,backends,ops_agent,weekly_agent}.py
│   │   ├── prompts/{ops_agent,weekly_agent}.md
│   │   ├── ops_theory.py         M/M/c: λ, μ, ρ, Wq, Lq per slot
│   │   ├── workforce.py          MILP staffing via scipy.optimize.milp
│   │   ├── forecast.py           GBR vs seasonal naive, MAE/MAPE
│   │   ├── greenlam.py           work-order client for the tracker API
│   │   ├── notify.py             trilingual templates; console + webhook sinks
│   │   └── simulate.py           replay/seed generator for demo and tests (labelled)
│   └── tests/
├── web/                          Next.js 16, React 19, Tailwind 4, Motion, R3F
│   ├── app/[locale]/(console)/{page,floor,events/[id],actions,shelves,forecast,report}/
│   ├── components/{tape,floor,kpi,stream,...}
│   ├── lib/{api,i18n,theme,profile}
│   ├── messages/{en,hi,ar}.json
│   └── tests/ (vitest) + e2e/ (playwright)
├── docs/                         architecture, datasets, pilot SOP, Term 4 artefacts
├── scripts/dev.sh                one command: api + edge(file loop) + web
├── docker-compose.yml            edge + api
├── CLAUDE.md, README.md, render.yaml, vercel.json
```

Package names: `raqib_edge`, `raqib_api`. The word MUSHRIF appears as the factory profile name, not as a package.

## 4. Data model

`Event` is the single source of truth, identical shape on edge (dataclass) and cloud (SQLModel):

```
id: str (ulid)   site: str   camera: str   ts: datetime (UTC)
kind: ppe_violation | zone_breach | machine_stopped | queue_over | shelf_gap | footfall_tick | checkout_served
severity: 1 info | 2 warn | 3 critical
payload: dict   (class, confidence, zone, track_id session-only, count, machine_id, shelf_id, dwell_s)
clip_path: str | None
rule_id: str    (R01 … R12)
```

Cloud adds: `Action` (agent proposal or executed tool: kind, args, status proposed|approved|rejected|executed, reasoning, event_id), `ToolCall` (input, output, cost_usd, latency_ms, backend), `Forecast` (target, horizon, ts, value, baseline_value), `Site`, `Camera`, `Zone` (polygon in floor-plan metres), `Clip`.

Rules and thresholds:

| Rule | Profile | Condition | Severity |
|---|---|---|---|
| R01_no_helmet | factory | person in `work_area` with no helmet box over head region ≥ 2 s | 3 |
| R02_zone_breach | factory | person centroid inside `exclusion` | 3 |
| R03_machine_stopped | factory | machine_state stopped ≥ 120 s in scheduled run | 2 |
| R10_queue_over | retail | ≥ N persons in `queue` zone ≥ 60 s | 2 |
| R11_shelf_gap | retail | shelf ROI empty-ratio > 0.4 for ≥ 5 min | 1 |
| R12_footfall_tick | both | person track crosses `entrance` line, emitted per crossing | 1 |
| R13_checkout_served | retail | track leaves `checkout` zone after dwell ≥ 20 s (μ estimator) | 1 |

Thresholds live in site YAML. Time in rules is injected (no wall-clock inside pure functions).

## 5. Agent layer

Tools (strict JSON schemas, validated before execution, all logged):

| Tool | Autonomy |
|---|---|
| create_work_order(machine_id, summary, severity) | autonomous ≤ severity 2, via Greenlam client (retail: restock task uses the same tool with `machine_id = shelf_id`) |
| send_alert(channel, lang, template, vars) | autonomous; templates only |
| log_downtime(machine_id, start, end, reason) | autonomous |
| propose_staffing_change(zone, delta, window) / propose_open_till(till, window, rho) | proposal, human approves in /actions |
| propose_maintenance_window(machine_id, window) | proposal |
| escalate(event_id, to_role, note) | autonomous on severity 3, clip attached |
| request_human_review(event_id, question) | autonomous when confidence < 0.6 |

Policies (`policies.py`, tested): severity 3 always escalates and alerts; agent cannot suppress or downgrade; max one work order per machine/shelf per 4 h unless human override; `propose_open_till` must cite ρ > 0.85 from `ops_theory`.

Backends: `DryRunBackend` maps (kind, severity, confidence, ρ) → tool calls with a written rationale, so the pipeline is demonstrable without a key. `ClaudeBackend` uses `claude-sonnet-4-6` per event and Opus for the weekly report with the same tool schemas; prompt inputs wrapped as untrusted data. Weekly agent produces EN/HI/AR report with three recommended actions and expected reduction.

## 6. Web app design — "Control Room"

Audience: a store operations manager on a wall screen or laptop, and a grader who has ten minutes. The page's job: show what the watcher sees right now and what it proposes to do.

Tokens (CSS variables, semantic, both themes defined together):

| Token | Dark | Light ("blueprint on paper") |
|---|---|---|
| ground | #0B0D10 | #F4F5F2 |
| surface | #12151A | #FFFFFF |
| surface-raised | #1A1F26 | #EEF0EC |
| hairline | rgba(255,255,255,.07) | rgba(20,24,29,.10) |
| ink | #E8EAED | #14181D |
| ink-muted | #8B93A1 | #5B6472 |
| signal (retail) | #1FD1B9 | #0F9E8E |
| signal (factory) | #FFB020 | #B87400 |
| critical | #FF4D3D | #C8291B |
| warn | #F5B700 | #A67A00 |
| info | #6E8DB5 | #4A6690 |

Severity is always colour + icon + label. Contrast checked to WCAG AA in both themes.

Type: IBM Plex Sans (EN), IBM Plex Sans Arabic (AR), IBM Plex Sans Devanagari (HI), IBM Plex Mono with tabular numerals for every figure. Archivo (variable width) for English display headings: narrow uppercase eyebrows, expanded for the hero KPI. Base 16 px, scale 12/14/16/20/28/40/64.

Layout: left rail (icon + label, 72 px collapsed, 220 px expanded), top region is the tape, content is a dense 12-column bento grid with 8 px rhythm.

Signature element, "the tape": a full-width 24-hour strip chart that sits under the header on every page. Footfall per 5-min bin is the trace (Canvas), events are ticks coloured by severity, the playhead marks now, hovering scrubs, clicking a tick navigates to the event. It is the spine of the product: what a watcher records.

Pages:

1. Dashboard `/`: KPI row (service level %, on-shelf availability %, avg queue, footfall/hour; factory: compliance %, downtime today, footfall/hour, stopped machines), 3D floor hero (R3F, instanced zone meshes, pulses at event locations, hover = last event), event stream (severity colours, open clip), "Queue model vs observed" card (M/M/c W_q vs measured), agent proposals preview.
2. Floor `/floor`: full-screen 3D floor with time scrub bound to the tape.
3. Event `/events/[id]`: clip player with detection overlay, confidence, rule text, agent JSON decision, approve/override.
4. Actions `/actions`: proposals queue with reasoning; approve executes the tool for real; audit log.
5. Shelves `/shelves`: OSA per shelf, time-to-restock (retail only).
6. Forecast `/forecast`: next-24 h queue-peak windows and shelf-out risk vs seasonal naive, MAE table.
7. Report `/report`: weekly bilingual report, print-to-PDF stylesheet.

Motion: page transitions (View Transitions) and tabular count-ups only; spring easing; `prefers-reduced-motion` freezes the tape and disables count-ups. No decorative motion on the stream.

Live data: Server-Sent Events from `/stream` for events; TanStack Query for the rest; Zustand for profile/theme/locale.

## 7. Operations analytics (Term 4)

- `ops_theory.py`: λ from `footfall_tick` per 15-min slot, μ from `checkout_served` dwell per open till, c from site config; returns ρ, W_q, L_q; validated against hand-computed M/M/c examples in tests.
- Service level: % of slots with queue ≤ 3, target 90%.
- OSA: 1 − time-weighted empty ratio per shelf; time-to-restock from `shelf_gap` open to close.
- `forecast.py`: hourly counts, features hour/weekday/shift/last-24h; GradientBoostingRegressor vs seasonal naive; MAE and MAPE on 7-day holdout; requires ≥ 14 days of events or reports "insufficient history".
- `workforce.py`: min Σ staff-hours s.t. ρ_slot ≤ 0.85 and ≥ 1 till open; `scipy.optimize.milp`; test on 3-till toy problem.
- Before/after simulation: replay a week with proposals applied vs baseline.

## 8. Error handling and offline behaviour

- Edge: camera loss retries with backoff and emits a `camera_offline` health record; SQLite is the source of truth; `sync.py` pushes with idempotent ULIDs and resumes after reconnect; clips uploaded after events.
- Cloud: pydantic validation on every input; tool-call argument validation before execution; failed tool calls recorded with error and never retried automatically for side-effecting tools.
- Web: every data region has loading skeleton, empty state with instruction, and error state with retry. SSE reconnects with backoff and shows a "reconnecting" pill in the header.

## 9. Testing

- Edge pytest: `Det` on 5 fixture frames (ultralytics installed); zones point-in-polygon; every rule with synthetic tracks including time injection; store round-trip; sync offline queue with a fake server.
- Cloud pytest: routers with SQLite; policies (severity-3 cannot be downgraded is an explicit assertion); tool schema validation rejects bad args; DryRunBackend decisions; ops_theory against textbook M/M/c; workforce toy MILP; forecast beats naive on a synthetic seasonal series.
- Web vitest: tape binning, severity mapping, i18n message completeness (all keys in en/hi/ar), RTL direction, theme token presence.
- Playwright smoke: seeded event appears in stream → open clip → approve proposal → restock task visible in actions log.
- Model targets from the brief (mAP ≥ 0.80 etc.) are reported by `eval.py` against real datasets and are not gating for this build because SH17/MVTec need manual download.

## 10. Deployment

- Supabase: new project, SQL migration generated from SQLModel metadata, service key in Render env.
- Render: `render.yaml` web service for `cloud/`, health check `/health`, free tier; README states cold-start caveat.
- Vercel: `web/` with `NEXT_PUBLIC_API_URL`.
- Edge stays on the M4 Pro (or Docker) looping the Pexels clip and syncing to the cloud API for the live demo.

## 11. Term 4 artefacts

Generated by scripts under `docs/term4/` from `docs/results/*.json` produced by `eval.py` and the notebook: `AI218_RAQIB_report.docx`, `AI218_RAQIB_deck.pptx`, `term4_raqib.ipynb`, `viva_qa.md`, demo video script. Build fails if `grep -rE "TODO|XX|\[insert" docs/` matches.

## 12. Out of scope for this build

Real RTSP plant camera, WhatsApp Cloud API sending (template rendering only, webhook sink), PWA push, CoreML export, multi-camera re-identification, 24-hour unattended soak. Each is listed in README limitations.
