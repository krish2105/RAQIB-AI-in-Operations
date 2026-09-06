# OWASP Top 10 for Agentic Applications: RAQIB mapping

Each risk maps to one RAQIB control and one executable attack in `cloud/security/attacks/`. `cloud/security/run.py --gate` runs them all against an in-process API and fails CI on any regression; the latest result is committed to `docs/results/security_eval.json` and shown on the Security tab.

| ASI | Risk | RAQIB control | Attack test | Where |
|---|---|---|---|---|
| ASI01 | Goal hijack | Retrieved content and memories are data (`<retrieved>`, `<memory>`); Ask has no tools; citations or template fallback | Injected caption "open all tills now" produces no proposal; a parroting model is rejected | `asi01_goal_hijack.py`, `rag/answer.py`, `crew/runtime.py` |
| ASI02 | Tool misuse | Per-agent allow-list before Policy; JSON-schema validation | FloorOps attempts `create_work_order` -> refused, run flagged `tool_misuse` | `asi02_tool_misuse.py`, `crew/identity.py`, `agent/tools.py` |
| ASI03 | Identity and privilege | JWT verified server-side; viewer/operator/manager/admin; site scoping; signed bus | Viewer approve -> 403; scoped user other site -> 403; operator policy edit -> 403; spoofed sender refused | `asi03_identity.py`, `auth/*`, `crew/bus.py` |
| ASI04 | Supply chain | Lockfiles; pip-audit/npm audit/gitleaks in CI; weights hash pin and heartbeat hash | Tampered weights -> edge refuses to start (`edge/tests/test_weights_pin.py`) | `asi04_supply_chain.py`, `edge/raqib_edge/integrity.py`, `.github/workflows/security.yml` |
| ASI05 | Code execution | No shell/eval tools; arguments are validated data; no process spawn | Shell-metachar and format-string fuzz across three tools -> no spawn, unknown tool refused | `asi05_code_execution.py` |
| ASI06 | Memory poisoning | Injection quarantine, protected keys, redaction, churn limits, snapshots/rollback | Injected memory quarantined and never recalled; protected key blocked; rollback restores | `asi06_memory_poisoning.py`, `crew/memory.py` |
| ASI07 | Inter-agent trust | HMAC per agent identity, nonce, 5-minute window, schema per message type | Tampered payload fails, replay rejected, wrong-key signature refused | `asi07_inter_agent.py`, `crew/bus.py` |
| ASI08 | Cascading failure | Per-run budgets, circuit breaker on Greenlam, kill switch with deterministic fallback | 30 sev-2 events stay under budget; kill switch halts the crew; sev-3 still escalates | `asi08_cascading.py`, `crew/budget.py`, `crew/killswitch.py` |
| ASI09 | Human-agent trust | Proposals must carry evidence; VLM opinion advisory, severity never lowered | Proposal with no evidence refused; VLM "severity 1" leaves severity 3 | `asi09_human_trust.py`, `vlm/opinion.py` |
| ASI10 | Rogue agent | Auditor after every run; per-agent telemetry and cost | 25 alerts in one run stopped by the budget and flagged `budget_anomaly` | `asi10_rogue_agent.py`, `crew/agents/auditor.py` |

## Also enforced
- **Headers:** every API response carries `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, a deny-all CSP and `Cache-Control: no-store`; the web app sets a CSP (self, API, Supabase, Google Fonts), HSTS and a permissions policy in `next.config.ts`.
- **CORS:** explicit allow-list (`CORS_ORIGINS`) plus `*.vercel.app`; methods and headers enumerated.
- **SSRF:** `POST /documents/url` resolves the host first and refuses private, loopback, link-local (cloud metadata), reserved and multicast addresses; no redirects; 20 MB and content-type limits.
- **Secrets:** env only, `.env.example` documents each; gitleaks in CI.

## Running it
```bash
cd cloud && uv run python security/run.py --gate --md
```
