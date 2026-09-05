# RAQIB / MUSHRIF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, inline in this session (owner asked for no subagents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A locally runnable, deploy-ready vision-operations system: edge pipeline on a looped supermarket clip or webcam, FastAPI cloud with a bounded agent and Term 4 operations analytics, and a premium Next.js control room with a 3D floor, all with tests.

**Architecture:** Deterministic edge rules turn detections into `Event`s stored in SQLite and synced to the cloud API. The cloud stores events, runs a schema-validated tool-calling agent (dry-run by default), computes M/M/c, OSA, forecasts, and staffing MILP, and streams to the web app over SSE. The web app is a dark-first "Control Room" with a 24-hour event tape as its spine and a site-profile switch between RAQIB retail and MUSHRIF factory.

**Tech Stack:** Python 3.12 via uv; ultralytics 8.4 (YOLO26n, RT-DETR, ByteTrack), OpenCV, shapely, SQLite; FastAPI, SQLModel, scipy, scikit-learn, anthropic SDK; Next.js 16, React 19, Tailwind 4, Motion 13, React Three Fiber 9, Recharts 3, next-intl 4, next-themes, Zustand, TanStack Query; pytest, vitest, Playwright.

Spec: `docs/superpowers/specs/2026-09-06-raqib-design.md`. Every task's requirements include the spec's Section 2 rules.

## Global Constraints

- Python `>=3.12,<3.13` in both `edge/` and `cloud/`, managed by uv with `.python-version` = 3.12.
- Node 20+ (dev machine has 24). Web uses `npm`.
- Faces blurred in `capture.py` before storage or send. No identity recognition. Track IDs never persisted.
- `rules.py` functions are pure: `(tracks, zones, state, now) -> list[Event]`, no LLM, no wall-clock.
- Detector implementations only in `edge/raqib_edge/detectors/`.
- Agent tools validated against JSON schema before execution; every call logged with `cost_usd`.
- Severity 3 always escalates; no code path may lower a severity-3 event.
- Secrets via env only; `.env.example` documents them; `.env` gitignored.
- Ultralytics AGPL-3.0 stated in README and `docs/datasets.md`.
- Copy in the UI: sentence case, active verbs, an action keeps its name through the flow ("Approve" → "Approved").
- Commit after every task with a conventional-commit message and the Claude co-author trailer.

---

## File map

Edge (`edge/raqib_edge/`): `events.py` (Event, Det, Track dataclasses + to_dict/from_dict), `zones.py` (Zone, load_site, point_in_zone), `rules.py` (R01–R03, R10–R13, RuleState), `detectors/base.py` (Detector Protocol, `make_detector(name)`), `detectors/yolo.py`, `detectors/rtdetr.py`, `track.py` (ByteTrack wrapper via ultralytics `model.track`), `capture.py` (FrameSource: webcam/file/rtsp, `blur_faces`), `shelf.py` (empty ratio), `machine_state.py` (ROI classifier stub with heuristics), `store.py` (SQLite + ClipWriter ring buffer), `sync.py` (outbox → HTTP), `preview.py`, `main.py` (typer CLI). Sites in `edge/sites/*.yaml`. Training in `edge/training/`.

Cloud (`cloud/raqib_api/`): `config.py`, `db.py`, `models.py`, `schemas.py`, `main.py`, `routers/{health,sites,events,actions,forecast,report,stream}.py`, `agent/{tools,policies,backends,ops_agent,weekly_agent}.py`, `prompts/*.md`, `ops_theory.py`, `workforce.py`, `forecast.py`, `greenlam.py`, `notify.py`, `simulate.py`, `templates/*.j2`.

Web (`web/`): `app/[locale]/layout.tsx`, `app/[locale]/(console)/layout.tsx` (rail + header + tape), pages per spec, `components/tape/Tape.tsx`, `components/floor/FloorScene.tsx`, `components/kpi/KpiTile.tsx`, `components/stream/EventStream.tsx`, `components/actions/ProposalCard.tsx`, `lib/api.ts`, `lib/store.ts`, `lib/profile.ts`, `lib/severity.ts`, `messages/{en,hi,ar}.json`, `i18n/{routing,request}.ts`, `middleware.ts`, `app/globals.css` (tokens).

---

## Phase A — Edge

### Task 1: Repo scaffolding, CLAUDE.md, datasets ledger

**Files:** Create `CLAUDE.md`, `README.md` (skeleton with problem/architecture/run/licences/limitations headings filled), `docs/datasets.md`, `.env.example`, `edge/pyproject.toml`, `cloud/pyproject.toml`, `edge/.python-version`, `cloud/.python-version`, `scripts/dev.sh` (placeholder body replaced in Task 22).

- [ ] Write CLAUDE.md with the spec Section 2 rules verbatim plus toolchain lines.
- [ ] Write `docs/datasets.md` with rows: Pexels 39221979 (Pexels licence, 1920×1080, 35 s), Pexels 854634 (CC0, 1280×720, 18 s), yolo26n.pt and rtdetr-l.pt (ultralytics/assets v8.4.0, AGPL-3.0), SH17 (CC BY-NC-SA 4.0, Kaggle URL, manual), MVTec-AD (CC BY-NC-SA 4.0, manual), MOT17 (manual, not required).
- [ ] `uv sync` in both `edge/` and `cloud/`; verify `python -c "import torch; print(torch.backends.mps.is_available())"` prints True.
- [ ] Commit: `chore: scaffold edge and cloud packages, CLAUDE.md, dataset ledger`.

### Task 2: Event model and zones

**Files:** Create `edge/raqib_edge/events.py`, `edge/raqib_edge/zones.py`, `edge/sites/retail_demo.yaml`, `edge/sites/greenlam_unit1.yaml`, `edge/tests/test_events.py`, `edge/tests/test_zones.py`.

**Interfaces produced:**
```python
@dataclass(frozen=True) class Det: cls: str; conf: float; xyxy: tuple[float,float,float,float]
@dataclass class Track: track_id: int; cls: str; conf: float; xyxy: tuple[...]; centroid: tuple[float,float]
@dataclass class Event: id: str; site: str; camera: str; ts: datetime; kind: str; severity: int; payload: dict; clip_path: str|None; rule_id: str
    def to_dict(self) -> dict; @classmethod from_dict(cls, d) -> Event
def new_event(site, camera, ts, kind, severity, payload, rule_id, clip_path=None) -> Event  # ulid id
@dataclass class Zone: name: str; kind: str  # entrance|queue|shelf|checkout|work_area|exclusion|machine
    polygon: list[tuple[float,float]]; camera: str; meta: dict
    def contains(self, pt) -> bool
@dataclass class Site: name: str; profile: str; cameras: dict; zones: list[Zone]; thresholds: dict; tills: int; floor: dict
def load_site(path) -> Site
```
Site YAML schema: `name`, `profile: retail|factory`, `cameras: {cam1: {source: file|webcam|rtsp, uri, fps}}`, `zones: [{name, kind, camera, polygon: [[x,y],...] in normalised 0–1 frame coords, meta: {till: 1, shelf_id: ...}}]`, `thresholds: {queue_n: 4, queue_s: 60, shelf_empty_ratio: 0.4, shelf_s: 300, helmet_s: 2, machine_stop_s: 120, checkout_dwell_s: 20}`, `tills: 3`, `floor: {width_m, depth_m, zones: [{name, x, y, w, d}]}`.

- [ ] Tests: Event round-trips through `to_dict/from_dict` with UTC timestamps; `new_event` ids are 26-char ULIDs and monotonic; `Zone.contains` true for centre, false for outside; `load_site` on both YAMLs returns the right profile and zone count; a zone with `kind` outside the allowed set raises `ValueError` naming the zone.
- [ ] Implement; run `uv run pytest`; commit `feat(edge): event model, zones, site config`.

### Task 3: Rules engine

**Files:** Create `edge/raqib_edge/rules.py`, `edge/tests/test_rules.py`.

**Interfaces produced:**
```python
@dataclass class RuleState:  # mutable across frames, per camera
    dwell: dict[tuple[str,int], datetime]   # (zone, track_id) -> entered_at
    queue_over_since: dict[str, datetime|None]
    shelf_gap_since: dict[str, datetime|None]
    machine_stopped_since: dict[str, datetime|None]
    last_emit: dict[str, datetime]           # rule_key -> ts (debounce)
    crossed: set[tuple[str,int]]
def evaluate(tracks: list[Track], site: Site, camera: str, state: RuleState, now: datetime,
             shelf_ratios: dict[str,float] | None = None, machine_states: dict[str,str] | None = None) -> list[Event]
```
Rules per spec table: R01 (factory, helmet), R02 (exclusion), R03 (machine stopped), R10 (queue over), R11 (shelf gap), R12 (footfall tick on first entry to `entrance`), R13 (checkout served on leaving `checkout` after dwell). Each rule a pure function `r10_queue_over(tracks, site, camera, state, now) -> list[Event]`; `evaluate` picks rules by profile. Debounce: R10/R11/R03 emit once per continuous violation; re-emit after `thresholds.reemit_s` (default 300).

- [ ] Tests (synthetic tracks, injected `now`): queue of 5 for 59 s emits nothing, at 61 s emits one severity-2 with `payload.count == 5`; two persons in exclusion emits two severity-3 immediately; helmet present suppresses R01; footfall tick emitted once per track; checkout dwell 25 s then leave emits `checkout_served` with `dwell_s`; shelf ratio 0.5 for 5 min emits severity 1 once; profile `retail` never runs R01–R03.
- [ ] Commit `feat(edge): deterministic rules R01-R03, R10-R13`.

### Task 4: Detector adapter, tracking

**Files:** Create `edge/raqib_edge/detectors/{__init__,base,yolo,rtdetr}.py`, `edge/raqib_edge/track.py`, `edge/tests/test_detectors.py`, `edge/tests/fixtures/frames/*.jpg` (5 frames extracted with ffmpeg from the checkout clip at t=2,9,16,23,30 s).

**Interfaces produced:**
```python
class Detector(Protocol):
    name: str
    def load(self, weights: str, device: str) -> None: ...
    def detect(self, frame: np.ndarray) -> list[Det]: ...
    def track(self, frame: np.ndarray) -> list[Track]: ...   # ByteTrack persist=True
def make_detector(name: Literal["yolo","rtdetr"]) -> Detector
def pick_device() -> str  # "mps" | "cuda" | "cpu"
```
COCO class filter: keep `person`; map `hardhat`/`helmet`/`vest` if the loaded model has them (custom PPE weights).

- [ ] Tests: `make_detector("yolo").detect(frame)` on 5 fixtures returns ≥1 person each with conf in (0,1] and xyxy inside frame; `track` on 10 consecutive frames keeps ≥1 stable id; `make_detector("rtdetr")` loads and detects on one fixture (skipped with reason if weights absent); swapping detector requires no change in `rules.py` (asserted by importing rules without detectors).
- [ ] Commit `feat(edge): Detector adapter with YOLO26 and RT-DETR, ByteTrack`.

### Task 5: Capture with face blur, shelf estimator, machine state

**Files:** Create `edge/raqib_edge/capture.py`, `edge/raqib_edge/shelf.py`, `edge/raqib_edge/machine_state.py`, `edge/tests/test_capture.py`, `edge/tests/test_shelf.py`.

**Interfaces produced:**
```python
class FrameSource:  # cv2 wrapper
    def __init__(self, uri: str|int, loop: bool = True, target_fps: float|None = None)
    def frames(self) -> Iterator[tuple[datetime, np.ndarray]]
def blur_faces(frame: np.ndarray, person_boxes: list[tuple]) -> np.ndarray  # OpenCV Haar cascade inside person boxes; falls back to blurring top 25% of each person box when cascade finds nothing
def shelf_empty_ratio(frame, polygon_norm) -> float  # edge density + colour variance heuristic, 0..1
def classify_machine_state(roi_prev, roi_now) -> Literal["running","idle","stopped"]  # frame-difference energy
```
- [ ] Tests: `FrameSource(file, loop=True)` yields more frames than the clip has (loops); `blur_faces` changes pixels inside the head region and nowhere else; `shelf_empty_ratio` on a flat grey image > 0.8 and on a busy fixture < 0.4; `classify_machine_state` returns `stopped` for identical ROIs and `running` for noisy differing ROIs.
- [ ] Commit `feat(edge): capture with face blur, shelf and machine-state estimators`.

### Task 6: Store, clip writer, sync outbox

**Files:** Create `edge/raqib_edge/store.py`, `edge/raqib_edge/sync.py`, `edge/tests/test_store.py`, `edge/tests/test_sync.py`.

**Interfaces produced:**
```python
class EventStore:  # sqlite
    def __init__(self, path: str); def append(self, e: Event) -> None
    def unsynced(self, limit=100) -> list[Event]; def mark_synced(self, ids: list[str]) -> None
    def recent(self, n=50) -> list[Event]
class ClipWriter:  # ring buffer of last 5 s frames, writes 10 s mp4 around an event
    def __init__(self, out_dir: str, fps: float, pre_s=5, post_s=5)
    def push(self, ts, frame); def trigger(self, event_id) -> str  # returns path when complete
class Syncer:
    def __init__(self, store: EventStore, api_url: str, site: str, clips_dir: str, client: httpx.Client|None=None)
    def push_once(self) -> int   # events posted; POST {api}/events/batch ; then PUT clips
```
- [ ] Tests: append/unsynced/mark_synced round trip; `ClipWriter` produces an mp4 with duration between 8 and 12 s; `Syncer.push_once` against `httpx.MockTransport` returning 503 leaves events unsynced, then 200 marks them synced; batch payload uses `Event.to_dict()`.
- [ ] Commit `feat(edge): sqlite store, clip ring buffer, offline sync`.

### Task 7: Edge CLI and preview

**Files:** Create `edge/raqib_edge/main.py`, `edge/raqib_edge/preview.py`, `edge/raqib_edge/pipeline.py` (glue: source → detector.track → blur → rules → store/clips → sync), `edge/tests/test_pipeline.py`.

CLI: `raqib-edge run --site sites/retail_demo.yaml [--source file|webcam] [--preview] [--api http://localhost:8000] [--max-frames N] [--detector yolo|rtdetr]`. `--max-frames` enables headless tests.

- [ ] Test: `run_pipeline(site, max_frames=60, detector="yolo", api=None)` on the checkout clip produces ≥1 `footfall_tick` or `checkout_served` event in SQLite and reports fps in the returned stats.
- [ ] Manual check: `--preview` shows boxes, zones, and blurred heads at ≥ 15 fps on M4 Pro; record the fps in README.
- [ ] Commit `feat(edge): pipeline, CLI, preview window`.

### Task 8: Training and evaluation scripts

**Files:** Create `edge/training/{prepare_data,train_ppe,train_shelf,eval}.py`, `edge/tests/test_prepare_data.py`.

- `prepare_data.py --dataset sh17|mvtec` checks `edge/data/datasets/<name>/` exists; if not, exits 2 printing dataset name, licence, and URL (no download of licensed sets). Appends a row to `docs/datasets.md` when found.
- `eval.py` runs COCO-pretrained yolo26n on fixture frames and the checkout clip, writing `docs/results/edge_eval.json` with per-frame latency (mean, p95), fps, detections per class, device. It also runs the RT-DETR adapter on 3 frames for the latency table. If a fine-tuned PPE weights file exists it reports mAP50 via `model.val`.
- [ ] Test: missing dataset exits with code 2 and message containing "CC BY-NC-SA".
- [ ] Commit `feat(edge): training scripts and eval report`.

## Phase B — Cloud

### Task 9: API skeleton, models, events router, SSE

**Files:** Create `cloud/raqib_api/{config,db,models,schemas,main}.py`, `routers/{health,sites,events,stream}.py`, `cloud/tests/{conftest,test_events}.py`.

**Interfaces produced:** SQLModel tables `Site, Camera, Zone, Event, Clip, Action, ToolCall, Forecast`; `POST /events/batch` (idempotent on id), `GET /events?site&since&kind&severity&limit`, `GET /events/{id}`, `PUT /clips/{event_id}` (multipart, stored under `CLIPS_DIR`), `GET /clips/{event_id}`, `GET /stream?site` (SSE `event` messages), `GET /sites`, `POST /sites/import` (site YAML), `GET /health`. Settings: `DATABASE_URL` (default sqlite), `CLIPS_DIR`, `ANTHROPIC_API_KEY`, `AGENT_BACKEND=dryrun|claude`, `GREENLAM_URL`, `GREENLAM_EMPLOYEE_ID`, `GREENLAM_PIN`, `CORS_ORIGINS`.

- [ ] Tests (TestClient + sqlite tmp): batch post of 3 events returns 201 with `inserted=3`, repost returns `inserted=0`; filter by severity; get by id 404 for unknown; `/stream` yields the event posted after subscription (use anyio task).
- [ ] Commit `feat(api): models, events, clips, SSE stream`.

### Task 10: Ops theory (M/M/c) and KPIs

**Files:** Create `cloud/raqib_api/ops_theory.py`, `cloud/raqib_api/kpis.py`, `routers/kpis.py`, `cloud/tests/test_ops_theory.py`, `cloud/tests/test_kpis.py`.

**Interfaces produced:**
```python
def mmc(lam: float, mu: float, c: int) -> MMCResult  # rho, p0, Lq, Wq, W, L ; raises if rho>=1 -> returns rho with Wq=inf
def slot_rates(events, slot_min=15, tills_open: int) -> list[SlotRates]  # lam from footfall_tick, mu from checkout_served dwell
def service_level(events, slot_min=15, max_queue=3) -> float
def osa(events, now, window_h=24) -> dict[shelf_id, float]; def time_to_restock(events) -> dict[shelf_id, float]
GET /kpis?site&profile -> {service_level, osa, avg_queue, footfall_per_hour, compliance, downtime_min, stopped_machines, queue_model: [{slot, lam, mu, rho, wq_model, wq_observed}]}
```
- [ ] Tests: textbook M/M/2 with λ=4, μ=3 gives ρ=0.667, Lq≈1.067, Wq≈0.267 h (tolerance 1e-3); c=1 reduces to M/M/1 formulas; ρ≥1 returns `Wq=math.inf`; service level on synthetic events; OSA = 1 − empty time fraction.
- [ ] Commit `feat(api): M/M/c queue model, service level, OSA KPIs`.

### Task 11: Agent tools, policies, backends

**Files:** Create `agent/{tools,policies,backends,ops_agent}.py`, `prompts/ops_agent.md`, `greenlam.py`, `notify.py`, `templates/alerts/{en,hi,ar}.yaml`, `routers/actions.py`, `cloud/tests/{test_policies,test_tools,test_agent,test_greenlam}.py`.

**Interfaces produced:**
```python
TOOL_SCHEMAS: dict[str, dict]  # JSON schema per tool name from spec Section 5
def validate_call(name, args) -> dict  # raises ToolValidationError
class ToolRunner: def execute(self, name, args, ctx) -> ToolResult  # side effects; logs ToolCall
class Policy: def check(self, event, proposed_calls) -> list[Call]  # enforces spec policies; adds escalate+send_alert for sev3; drops downgrade attempts; rate-limits work orders (4 h)
class AgentBackend(Protocol): def decide(self, event, context) -> Decision  # Decision(calls: list[Call], rationale: str, confidence: float, cost_usd: float)
class DryRunBackend(AgentBackend); class ClaudeBackend(AgentBackend)  # anthropic tool-use, model claude-sonnet-4-6
def handle_event(event, session, backend, runner) -> list[Action]  # proposals stored, autonomous calls executed
class GreenlamClient: def __init__(url, employee_id, pin, client=None); def login(); def raise_ticket(machine_id:int, description, priority, location=None, client_id: UUID|None=None) -> dict
def render_alert(template: str, lang: str, vars: dict) -> str
POST /actions/{id}/approve -> executes tool; POST /actions/{id}/reject; GET /actions?status ; GET /toolcalls
```
- [ ] Tests: sev-3 event → policy output contains `escalate` and `send_alert` even when backend returned nothing; backend attempting `severity=1` on sev-3 is rejected; second `create_work_order` for same machine within 4 h is dropped with reason; bad args (priority "Urgent") raise; `DryRunBackend` on `queue_over` with ρ=0.9 proposes `propose_open_till` citing rho; `GreenlamClient.raise_ticket` posts `TicketCreate`-shaped JSON with bearer header (respx); approve endpoint moves status to `executed` and creates a `ToolCall` row; alert templates exist for every (template, lang) combination.
- [ ] Commit `feat(api): bounded agent with tools, policies, dry-run and Claude backends`.

### Task 12: Forecasting and workforce MILP

**Files:** Create `forecast.py`, `workforce.py`, `routers/forecast.py`, `cloud/tests/{test_forecast,test_workforce}.py`.

**Interfaces produced:**
```python
def hourly_counts(events, kind) -> pd.Series
def seasonal_naive(series, season=24*7) -> pd.Series
def fit_predict(series, horizon=24) -> ForecastResult  # GradientBoostingRegressor, features hour, weekday, lag24, lag168, rolling24; returns preds, baseline, mae, mape, mae_naive
def staffing_plan(lam: list[float], mu: float, max_rho=0.85, max_tills=6) -> StaffingPlan  # scipy milp; tills per slot, total staff-hours, cost
GET /forecast?site&target=queue|shelf -> {history, forecast, baseline, mae, mae_naive, improvement_pct, sufficient: bool}
GET /workforce?site -> plan
```
- [ ] Tests: on a synthetic 21-day series with daily+weekly seasonality plus noise, GBR MAE < naive MAE; < 14 days returns `sufficient=False`; toy 3-slot MILP picks minimum tills keeping ρ ≤ 0.85 (hand-computed: λ=[2,5,8], μ=3 → tills [1,2,4]).
- [ ] Commit `feat(api): GBR forecast vs seasonal naive, staffing MILP`.

### Task 13: Weekly agent and report

**Files:** Create `agent/weekly_agent.py`, `prompts/weekly_agent.md`, `routers/report.py`, `templates/report/{en,hi,ar}.md.j2`, `cloud/tests/test_report.py`.

`GET /report/weekly?site&lang` → JSON `{period, kpis, top_events, forecasts, recommendations: [3 × {title, rationale, expected_reduction}], before_after: {baseline, with_proposals}}` plus `?format=md`. Dry-run backend fills recommendations from a rule table; Claude backend uses Opus.

- [ ] Tests: report renders in all three languages with no empty sections; exactly three recommendations; before/after simulation reduces total W_q when proposals applied.
- [ ] Commit `feat(api): weekly bilingual report and before/after simulation`.

### Task 14: Simulator and seed

**Files:** Create `simulate.py`, `routers/admin.py` (`POST /admin/seed?days=21`), `cloud/tests/test_simulate.py`.

Generates 21 days of labelled synthetic history (footfall with daily/weekly seasonality, checkout served, queue_over at peaks, shelf gaps, and for factory profile machine_stopped/ppe) tagged `payload.simulated=true` so the UI can label it. Live edge events are never tagged.

- [ ] Tests: seed produces events for every kind of the chosen profile; all have `simulated=true`; deterministic with seed.
- [ ] Commit `feat(api): labelled history simulator for demo and forecasting`.

## Phase C — Web

### Task 15: Next.js scaffold, tokens, theme, i18n, shell

**Files:** `web/` via `create-next-app@latest` (TypeScript, Tailwind, App Router, Turbopack, no src dir). Create `app/globals.css` (tokens from spec Section 6, both themes, `data-theme` + `prefers-color-scheme`), `i18n/routing.ts`, `i18n/request.ts`, `middleware.ts`, `messages/{en,hi,ar}.json`, `app/[locale]/layout.tsx` (fonts via `next/font/google`: IBM Plex Sans, IBM Plex Sans Arabic, IBM Plex Sans Devanagari, IBM Plex Mono, Archivo), `components/shell/{Rail,Header,ThemeToggle,LocaleSwitch,ProfileSwitch}.tsx`, `lib/{store,profile,severity,api}.ts`, `tests/severity.test.ts`, `tests/messages.test.ts`.

- [ ] Tests (vitest): `severityMeta(3)` returns label, icon name, token `--critical`; every key in `en.json` exists in `hi.json` and `ar.json`; `ar` locale sets `dir="rtl"`.
- [ ] Verify in browser: theme toggle persists, RTL flips the rail, fonts load.
- [ ] Commit `feat(web): control-room shell, tokens, theme toggle, EN/HI/AR`.

### Task 16: The tape

**Files:** Create `components/tape/{Tape,useTapeData,tapeMath}.tsx`, `tests/tapeMath.test.ts`.

`binEvents(events, dayStart, binMin=5) -> {footfall: number[], ticks: {x, severity, id}[]}`; Canvas renders trace, ticks, playhead; hover shows time + count; click tick → `/events/[id]`; respects reduced motion (no playhead animation).

- [ ] Tests: binning puts an event at 00:07 into bin 1, 23:59 into bin 287; ticks preserve ids.
- [ ] Commit `feat(web): 24-hour event tape`.

### Task 17: Dashboard, KPI tiles, event stream, queue model card

**Files:** Create `app/[locale]/(console)/page.tsx`, `components/kpi/KpiTile.tsx` (Motion count-up, tabular mono), `components/stream/EventStream.tsx` (SSE via `EventSource`, reconnect pill), `components/kpi/QueueModelCard.tsx` (Recharts line: W_q model vs observed), `components/actions/ProposalPreview.tsx`, `lib/sse.ts`.

- [ ] Test: `useEventStream` reducer prepends new events and caps at 200.
- [ ] Commit `feat(web): dashboard with KPIs, live stream, queue model`.

### Task 18: 3D floor

**Files:** Create `components/floor/{FloorScene,ZoneMesh,EventPulse,useFloorData}.tsx`, `app/[locale]/(console)/floor/page.tsx`.

R3F canvas, `dpr=[1,1.5]`, no post-processing, zones as extruded rectangles from `site.floor`, instanced pulses at event zones fading over 3 s, hover tooltip with last event, orthographic camera by default, `frameloop="demand"` when idle. Dashboard embeds the same component at smaller size.

- [ ] Verify 60 fps in Chrome performance panel on the desktop; mobile viewport renders.
- [ ] Commit `feat(web): R3F 3D floor with live pulses`.

### Task 19: Event detail, actions, shelves, forecast, report pages

**Files:** Create pages under `app/[locale]/(console)/{events/[id],actions,shelves,forecast,report}/page.tsx` and components `components/events/{ClipPlayer,DetectionOverlay,DecisionPanel}.tsx`, `components/actions/ProposalCard.tsx`, `components/shelves/ShelfGrid.tsx`, `components/forecast/ForecastChart.tsx`, `components/report/ReportView.tsx` (print stylesheet).

- [ ] Tests: `ProposalCard` renders Approve/Reject and calls the API; approving shows "Approved".
- [ ] Commit `feat(web): event detail, actions queue, shelves, forecast, report`.

### Task 20: Playwright smoke

**Files:** `web/e2e/smoke.spec.ts`, `web/playwright.config.ts` (starts API with seed and web dev server).

Flow: seed → dashboard shows an event in the stream → open it → clip or overlay visible → go to Actions → approve a proposal → status "Executed" and a tool call row appears.

- [ ] Commit `test(web): playwright smoke flow`.

## Phase D — Integration, docs, deploy

### Task 21: One-command dev, Docker, deploy configs

**Files:** `scripts/dev.sh` (API on 8000 with seed, edge file-loop syncing, web on 3000), `docker-compose.yml` (edge + api), `edge/Dockerfile`, `cloud/Dockerfile`, `render.yaml`, `web/vercel.json`, `cloud/supabase/schema.sql` (generated from SQLModel metadata by `scripts/export_schema.py`).

- [ ] Verify `scripts/dev.sh` brings all three up and a live edge event appears in the browser within 30 s.
- [ ] Commit `chore: dev script, docker, render and vercel configs`.

### Task 22: Eval results, Term 4 artefacts, README, docs

**Files:** `docs/results/*.json` from `eval.py`, `/kpis`, `/forecast`, `/workforce`; `docs/term4/{build_report.py,build_deck.py,build_notebook.py}` producing `docs/AI218_RAQIB_report.docx`, `docs/AI218_RAQIB_deck.pptx`, `docs/term4_raqib.ipynb`; `docs/viva_qa.md`; `docs/pilot_sop.md`; `docs/privacy_notice.md`; `docs/architecture.md` (Mermaid); `docs/demo_script.md`; final `README.md`.

- [ ] Gate: `grep -rE "TODO|XX|\[insert" docs/` returns nothing; every number in the report maps to a key in `docs/results/`.
- [ ] Commit `docs: Term 4 report, deck, notebook, viva, SOP, README`.

### Task 23: Deploy (each step confirmed by owner)

- [ ] Supabase: create project `raqib`, apply `schema.sql`, note `DATABASE_URL`.
- [ ] Render: create web service from `render.yaml`, set env, verify `/health`.
- [ ] Vercel: deploy `web/` with `NEXT_PUBLIC_API_URL`, verify dashboard loads with seeded data.
- [ ] GitHub: create `krish2105/RAQIB-AI-in-Operations`, push.
- [ ] Update README with live URLs; commit `docs: live deployment URLs`.

---

## Self-review

Spec coverage: Sections 3–11 map to Tasks 1–23; Section 12 out-of-scope items are listed in README (Task 22). Placeholder scan: none. Type consistency: `Event.to_dict()` used by `Syncer` and `POST /events/batch`; `Decision.calls` consumed by `Policy.check`; `slot_rates` output consumed by `staffing_plan` via `lam` list and `mu`.
