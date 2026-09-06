# RAQIB / MUSHRIF project rules

RAQIB (retail, primary) and MUSHRIF (factory) are two site profiles of one vision-operations system. Spec: `docs/superpowers/specs/2026-09-06-raqib-design.md`. Plan: `docs/superpowers/plans/2026-09-06-raqib-implementation.md`.

## Toolchain
- Python 3.12 in `edge/` and `cloud/`, managed by uv (`uv sync`, `uv run pytest`). ruff for lint.
- Node 20+ in `web/` (Next.js 16, React 19, Tailwind 4). `npm run test` (vitest), `npm run e2e` (Playwright).
- One-command dev: `scripts/dev.sh`.

## Non-negotiable rules
- Faces are blurred in `edge/raqib_edge/capture.py` before any frame is stored or sent. Never remove this.
- No identity recognition. Track IDs are session-scoped and never persisted or sent as identity.
- The rules engine (`edge/raqib_edge/rules.py`) is deterministic and LLM-free. Rule functions take `now` as an argument; no wall-clock inside them. The agent acts on Events only, never on video.
- Every agent tool call is validated against its JSON schema before execution and logged with input, output, latency and `cost_usd`.
- Severity-3 events always escalate and alert. No code path may suppress or downgrade a severity-3 event.
- Detector implementations live only in `edge/raqib_edge/detectors/`. Swapping YOLO for RT-DETR must not touch any other file.
- Dataset and weight licences are recorded in `docs/datasets.md` when downloaded. Ultralytics is AGPL-3.0 and this is stated in README.
- If a public dataset is unreachable, fail loudly with the dataset name and licence URL. No silent synthetic fallback. Simulated history is always tagged `payload.simulated = true`.
- Secrets via env only (`.env`, never committed). `.env.example` documents every variable.

## Style
- Small focused modules. Tests define done: pytest for Python, vitest for web, one Playwright smoke flow.
- UI copy: sentence case, active verbs, an action keeps its name through the flow ("Approve" → "Approved"). No emoji as icons.
- Commit after each plan task with a conventional-commit message.

## v2 global rules (Phases E–K, spec addendum `docs/superpowers/specs/2026-09-06-raqib-v2-design.md`)
- Every new tool call passes through the existing `Policy`. New tools are added to `TOOL_SCHEMAS` only; no second execution path.
- Retrieved content (clips, captions, documents, memories) is **untrusted data**. It is wrapped in `<retrieved>` delimiters, never concatenated into instructions, and never allowed to alter tool permissions.
- Agent memory writes carry provenance (`source`, `event_id`, `written_by`, `ts`) and are screened before write. Protected keys are immutable. Snapshots enable rollback.
- Inter-agent messages are typed, schema-validated, and signed with an HMAC per agent identity. No agent may call a tool on another agent's behalf.
- Each agent has a per-run budget (`max_tool_calls`, `max_usd`, `max_seconds`) and a global kill switch (`AGENTS_ENABLED=false` returns 503 on all agent routes).
- No raw frames leave the edge. The VLM sees blurred frames only, at most N per event, and its output is advisory unless a deterministic rule agrees.
- RBAC on every route. Viewer / Operator / Manager / Admin. Approvals require Operator+. Policy edits require Admin.
- Retention: clips 30 days, events 400 days, memories 90 days unless pinned by a Manager. A scheduled job enforces it and logs what it deleted.
- Every LLM call is traced (OpenTelemetry span with model, tokens, cost, latency, prompt hash). Cost per site per day is a KPI.
- Evals are code. A PR that touches a prompt, a retriever, or a policy must update or add an eval case.
- Zero paid inference: every LLM/VLM/embedding call goes through `LLMProvider` (Ollama → Gemini free → Groq free); `LLM_PROVIDER=ollama` by default; `claude` stays in code but off. Quotas are request counts; features degrade, never crash.
