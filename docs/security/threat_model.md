# RAQIB threat model (v2)

RAQIB is an agentic vision-operations system: edge boxes detect, a rules engine emits events, a crew of six LLM-backed agents proposes or executes tool calls through one policy layer, and people approve from a web console. The model below follows STRIDE per trust boundary and maps every mitigation to the OWASP Top 10 for Agentic Applications (ASI01-ASI10, see `asi_mapping.md`).

## Assets

| Asset | Why it matters |
|---|---|
| Blurred clips and captions | Personal data even when blurred; retention 30 days |
| Events, actions, audit trail | Operational truth; tampering hides incidents |
| Policy thresholds | Change what the agent may do without a human |
| Agent memories | Persist across runs; poisoning changes future behaviour |
| Credentials (Supabase JWT secret, provider keys, bus HMAC keys, WhatsApp token) | Full control of the API or spend |
| Detector weights | A swapped model can blind the system |

## Trust boundaries and threats

### B1: Camera -> edge box
- **Threat:** raw frames leaving the box (privacy), identity recognition.
- **Controls:** faces blurred in `capture.py` before any frame is stored or sent; track ids session-scoped; VLM sees blurred frames only, at most N per event. Not changeable by config.

### B2: Edge -> cloud API
- **Threat:** spoofed events, tampered weights, replayed heartbeats.
- **Controls:** edge token per box, weights hash pin (`RAQIB_WEIGHTS_SHA256`, ASI04) and hash in every heartbeat; sample floors on drift; `edge_offline` after 5 minutes of silence.

### B3: Retrieved content -> model context
- **Threat:** prompt injection through captions, documents, POS rows, memories ("open all tills now").
- **Controls:** all retrieved content is wrapped in `<retrieved>` / `<memory>` delimiters and declared data in the system prompt; the router is deterministic for kind/time/superlatives and only accepts model values literally present in the question; answers must cite `[c:ID]` per factual sentence or fall back to a template; Ask has no tools at all (ASI01).

### B4: Agent -> tools
- **Threat:** an agent calling a tool it was never given, arguments that reach a shell, runaway loops.
- **Controls:** per-agent allow-list checked in the runtime before `Policy`; JSON-schema validation of every call; the runner has no shell/eval tool and never spawns processes (ASI02, ASI05); per-run budgets and a global kill switch (ASI08); proposals without evidence are refused (ASI09).

### B5: Agent <-> agent
- **Threat:** a compromised agent impersonating the Auditor, replaying or tampering messages.
- **Controls:** typed, schema-validated messages with a per-agent HMAC, nonce and 5-minute window (ASI07); no agent may call a tool on another's behalf; Auditor runs after every run (ASI10).

### B6: Agent -> memory
- **Threat:** persistence of injected instructions; overwrite of thresholds via memory.
- **Controls:** provenance on every write, injection quarantine, protected keys, secret redaction, size/churn limits, snapshots and rollback (ASI06).

### B7: Person -> API
- **Threat:** privilege escalation, cross-site reads, CSRF/clickjacking, SSRF through document URLs.
- **Controls:** Supabase JWT verified server-side (HS256 secret or JWKS), four roles, site scoping, rate limits on Ask/VLM, strict CORS allow-list, defensive headers on every response, CSP on the web app, SSRF guard on `POST /documents/url` (public addresses only, no redirects, size and type limits) (ASI03).

### B8: Supply chain
- **Threat:** vulnerable or malicious dependency, tampered weights.
- **Controls:** lockfiles (`uv.lock`, `package-lock.json`), pip-audit and npm audit in CI (`security.yml`), gitleaks secret scan, weights pin (ASI04).

## Residual risks
- The free LLM providers see prompt content (never raw frames, never secrets). Ollama on-prem removes this for sites that run it.
- Render's free tier runs on ephemeral SQLite; the audit trail is durable only once `DATABASE_URL` points at Supabase.
- Weights are pinned only when the operator sets the hash; the default is "report, not enforce".
- The red-team suite is a regression gate, not a proof: each ASI has one representative attack.
