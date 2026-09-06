# RAQIB v2 — one page

**What.** A vision-operations control room for supermarkets (RAQIB) and factories (MUSHRIF) that runs on the cameras a site already owns. Deterministic rules turn detections into events; queueing theory, a forecast and an integer program turn events into staffing decisions; a bounded crew of agents proposes or acts through one policy; people approve from a trilingual console.

**What is new in v2.**
- **Ask:** cited answers over events, KPIs and documents in EN/HI/AR. 30 eval cases: recall@5 1.00, faithfulness 0.93, 0 hallucinations.
- **Watch:** blurred camera wall with live boxes, captions, and VLM second opinions that can ask for a human but never lower a severity.
- **Crew:** six narrow agents on one runtime with allow-lists, budgets, signed messages, an Auditor after every run, guarded memory with rollback, and a kill switch.
- **Twin:** replay any day at one-minute resolution and test "one more till" before opening it.
- **Integrations:** POS import (mu from POS), planogram and price-tag rules on the edge, WhatsApp templates to an opt-in roster, Greenlam tracker with a circuit breaker.
- **Fleet and ops:** Supabase Auth with four roles and site scoping, drift detection (PSI) with a suggested fix, edge health, retention, one span per model call and a cost KPI.
- **Security:** OWASP ASI01-ASI10 mapped to controls and executable attacks; 10/10 defended; CI gate with pip-audit, npm audit and a secret scan.

**Numbers that matter.**

| | |
|---|---|
| Inference spend | $0.00 (Ollama, then Gemini and Groq free tiers) |
| Ask latency (laptop, 8B model) | mean 18.1 s, p95 24.0 s |
| Crew run | FloorOps 0.028 s, Auditor 0.005 s |
| Twin playback | 60.5 fps headless at 60x |
| Drift alert | PSI > 0.2 for 3 h vs a 7-day baseline |
| Red team | 10 of 10 ASI attacks defended |

**Ask of a pilot site.** One entrance, one checkout bank, three shelves, an edge box the site owns, four weeks; gates: false alerts < 5 per camera per day, approval rate >= 60 %, then service level >= 90 % and OSA >= 98 %. Software stays under USD 50 a month; inference stays at zero on-prem.

**Links.** Live: https://raqib-orcin.vercel.app · API: https://raqib-backend-7qdg.onrender.com/docs · Repo: https://github.com/krish2105/RAQIB-AI-in-Operations · Threat model: docs/security/threat_model.md
