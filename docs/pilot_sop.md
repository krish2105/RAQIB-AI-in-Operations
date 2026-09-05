# Pilot SOP — one camera, one machine, four weeks

Standard operating procedure for the first MUSHRIF pilot at a Greenlam Laminates plant unit, and the equivalent RAQIB pilot in one supermarket. Written for the site engineer and the project owner.

## 0. Before day one

| Item | Owner | Done when |
|---|---|---|
| Signed privacy notice and entrance signage (`docs/privacy_notice.md`) | Site HR / manager | Signed copy in the pilot folder |
| One camera RTSP URL and credentials, one machine chosen | Site engineer | `rtsp://…` opens in VLC on the pilot box |
| Pilot box: Mac mini / M-series laptop or a Linux box with a GPU or a Jetson; Ethernet to the camera VLAN; internet for sync | Project owner | `uv run raqib-edge run --site sites/greenlam_unit1.yaml --preview` shows the feed |
| Site YAML: zones drawn on a saved frame (normalised 0–1), machine id matching the tracker's `machines.id`, scheduled hours | Project owner + engineer | `uv run pytest tests/test_zones.py` green with the new file |
| Tracker access: employee id + PIN for the RAQIB agent user in the Greenlam tracker (`GREENLAM_*` in `.env`) | Plant IT | A test ticket appears in the tracker sandbox |
| Cloud: API on Render, database on Supabase, dashboard on Vercel (`docs/architecture.md`) | Project owner | `/health` returns ok; dashboard loads |

## 1. Week 1 — record and label

1. Start the edge box in **record mode**: `raqib-edge run --site … --api <API_URL>`. Faces are blurred; events flow; no work orders yet (`AGENT_BACKEND=dryrun`, `GREENLAM_URL` empty).
2. With permission, record **two hours** of footage across two shifts (`ffmpeg -i rtsp://… -t 7200 -c copy site_footage.mp4`) for labelling.
3. Label helmet / vest / person on ~600 frames (Roboflow or CVAT). Export YOLO format to `edge/data/datasets/site_ppe/`.
4. Daily: open the dashboard, skim the event stream, note false alerts in `docs/pilot_log.md` (date, event id, what it really was).

## 2. Week 2 — tune

1. Fine-tune: `uv run python training/train_ppe.py --epochs 30` (SH17 + site frames). Record mAP50 in `docs/results/ppe_train.json`.
2. Adjust thresholds in the site YAML (`helmet_s`, `machine_stop_s`, `min_conf`, zone polygons) until false alerts per camera per day < 5 over three consecutive days.
3. Manual precision check: review 50 zone-breach clips; record precision in `docs/results/pilot_precision.json`. Target ≥ 0.90.

## 3. Week 3 — act

1. Set `GREENLAM_URL`, `GREENLAM_EMPLOYEE_ID`, `GREENLAM_PIN`. The agent now raises **real** work orders for `machine_stopped` (severity 2) and escalates severity-3 events to the safety officer with the clip.
2. Shift supervisor reviews `/actions` at shift end: approve or reject proposals. Approval rate is the acceptance KPI (target ≥ 60 %).
3. If a work order is wrong, reject it in the tracker and note the event id; the 4-hour cooldown prevents duplicates.

## 4. Week 4 — measure and decide

1. Run `scripts/export_results.py --api <API_URL>` and `edge/training/eval.py`. Regenerate the Monday report.
2. Compare: downtime minutes per week before vs during the pilot (tracker data), breaches per week, approval rate, false alerts per day, frame-to-alert latency.
3. Decision meeting with the plant head: continue to three cameras, or stop. Inputs: the report, `docs/results/`, and the pilot log.

## Daily checklist (5 minutes)

- Dashboard shows **Live** and the tape has today's trace.
- `/health` returns ok; `events` count increased since yesterday.
- Edge box log has no repeated `sync offline` warnings (Wi-Fi) or `cannot open video source` (camera).
- Clips exist for yesterday's severity-3 events.

## Incident handling

| Symptom | Action |
|---|---|
| Camera offline | Edge logs `cannot open video source`; check RTSP URL and VLAN; the box retries with backoff |
| API asleep (Render free tier) | Events queue in SQLite; the first request wakes the API; sync resumes within 30 s |
| False severity-3 escalation | Review clip on `/events/[id]`; mark in pilot log; adjust exclusion polygon or `min_conf` |
| Duplicate work orders | Should not happen (idempotent UUID + 4-hour cooldown); if it does, file an issue with both event ids |

## Roll-back

Stop the edge process. Nothing else changes: the tracker keeps its tickets, the dashboard keeps history, the cameras keep recording as before.

## Costs (pilot)

| Item | Monthly |
|---|---|
| Pilot box (existing laptop or a ~USD 200–700 box amortised) | 0–30 USD |
| Render small instance (free tier sleeps) | 0–7 USD |
| Supabase free tier | 0 |
| Vercel hobby | 0 |
| Claude API at ~50 actionable events/day with Sonnet | < 5 USD |
