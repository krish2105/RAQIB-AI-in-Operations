# Demo video script v2 — 4 minutes, English, narrated

Continues docs/demo_script.md (the three-minute v1 cut). Numbers are read from docs/results/ at build time.

**0:00–0:25 · Ask.** Press `/`, type "Which till had the longest queue last Friday evening?" Watch the stages stream: route, retrieve, answer. Click a citation chip; the event page opens. Switch to Hindi, ask the same. "Every sentence cites a record. 30 trilingual cases, 0 hallucinations, $0 of inference."

**0:25–0:55 · Watch.** The camera wall, heads blurred before the stream (10.8 fps at the client). Open a queue event, press Request opinion: the VLM agrees at 0.9. Open a severity-3 breach where it disagreed: the severity did not move. "A second opinion can ask for a human. It cannot lower a severity."

**0:55–1:35 · Crew.** Roster with budgets, the run graph, the signed message log. Post a queue event: FloorOps lights, proposes till 2 with evidence, the Auditor checks it in 0.005 s. Type KILL: every agent route returns 503, the deterministic path still escalates severity 3. Resume.

**1:35–2:05 · Twin.** Pick yesterday, Play at 60x; the floor breathes with the day (1440 bins). Move the tills slider: the wait and staff-hour delta update. Save as scenario, then ask Ask about it.

**2:05–2:35 · Settings, Shelves, Fleet.** Import the labelled POS sample; the queue model's mu switches to POS. Shelves: planogram compliance and a price-tag mismatch. Fleet: the leaderboard, a drift panel that suggests a fix, edge health from heartbeats.

**2:35–3:20 · Security.** The ASI scorecard: 10 of 10 attacks defended, each with its evidence. Edit the till-proposal threshold as Admin: the diff, the note, the confirmation, the attribution. Sign in as an Operator: read-only. The memory-guard log shows what was quarantined.

**3:20–4:00 · Close.** "Same cameras, same events, same policy. v2 adds judgement in six narrow agents, a memory that can be rolled back, a twin to test decisions before making them, and a red-team gate that runs on every push. Cost of inference: zero. RAQIB."
