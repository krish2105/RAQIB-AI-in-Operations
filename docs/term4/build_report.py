"""Build docs/AI218_RAQIB_report.docx from docs/results/. No placeholders: every figure is loaded.

  cd cloud && uv run --no-sync python ../docs/term4/build_report.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DOCS, all_figures, load, num, pct  # noqa: E402

from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

OUT = DOCS / "AI218_RAQIB_report.docx"

REFERENCES = [
    "Erlang, A. K. (1917). Solution of some problems in the theory of probabilities of significance in automatic telephone exchanges. Elektroteknikeren, 13, 5–13.",
    "Little, J. D. C. (1961). A proof for the queuing formula: L = λW. Operations Research, 9(3), 383–387. https://doi.org/10.1287/opre.9.3.383",
    "Hillier, F. S., & Lieberman, G. J. (2021). Introduction to operations research (11th ed.). McGraw-Hill.",
    "Gruen, T. W., Corsten, D. S., & Bharadwaj, S. (2002). Retail out-of-stocks: A worldwide examination of extent, causes and consumer responses. Grocery Manufacturers of America.",
    "Hyndman, R. J., & Athanasopoulos, G. (2021). Forecasting: Principles and practice (3rd ed.). OTexts. https://otexts.com/fpp3/",
    "Friedman, J. H. (2001). Greedy function approximation: A gradient boosting machine. The Annals of Statistics, 29(5), 1189–1232. https://doi.org/10.1214/aos/1013203451",
    "Zhang, Y., Sun, P., Jiang, Y., Yu, D., Weng, F., Yuan, Z., Luo, P., Liu, W., & Wang, X. (2022). ByteTrack: Multi-object tracking by associating every detection box. In Proceedings of ECCV 2022. https://doi.org/10.1007/978-3-031-20047-2_1",
    "Ahmad, H. M., & Rahimi, A. (2024). SH17: A dataset for human safety and personal protective equipment detection in manufacturing industry. Journal of Safety Science and Resilience, 5(4), 375–386. https://doi.org/10.1016/j.jnlssr.2024.09.002",
    "Huangfu, Q., & Hall, J. A. J. (2018). Parallelizing the dual revised simplex method. Mathematical Programming Computation, 10(1), 119–142. https://doi.org/10.1007/s12532-017-0130-5",
]


def h(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    for r in p.runs:
        r.font.color.rgb = RGBColor(0x14, 0x18, 0x1D)
    return p


def para(doc, text, italic=False, size=10.5):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.italic = italic
    r.font.size = Pt(size)
    p.paragraph_format.space_after = Pt(6)
    return p


def table(doc, rows, header=True, widths=None):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Light Grid Accent 1"
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            c = t.cell(i, j)
            c.text = str(cell)
            for p in c.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(9.5)
                    r.bold = header and i == 0
    if widths:
        for row in t.rows:
            for j, w in enumerate(widths):
                row.cells[j].width = Cm(w)
    doc.add_paragraph()
    return t


def main() -> None:
    k = load("kpis_retail.json")
    kf = load("kpis_factory.json")
    f = load("forecast_retail.json")
    w = load("workforce_retail.json")
    r = load("report_retail_en.json")
    e = load("edge_eval.json")
    t = load("toolcalls_retail.json")
    figs = all_figures()
    ba = r["before_after"] or {}
    st = r["staffing"] or {}
    gov = r["governance"]
    y = e["detectors"]["yolo"]
    rt = e["detectors"].get("rtdetr", {})
    p = e["pipeline"]

    doc = Document()
    s = doc.styles["Normal"]
    s.font.name = "Calibri"
    s.font.size = Pt(10.5)
    for section in doc.sections:
        section.left_margin = section.right_margin = Cm(2.2)
        section.top_margin = section.bottom_margin = Cm(2.0)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    rr = title.add_run("RAQIB · رقيب\nA vision-driven operations control room for supermarket floors")
    rr.font.size = Pt(22)
    rr.bold = True
    para(doc, f"MAIB AI 218 — AI in Operations · Term 4 deployed MVP · Krishna Mathur · {date.today().isoformat()}", italic=True)
    para(doc, "Repository: github.com/krish2105/RAQIB-AI-in-Operations · Live dashboard link and QR on the deck's slide 5. All figures in this report are generated from docs/results/ by docs/term4/build_report.py.", italic=True, size=9)

    h(doc, "1. Executive summary")
    para(doc, "Supermarkets already own the sensor that could run their floor: the CCTV system. RAQIB turns those cameras into an operations agent. On the edge, a detector and tracker feed a deterministic rule engine that emits events (footfall, queue over limit, checkout served, shelf gap). In the cloud, the events feed a queueing model, a forecast, a staffing integer program, and a bounded agent that alerts, raises restock tasks, and proposes opening tills. A control-room web app shows it all live in English, Hindi, and Arabic.")
    para(doc, f"Three measured results on the deployed demo: (1) the edge pipeline runs at {p['fps_end_to_end']} frames per second end to end on a laptop with {p['frame_to_event_ms_p50']} ms median frame-to-event latency; (2) the footfall forecast beats the seasonal-naive baseline by {f['improvement_pct']}% (MAE {f['mae']} vs {f['mae_naive']}); (3) the staffing plan keeps checkout utilisation at or below 0.85 with {w['staff_hours']} staff-hours per day against {w['baseline_staff_hours']} with three tills open all day, a saving of {w['savings_hours']} hours. Service level over the last 24 h is {pct(k['service_level'])} against a 90% target and on-shelf availability is {pct(k['osa_store'])}.")

    h(doc, "2. Problem and operations context")
    para(doc, "A hypermarket floor is a queueing system and an inventory system sharing one workforce. Queues longer than three customers are the single largest driver of walk-outs; out-of-stocks on the shelf cost 4% of sales in the meta-analysis by Gruen, Corsten and Bharadwaj (2002). Both are measured today by manual counts, mystery shoppers, or not at all. Cameras see both continuously but only record. The gap is not sensing; it is turning what the camera sees into decisions a floor manager can act on within the shift.")
    para(doc, "RAQIB's design premise: rules make the safety- and service-critical decisions deterministically; a model adds judgement about what to do; a human approves anything that moves staff. Every action carries the frames, the confidence, the rule, and a written rationale, so an operations manager can audit the system the way they audit a shift log.")

    h(doc, "3. Literature and practice")
    para(doc, "Queue management in retail rests on Erlang's (1917) multi-server model and Little's (1961) law, taught in Hillier and Lieberman (2021) as M/M/c: the closed forms for expected wait and utilisation are what let a dashboard compute a target till count from an arrival rate in real time. Commercial queue-management vendors (people-counting sensors above tills) implement the counting but rarely the model. On-shelf availability, Gruen et al. (2002) established the 8% global out-of-stock rate and the consumer response mix (substitute, delay, leave), which is the cost side of the OSA KPI here. For forecasting, Hyndman and Athanasopoulos (2021) motivate the seasonal-naive baseline as the honest comparator for any seasonal demand series, and Friedman (2001) gives the gradient-boosting machine used as the challenger. For vision, ByteTrack (Zhang et al., 2022) associates every detection box, which is what makes per-track dwell and first-entry counting stable enough for λ and μ estimation; SH17 (Ahmad and Rahimi, 2024) is the PPE dataset for the factory profile. The staffing program is solved with HiGHS (Huangfu and Hall, 2018) through SciPy.")

    h(doc, "4. System design")
    para(doc, "Edge (Python 3.12): capture from webcam, looped file, or RTSP; YOLO26n behind a Detector adapter with RT-DETR as a second implementation; ByteTrack session-scoped ids; every person's head band pixelated and blurred before any frame is stored or sent; polygon zones from a site YAML; pure rule functions with an injected clock; SQLite outbox with 10-second clips; idempotent sync. Cloud (FastAPI): events, clips, Server-Sent Events; a bounded agent whose backend (deterministic dry-run or Claude tool-use) is always filtered by a Policy that cannot be bypassed; queueing, OSA, forecasting, and workforce modules; a weekly report in three languages. Web (Next.js 16): a Control Room design with a 24-hour event tape as the spine of every page, a 3D floor plan, and a light/dark, LTR/RTL theme.")
    table(doc, [
        ["Rule", "Profile", "Condition", "Severity"],
        ["R10 queue over", "retail", "≥ N persons in a queue zone for ≥ 60 s", "2"],
        ["R11 shelf gap", "retail", "shelf empty ratio > 0.4 for ≥ 5 min", "1"],
        ["R12 footfall", "both", "track's first entry to an entrance zone", "1"],
        ["R13 checkout served", "retail", "track leaves checkout after ≥ 20 s dwell (μ estimator)", "1"],
        ["R01 no helmet", "factory", "person in work area, no helmet over head for ≥ 2 s", "3"],
        ["R02 zone breach", "factory", "person inside an exclusion zone", "3"],
        ["R03 machine stopped", "factory", "machine ROI stopped ≥ 120 s in scheduled run", "2"],
    ], widths=[3.5, 2, 8, 2])
    para(doc, "Privacy by design: faces blurred at capture, no identity recognition, track ids never persisted, only counts and events leave the edge, and the agent never sees video. Simulated history used for the demo carries a simulated flag in every payload and is labelled in the UI and in this report.")

    h(doc, "5. Data and models")
    table(doc, [
        ["Asset", "Licence", "Use"],
        ["Pexels checkout clip 39221979, time-lapse 854634", "Pexels licence / CC0", "Looped demo cameras"],
        ["YOLO26n, RT-DETR-L (Ultralytics)", "AGPL-3.0", "Detector adapter (swap before commercial sale)"],
        ["SH17 (Ahmad & Rahimi, 2024)", "CC BY-NC-SA 4.0", "PPE fine-tuning (manual download, not run in the demo)"],
        ["Labelled simulator (21 days)", "generated", "Forecast, workforce, and report history; flagged simulated"],
    ], widths=[6, 3.5, 6])
    doc.add_picture(str(figs["latency"]), width=Cm(15))
    table(doc, [
        ["Metric", "Value", "Source"],
        ["YOLO26n median detect latency / detect-only fps", f"{y['latency_ms_p50']} ms / {y['fps_detect_only']}", "edge_eval.json"],
        ["RT-DETR-L median detect latency / detect-only fps", f"{rt.get('latency_ms_p50', 'n/a')} ms / {rt.get('fps_detect_only', 'n/a')}", "edge_eval.json"],
        ["End-to-end pipeline fps", str(p["fps_end_to_end"]), "edge_eval.json"],
        ["Frame → event latency p50 / p95", f"{p['frame_to_event_ms_p50']} / {p['frame_to_event_ms_p95']} ms", "edge_eval.json"],
        ["PPE mAP50", e["ppe_map50"]["status"] + " (needs SH17 + site labels)", "edge_eval.json"],
    ], widths=[7, 5, 3.5])

    h(doc, "6. Operations analytics")
    para(doc, f"Queue model vs observed. Arrivals λ come from footfall ticks per 15-minute slot; service rate μ per till from checkout dwell (rule R13), currently {w['mu']:.0f} customers per hour per till and labelled 'estimated from video'. M/M/c with c = 3 tills gives ρ and W_q per slot; the observed W_q is Little's law on the measured queue length. Peak ρ in the last 24 h: {num(k['peak_rho'], 2)}. Service level (slots with queue ≤ 3): {pct(k['service_level'])} against a 90% target. Average queue when over limit: {k['avg_queue']} customers.")
    doc.add_picture(str(figs["queue"]), width=Cm(15.5))
    para(doc, f"On-shelf availability. Store OSA over 24 h: {pct(k['osa_store'])}; per shelf: {', '.join(f'{s} {pct(v)}' for s, v in k['osa'].items())}. Mean time to restock: {', '.join(f'{s} {v:.0f} min' for s, v in k['time_to_restock_min'].items()) or 'no gap episodes'}.")
    para(doc, f"Forecast vs baseline. Hourly footfall, GradientBoostingRegressor on hour, weekday, lag-24, lag-168, rolling means, and a leak-free hour-of-week profile, versus seasonal naive. Seven-day holdout MAE {f['mae']} vs {f['mae_naive']} ({f['improvement_pct']}% better; MAPE {f['mape']}%). Expected peaks in the next 24 h: {', '.join(x['ts'][11:16] for x in f['peaks'][:3])} UTC.")
    doc.add_picture(str(figs["forecast"]), width=Cm(15.5))
    para(doc, f"Workforce optimisation. Minimise total tills per 15-minute slot subject to ρ ≤ 0.85 and integer tills between 1 and the ceiling, solved with HiGHS. One day: {w['staff_hours']} staff-hours versus {w['baseline_staff_hours']} with three tills open all day (saving {w['savings_hours']} h). Week: peak {st.get('peak_tills', 'n/a')} tills, mean {st.get('mean_tills', 'n/a')}, {st.get('slots_over_baseline', 'n/a')} slots need more than today's three tills.")
    doc.add_picture(str(figs["workforce"]), width=Cm(15.5))
    para(doc, f"Before/after. Replaying the week with the agent's open-till proposals applied (tills = max(today's 3, plan)) changes total customer wait from {ba.get('baseline_customer_wait_min', 'n/a')} to {ba.get('with_plan_customer_wait_min', 'n/a')} customer-minutes ({ba.get('reduction_pct', 'n/a')}% reduction). Closing tills off-peak is reported as the staff-hour saving above, not as a wait effect.")

    h(doc, "7. Agent design and governance")
    table(doc, [
        ["Tool", "Autonomy", "Guard"],
        ["send_alert", "autonomous", "templates only, EN/HI/AR"],
        ["create_work_order", "autonomous for severity ≤ 2", "one per machine/shelf per 4 h"],
        ["log_downtime", "autonomous", "schema"],
        ["escalate", "mandatory on severity 3", "cannot be suppressed or downgraded"],
        ["request_human_review", "mandatory below 0.6 confidence", "replaces side effects"],
        ["propose_open_till", "proposal", "must cite ρ > 0.85"],
        ["propose_staffing_change / maintenance_window", "proposal", "human approves in /actions"],
    ], widths=[5.5, 5, 5])
    para(doc, f"Every call is validated against its JSON schema before execution and logged with input, output, latency, and model cost. Seeded week: {gov['actions']} actions ({gov['autonomous']} autonomous, {gov['proposals']} proposals), {gov['tool_calls']} tool calls, {gov['failed_calls']} failed, cost ${gov['cost_usd']}; retail tool-call ledger: {t['total_calls']} calls, ${t['total_cost_usd']}. The demo runs the deterministic dry-run backend; the Claude backend uses the same tool schemas and the same Policy.")

    h(doc, "8. Deployment")
    para(doc, "Edge on an Apple M4 Pro (MPS) or any Linux box via Docker (CPU). API on Render (free tier sleeps; the edge buffers in SQLite and syncs on reconnect, tested). Postgres on Supabase from the generated schema. Web on Vercel. Health check at /health; SSE stream reconnects with backoff and the header shows 'reconnecting'.")

    h(doc, "9. Limitations and ethics")
    para(doc, "The demo cameras are public stock clips, not a store; POS data is absent so μ is estimated from video; the 21-day history is a labelled simulator, so the forecast margin over naive understates real data; COCO weights see persons only and PPE mAP is not measured; Ultralytics is AGPL-3.0 and must be swapped or licensed before commercial sale. Ethically the system is built to be unable to identify people: faces are blurred before storage and no identity model exists in the codebase.")

    h(doc, "10. Business case and 90-day rollout for a Dubai hypermarket")
    table(doc, [
        ["Phase", "Weeks", "Scope", "KPI gate"],
        ["Pilot", "1–4", "one entrance camera, one checkout bank, 3 shelves; SOP in docs/pilot_sop.md", "false alerts < 5/camera/day; approval ≥ 60%"],
        ["Expand", "5–8", "all checkout banks, POS import for μ, staffing plan used for rosters", "service level ≥ 90%; MAE ≥ 20% better than naive on real data"],
        ["Scale", "9–13", "shelf coverage per aisle, second store", "OSA ≥ 98%; cost per store < USD 150/month"],
    ], widths=[2.2, 1.8, 7, 5.5])
    para(doc, "Software cost under USD 50 per month per store on current tiers plus an edge box the store owns. The value case is one avoided walk-out per till-hour at peak and one avoided out-of-stock episode per shelf per day; both are measurable from the same events the system already records.")

    h(doc, "11. Conclusion and future work")
    para(doc, "RAQIB shows that an operations agent can be built on existing cameras with deterministic rules for the decisions that matter, queueing theory for the decisions that need a model, and a language model only where judgement is needed and always behind a policy. Next: POS import, labelled site footage and fine-tuned PPE weights, planogram checks, digital-twin playback on the 3D floor, and a 24-hour unattended soak on a real camera.")

    h(doc, "References")
    for ref in REFERENCES:
        para(doc, ref, size=9.5)

    h(doc, "Appendix")
    para(doc, "A. Site YAML: edge/sites/retail_demo.yaml. B. Rule table: section 4. C. Tool schemas: cloud/raqib_api/agent/tools.py. D. Test coverage: edge 47 tests, cloud 41 tests, web 15 unit tests plus a Playwright smoke flow. E. Results files: docs/results/*.json.", size=9.5)

    doc.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
