# RAQIB / MUSHRIF — v2 Design Addendum (Phases E–K)

Date: 2026-09-06 · Owner: Krishna Mathur · Status: DRAFT, awaiting owner "go"

This addendum extends `2026-09-06-raqib-design.md`. It never rewrites a Phase A–D interface; where an interface grows, the exact addition is stated. Plan: `docs/superpowers/plans/RAQIB-master-plan-v2-phases-E-K.md`.

## 1. Goals

The MVP proves cameras → deterministic rules → bounded agent → human approval. v2 adds five capabilities, each with its own tests, evals and kill switch:

| Capability | Tab | One-line promise |
|---|---|---|
| Ask | `/ask` | A manager types a question in EN/HI/AR and gets a cited answer over events, clips, KPIs and documents, or an honest "no matching data". |
| Watch | `/watch` | Blurred camera wall with a VLM second opinion that can raise attention but never lower severity. |
| Crew | `/crew` | Six narrow agents on one runtime, signed messages, per-run budgets, an Auditor that cannot be switched off, a kill switch. |
| Twin | `/twin` | Replay any day at 1-minute resolution and re-run M/M/c + MILP under what-if sliders. |
| Fleet | `/fleet` | Multi-store leaderboard, drift monitor, edge box health, RBAC, retention, cost governance. |
| Security | `/security` | OWASP Top 10 for Agentic Applications scorecard backed by a red-team harness that runs in CI. |

Budget for inference: **$0**. Every model call goes through one `LLMProvider` adapter (Section 4).

## 2. Confirmed baseline (measured 2026-09-06)

- Live API `https://raqib-backend-7qdg.onrender.com/health` → `{"status":"ok","events":0,"agent_backend":"dryrun","database":"sqlite"}`. The Render service is **not** pointed at Supabase; it runs on ephemeral SQLite, so seeded history vanishes on every deploy. Supabase project `raqib` (ap-south-1, Postgres 17.6) has the eight Phase A–D tables with 0 rows. Fixing this is a Render env change (owner action).
- Live web `https://raqib-orcin.vercel.app` → 307 to `/en`, renders.
- Tests: edge 47 passed, cloud 44 passed, web 15 passed, Playwright 2 flows.
- Machine: Apple M4 Pro, 24 GB unified memory, 214 GB free disk. Ollama 0.33.2 running; models present: `llama3.2:3b` (2.0 GB, tools, 128k ctx), `nomic-embed-text:latest` (274 MB, 768-d).
- Render plan: free (512 MB RAM, sleeps after 15 min, single worker). No Ollama on Render.

## 3. Tabs and routes

The rail order in the plan (Section 2 of the plan) is final. New pages are added to `web/components/shell/rail.tsx` `ITEMS` only; no existing page changes its route. Each new tab has loading, empty and error states like Phase C pages, sentence-case copy, no emoji icons.

## 4. LLMProvider: zero-cost adapter

```python
class LLMProvider(Protocol):
    name: str
    def complete(self, system: str, user: str, *, json_schema: dict | None = None,
                 images: list[bytes] | None = None, max_tokens: int = 800) -> LLMResult
# LLMResult(text, parsed, tokens_in, tokens_out, provider, model, latency_ms, cost_usd=0.0)

def get_provider(task: Literal["route", "answer", "caption", "opinion", "judge"]) -> LLMProvider
def embed_texts(texts: list[str]) -> list[list[float]]
class Quota:  # daily request + token counters per provider, stored in DB table `quota_counters`
    def check(self, provider: str) -> bool
    def record(self, provider: str, tokens: int) -> None
class QuotaExhausted(Exception): ...
```

Provider order per task, all free, first reachable wins; a connection error or `QuotaExhausted` falls through to the next; when the chain is empty the caller degrades (Section 4.3):

| Task | 1. Ollama (Mac / edge box) | 2. Gemini free tier | 3. Groq free tier | 4. `claude` (off) |
|---|---|---|---|---|
| route | `qwen3:4b-instruct` | `gemini-2.5-flash-lite` | `llama-3.1-8b-instant` | `claude-sonnet-4-6` |
| answer | `qwen3:8b` | `gemini-2.5-flash` | `llama-3.1-8b-instant` | `claude-sonnet-4-6` |
| judge | `qwen3:8b` | `gemini-2.5-flash` | `llama-3.1-8b-instant` | `claude-sonnet-4-6` |
| caption | `qwen2.5vl:7b` | `gemini-2.5-flash` (vision) | none (text only) | `claude-sonnet-4-6` |
| opinion | `qwen2.5vl:7b` | `gemini-2.5-flash` (vision) | none | `claude-sonnet-4-6` |

`LLM_PROVIDER=ollama` is the default; `LLM_PROVIDER_<TASK>` overrides one task; `LLM_PROVIDER=claude` requires `ANTHROPIC_API_KEY` and is never chosen implicitly. Ollama tags above are to be verified with `ollama pull` at Task 24b and recorded in `docs/models.md` with measured latency. Ollama calls set `think=false` for Qwen3 and `format=<json_schema>` when a schema is given.

### 4.1 Strict JSON
When `json_schema` is given the result is validated with pydantic; one retry with the validation error appended; a second failure returns `parsed=None` and the caller takes its deterministic path (regex/dateparser router, template answer, "opinion unavailable"). No guess is ever substituted.

### 4.2 Quotas
`Quota` counts requests and tokens per provider per UTC day in table `quota_counters(provider, day, requests, tokens)`. Limits are config, defaults conservative and below the published free tiers so a burst never produces a 429 storm:

| Provider | Config key | Default | Published free tier (to confirm in the provider console after the key is added) |
|---|---|---|---|
| ollama | `OLLAMA_DAILY_REQUESTS` | 5000 | n/a (local) |
| gemini | `GEMINI_DAILY_REQUESTS` | 800 | ~15 RPM / ~1,500 RPD Flash; ~1,000 RPD Flash-Lite; 250k TPM (third-party summaries, Sept 2026) |
| groq | `GROQ_DAILY_REQUESTS` | 800 | ~30 RPM / ~1,000 RPD / 12k TPM / 100k TPD for 8B-class models (third-party summaries; 70B moved off the free table Aug 2026) |
| claude | `CLAUDE_DAILY_REQUESTS` | 0 | paid; disabled |

Minute-level limits are handled by a token bucket in the client (`*_RPM`, default 10) plus honouring `Retry-After` once, then falling through.

### 4.3 Degradation ladder (never crash)
| Feature | With a provider | Without any provider |
|---|---|---|
| Caption | strict JSON caption stored | skipped, `quota_exhausted` or `provider_unavailable` logged as a `Caption` row with `model="none"` |
| Route | model plan validated by schema | regex + dateparser plan (time range, kind, camera, till, shelf) |
| Answer | cited prose in the query language | template answer listing the top hits with citations, in the query language, marked `confidence=0.3` |
| Opinion | Opinion row | Opinion row `agrees=None, observed="unavailable"` |
| Judge (evals) | faithfulness score | citation-coverage check only, marked `judge="deterministic"` |

The cost KPI reports requests and tokens per provider per day; dollars are 0 unless `claude` is enabled.

## 5. RAG design (Phase E)

### 5.1 Where things run
Render free has 512 MB RAM and no Ollama, so:
- **Indexing** (captions, chunking, embeddings) runs on the Mac / edge box via `raqib-api index --site --since` and writes chunks + vectors to the shared database (Supabase Postgres, or local SQLite in dev). The live API never embeds a corpus.
- **Querying** runs on Render. Hybrid retrieval always has two legs that need no model: SQL filters and BM25 (`tsvector` on Postgres, `rank-bm25` in SQLite dev). The third leg, pgvector ANN, needs a query embedding from the **same model used at index time**, so the embedding choice in Task 24b has a hard constraint: it must be computable on Render or via a free API. Candidates and the spike are in 5.3.
- **Rerank**: `bge-reranker-v2-m3` is not in the Ollama library (checked 2026-09-06). A cross-encoder needs torch, which does not fit Render free. Rerank is therefore `RERANK_ENABLED=false` by default and RRF is the final order on Render; when enabled (Mac dev, edge box) `sentence-transformers` runs `BAAI/bge-reranker-v2-m3`. Eval results are reported for both settings.

### 5.2 Schema additions (Task 24)
New tables, all additive: `captions`, `documents`, `chunks` (with `embedding` = pgvector `vector(EMBED_DIM)` on Postgres, JSON float list on SQLite; `model` column records which embedder produced it; `tsv` generated column on Postgres), `memories`, `agent_runs`, `agent_messages`, `users`, `stores`, `drift_samples`, `quota_counters`. `EMBED_DIM` is a setting (default 1024) read by the migration so the spike can change it once. Alembic manages all v2 tables; Phase A–D tables stay on `create_all` and are stamped as the baseline. `cloud/supabase/schema.sql` gains `create extension if not exists vector;` and the v2 DDL.

### 5.3 Embedding spike (Task 24b)
Corpus: 500 seeded event chunks + 3 documents (SOP, price list, planogram) chunked. 20 queries (8 EN, 6 HI, 6 AR) with hand-labelled relevant chunk ids. Candidates:

| Candidate | Dim | Where it can run | Multilingual |
|---|---|---|---|
| `bge-m3:567m` via Ollama | 1024 | Mac only | yes |
| `nomic-embed-text` via Ollama (present) | 768 | Mac only | weak |
| `intfloat/multilingual-e5-small` via fastembed (ONNX, int8) | 384 | Mac and Render (measure RSS) | yes |
| `gemini-embedding-001` via Gemini free API | 768 (truncated) | anywhere with a key | yes |

Measured: index time, query p95, recall@5, RSS on a 512 MB budget. Choice recorded in `docs/models.md` with the table. Default recommendation before measuring: a model Render can run itself (e5-small) or the Gemini API, so live `/ask` keeps its semantic leg; `bge-m3` only if the owner accepts that live semantic search degrades to BM25 + SQL when Ollama is unreachable.

### 5.4 Retrieval and answering (Task 26)
`route_query` → `QueryPlan{mode, time_range, kind, camera, shelf, till, lang, terms}`; `retrieve` → SQL prefilter → BM25 top 30 ∪ ANN top 30 → reciprocal rank fusion → optional rerank → top k=12; `answer` → every factual sentence carries ≥1 `[c:<chunk_id>]` citation, verified by a regex over sentence boundaries; zero hits above the floor → "No matching data for …" plus filter suggestions and no citations. Retrieved chunks are wrapped as `<retrieved id="…" kind="…">…</retrieved>` and the system prompt says they are data. Answer language = query language, checked with a script-based detector; mismatch triggers one regeneration then the template path.

### 5.5 Evals (Task 27)
30 cases in `cloud/evals/ask/cases.yaml`; metrics recall@5, citation precision, faithfulness (judge via `get_provider("judge")` on retrieved context only, plus deterministic citation coverage), latency p95, tokens per query. Gate: recall@5 ≥ 0.8, faithfulness ≥ 0.9, zero must-not-say hits. Runs in CI on PRs touching `rag/` or `prompts/`; the live run also writes `docs/results/ask_eval.json`.

## 6. Watch (Phase F)
`second_opinion(event, frames≤3 blurred keyframes from the stored clip)` → `Opinion`. Policy: may add `request_human_review`; may never change `Event.severity` or cancel an Action; `suggested_severity < event.severity` is stored as a disagreement metric. Auto for severity 3 and for detector confidence < 0.6. Edge gains an optional MJPEG endpoint of the already-blurred frames; the cloud proxies it behind auth. No raw frames leave the edge.

## 7. Crew (Phase G)
Agents: FloorOps, ShelfOps, Workforce, Safety (factory), Analyst (read-only), Auditor (mandatory). One `Runtime` enforces `Budget(max_tool_calls, max_usd, max_seconds)`, records every tool call through the existing `ToolRunner` and `Policy` (no second execution path), and checks the kill switch before every run and at every tool boundary. `Bus.send` validates the message schema, signs HMAC-SHA256 with the sender's key, and rejects replays (nonce + 5-minute window). Memory writes are screened (injection patterns, secrets/PII, protected keys, size, churn) → allow / redact / quarantine / block; nightly snapshot; rollback endpoint. Memories enter prompts only inside `<memory provenance="…">` blocks.

## 8. Twin (Phase H)
Replay = 1440 one-minute bins per day from events (occupancy per zone, queue length, shelf availability, events). What-if re-runs `slot_rates → mmc → service_level` and `staffing_plan` with overrides; deterministic for identical inputs. Scenarios saved as `Document(kind="scenario")` so Ask can cite them.

## 9. Integrations (Phase I)
POS CSV importer with dedupe; `slot_rates` gains `mu_source: video|pos` (additive field, default `video`). Planogram diff and price-tag OCR on the edge, new deterministic rules `R14_price_mismatch` and `R15_planogram_drift` (severity 1). WhatsApp templates only; Greenlam client gains retry, idempotency key and a circuit breaker.

## 10. Fleet (Phase J)
Supabase Auth (magic link + Google), JWT verified server-side, roles Viewer/Operator/Manager/Admin from `users.role`, site scoping from `users.site_ids`. Route matrix in `docs/rbac.md`. Drift: hourly `DriftSample`, PSI vs 7-day baseline, `model_drift` event when PSI > 0.2 for 3 hours. Retention job: clips 30 d, events 400 d, memories 90 d unless pinned; deletions logged. OpenTelemetry spans on every model call with model, tokens, cost, latency and prompt hash.

## 11. Security (Phase K)
ASI01–ASI10 mapped to a control and an attack test each (plan Task 43). `cloud/security/run.py` produces `docs/results/security_eval.json`; CI fails on regression. Defensive only.

## 12. Security envelope (applies to every phase)
- Every new tool is added to `TOOL_SCHEMAS` only and validated by `validate_call`; `Policy.check` still runs after any agent.
- Retrieved content and memories are untrusted data in delimiters, never instructions, never able to alter tool permissions.
- Severity 3 cannot be lowered by any new path (VLM, crew, Ask). Tested explicitly in each phase.
- `AGENTS_ENABLED=false` → 503 on every agent route. Auditor cannot be disabled while any other agent is enabled.
- No raw frames leave the edge; the VLM sees blurred frames only, ≤3 per event.
- Secrets via env only; `.env.example` documents every new variable.

## 13. Out of scope for v2
Facial recognition, re-identification, demographics (never). Individual-level loss prevention. A custom vector DB or agent framework. VLM fine-tuning. Kubernetes. Paid inference of any kind.
