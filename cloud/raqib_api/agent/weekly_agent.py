"""Monday report: 7 days of KPIs, model vs observed, forecasts, staffing, before/after.

`build_report_data` is deterministic and fully testable. `recommend` is the only
part that touches a backend: DryRun uses a rule table; Claude writes from the
same numbers under prompts/weekly_agent.md. Rendering is Jinja, three languages.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlmodel import Session, select

from ..config import settings
from ..forecast import fit_predict, hourly_counts
from ..kpis import summary
from ..models import Action, Event, Site, ToolCall
from ..ops_theory import mmc, slot_rates, tills_for_target_rho
from ..tz import ensure_utc
from ..workforce import staffing_plan

TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "report"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(default=False), trim_blocks=True, lstrip_blocks=True)


def before_after(slots, mu: float, tills_now: int, plan_tills: list[int]) -> dict[str, Any]:
    """Customer wait over the day: current fixed tills vs the agent's open-till proposals applied.

    Proposals only ever *open* tills at peaks, so the "after" schedule is max(current, plan)
    per slot. Closing tills off-peak is the workforce lever and is reported as staff-hour
    savings, not as a wait-time effect.
    """
    plan_tills = [max(tills_now, c) for c in plan_tills]
    def total(tills_per_slot):
        tot = 0.0
        unstable = 0
        for s, c in zip(slots, tills_per_slot, strict=True):
            r = mmc(s.lam_per_h, mu, c)
            if r.stable:
                tot += r.wq * 60 * s.arrivals  # customer-minutes waited
            else:
                unstable += 1
                tot += 30 * s.arrivals  # cap: 30 min each when the queue explodes
        return round(tot, 1), unstable
    base, base_unstable = total([tills_now] * len(slots))
    after, after_unstable = total(plan_tills)
    return {"baseline_customer_wait_min": base, "with_plan_customer_wait_min": after,
            "reduction_pct": round((1 - after / base) * 100, 1) if base > 0 else 0.0,
            "baseline_unstable_slots": base_unstable, "plan_unstable_slots": after_unstable}


def build_report_data(site: str, session: Session, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    s = session.get(Site, site)
    if s is None:
        raise ValueError(f"site {site!r} not found")
    start = now - timedelta(days=7)
    # The report needs the last 7 days for `week` plus enough history before that for the
    # forecast to train (fit_predict needs >= MIN_DAYS span); fetch that bounded window
    # rather than the site's entire history (see routers/forecast.py's same reasoning).
    from ..routers.forecast import _FORECAST_LOOKBACK_DAYS

    fetch_since = now - timedelta(days=_FORECAST_LOOKBACK_DAYS)
    events = ensure_utc(
        session.exec(select(Event).where(Event.site == site, Event.ts >= fetch_since).order_by(Event.ts)).all()
    )
    week = [e for e in events if e.ts >= start]
    from ..routers.kpis import shelf_ids

    kp = summary(week, s.profile, s.tills, now, window_h=24 * 7, shelves=shelf_ids(session, site))
    top = sorted(week, key=lambda e: (-e.severity, e.ts))[:8]
    fc = fit_predict(hourly_counts(events, "footfall_tick", end=now), horizon=24)
    # The staffing plan and the before/after simulation cover the whole week of 15-min slots.
    slots = slot_rates(week, tills_open=s.tills)
    mus = [x.mu_per_h for x in slots if x.served > 0]
    mu = sum(mus) / len(mus) if mus else 30.0
    plan = None
    plan_dict = None
    if slots and s.profile == "retail":
        lam = [x.lam_per_h for x in slots]
        ceiling = max(s.tills, 3, tills_for_target_rho(max(lam), mu))
        plan = staffing_plan(lam, mu, max_tills=ceiling, baseline_tills=s.tills)
        by_day: dict[str, dict[str, float]] = {}
        for sl, c in zip(slots, plan.tills, strict=True):
            d0 = by_day.setdefault(sl.slot_start.date().isoformat(), {"staff_hours": 0.0, "peak_tills": 0, "slots": 0})
            d0["staff_hours"] += c * plan.slot_minutes / 60
            d0["peak_tills"] = max(d0["peak_tills"], c)
            d0["slots"] += 1
        plan_dict = {**plan.as_dict(), "by_day": {k: {**v, "staff_hours": round(v["staff_hours"], 2)} for k, v in by_day.items()},
                     "peak_tills": max(plan.tills), "mean_tills": round(sum(plan.tills) / len(plan.tills), 2),
                     "slots_over_baseline": sum(1 for c in plan.tills if c > s.tills)}
        # keep the JSON compact: the full per-slot vectors live in /workforce
        for k in ("tills", "lam", "rho", "wq_min"):
            plan_dict[k] = plan_dict[k][-96:]
    ba = before_after(slots, mu, s.tills, plan.tills) if plan else None
    actions = session.exec(select(Action).where(Action.site == site, Action.created_at >= start)).all()
    calls = session.exec(select(ToolCall).where(ToolCall.site == site, ToolCall.created_at >= start)).all()
    approved = sum(1 for a in actions if a.status == "executed" and a.decided_by not in (None, "agent"))
    proposals = sum(1 for a in actions if not a.autonomous)
    return {
        "site": site, "profile": s.profile, "period": {"start": start.date().isoformat(), "end": now.date().isoformat()},
        "generated_at": now.isoformat(), "kpis": kp, "top_events": [
            {"id": e.id, "ts": e.ts.isoformat(), "kind": e.kind, "severity": e.severity, "rule_id": e.rule_id, "payload": e.payload} for e in top],
        "forecast": fc.as_dict(), "staffing": plan_dict, "before_after": ba,
        "governance": {"actions": len(actions), "autonomous": sum(1 for a in actions if a.autonomous), "proposals": proposals,
                       "approved_by_human": approved, "approval_rate": round(approved / proposals, 3) if proposals else None,
                       "tool_calls": len(calls), "cost_usd": round(sum(c.cost_usd for c in calls), 4),
                       "failed_calls": sum(1 for c in calls if not c.ok)},
        "data_quality": {"simulated_share": kp.get("simulated_share", 0.0), "mu_source": "estimated_from_video"},
    }


NARRATIVE_QUESTIONS = {
    "en": [("Queues", "Which till had the biggest queue this week?"), ("Shelves", "Show me shelf gaps this week"), ("Footfall", "Which day had the highest footfall?")],
    "hi": [("कतारें", "इस हफ़्ते सबसे लंबी कतार कब थी?"), ("शेल्फ़", "इस हफ़्ते शेल्फ़ में कहाँ गैप थे?"), ("फुटफॉल", "किस दिन सबसे ज़्यादा footfall था?")],
    "ar": [("الطوابير", "ما هي أطول فترة انتظار هذا الأسبوع؟"), ("الرفوف", "أين كانت فجوات الرفوف هذا الأسبوع؟"), ("الزوار", "في أي يوم كان عدد الزوار هو الأعلى؟")],
}


def narrative_sections(site: str, session: Session, lang: str = "en", now: datetime | None = None) -> list[dict[str, Any]]:
    """Ask-generated report sections: each is a question, a cited answer and its citations. Empty when nothing is indexed."""
    from sqlmodel import func

    from ..models import Chunk
    from ..rag.answer import answer
    from ..rag.retriever import retrieve
    from ..rag.router_query import route_query

    now = now or datetime.now(UTC)
    if not session.exec(select(func.count()).select_from(Chunk).where(Chunk.site == site)).one():
        return []
    out = []
    for title, q in NARRATIVE_QUESTIONS.get(lang, NARRATIVE_QUESTIONS["en"]):
        plan = route_query(q, now)
        plan.lang = lang
        hits = retrieve(plan, site, session, k=6)
        a = answer(q, hits, lang, plan, now=now)
        out.append({"title": title, "question": q, "answer": a.text, "citations": [c.__dict__ for c in a.citations], "path": a.path,
                    "provider": a.provider, "confidence": a.confidence})
    return out


def recommend(data: dict[str, Any], backend: str | None = None) -> list[dict[str, Any]]:
    backend = backend or settings.agent_backend
    if backend == "claude" and settings.anthropic_api_key:
        try:
            return _recommend_claude(data)
        except Exception:  # noqa: BLE001 — fall back to the deterministic table
            pass
    return _recommend_rules(data)


def _recommend_rules(d: dict[str, Any]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    kp, plan, ba, fc = d["kpis"], d.get("staffing"), d.get("before_after"), d.get("forecast")
    if d["profile"] == "retail":
        if plan and ba:
            peak = max(range(len(plan["tills"])), key=lambda i: plan["lam"][i])
            recs.append({"title": f"Open {max(plan['tills'])} tills at the evening peak", "evidence": f"peak arrival rate {plan['lam'][peak]:.0f}/h drives utilisation {plan['rho'][peak]:.2f} at the planned tills; the MILP plan uses {plan['staff_hours']:.1f} staff-hours vs {plan['baseline_staff_hours']:.1f} flat", "expected_reduction": f"{ba['reduction_pct']:.0f}% less customer wait time ({ba['baseline_customer_wait_min']:.0f} to {ba['with_plan_customer_wait_min']:.0f} customer-minutes/day)"})
        worst = min(kp.get("osa", {}).items(), key=lambda kv: kv[1], default=None)
        if worst:
            ttr = kp.get("time_to_restock_min", {}).get(worst[0])
            recs.append({"title": f"Move shelf {worst[0]} to a 30-minute replenishment check", "evidence": f"on-shelf availability {worst[1]*100:.1f}% this week" + (f", mean time to restock {ttr:.0f} min" if ttr else ""), "expected_reduction": f"raise OSA on {worst[0]} toward the 98% target by cutting gap episodes roughly in half"})
        if fc and fc.get("sufficient") and fc.get("peaks"):
            hrs = ", ".join(p["ts"][11:16] for p in fc["peaks"][:3])
            recs.append({"title": "Pre-position one floater before forecast peaks", "evidence": f"next-24h footfall forecast peaks at {hrs} UTC; model MAE {fc['mae']} vs seasonal naive {fc['mae_naive']} ({fc['improvement_pct']}% better)", "expected_reduction": "avoid the first 5 minutes of queue build-up at each peak, worth about one severity-2 queue alert per peak"})
        if len(recs) < 3:
            recs.append({"title": "Enable the second camera on the dairy aisle", "evidence": "shelf B3 coverage relies on a single camera; gaps outside its field are not measured", "expected_reduction": "closes the measurement gap; no wait-time effect"})
    else:
        recs.append({"title": "Schedule a maintenance window for press 1", "evidence": f"{kp.get('downtime_min', 0):.0f} min unplanned downtime this week across {len(kp.get('stopped_machines', []))} machine(s)", "expected_reduction": "convert repeated short stops into one planned 60-minute window; expect 30-50% less unplanned downtime"})
        recs.append({"title": "Brief the shift on exclusion-zone breaches", "evidence": f"{kp.get('breaches', 0)} zone breaches and compliance {((kp.get('compliance') or 0) * 100):.1f}%", "expected_reduction": "target zero breaches; each breach is a severity-3 escalation"})
        recs.append({"title": "Label two hours of plant footage for PPE fine-tuning", "evidence": "COCO weights detect persons only; helmet detection needs SH17 fine-tuning plus site data", "expected_reduction": "moves PPE mAP50 toward the 0.80 target"})
    return recs[:3]


def _recommend_claude(d: dict[str, Any]) -> list[dict[str, Any]]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    system = (Path(__file__).resolve().parents[1] / "prompts" / "weekly_agent.md").read_text()
    slim = {k: d[k] for k in ("site", "profile", "period", "kpis", "staffing", "before_after", "governance", "data_quality")}
    slim["forecast"] = {k: d["forecast"].get(k) for k in ("sufficient", "mae", "mae_naive", "improvement_pct", "peaks")}
    tool = {"name": "recommendations", "description": "Return exactly three recommendations", "input_schema": {
        "type": "object", "properties": {"items": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "evidence": {"type": "string"}, "expected_reduction": {"type": "string"}}, "required": ["title", "evidence", "expected_reduction"]}}},
        "required": ["items"]}}
    resp = client.messages.create(model=settings.weekly_model, max_tokens=1200, system=system, tools=[tool],
                                  tool_choice={"type": "tool", "name": "recommendations"},
                                  messages=[{"role": "user", "content": "<untrusted_report_data>\n" + json.dumps(slim, default=str) + "\n</untrusted_report_data>"}])
    for b in resp.content:
        if getattr(b, "type", None) == "tool_use":
            return list(b.input["items"])[:3]
    raise RuntimeError("no tool output")


def render_markdown(data: dict[str, Any], recommendations: list[dict[str, Any]], lang: str = "en") -> str:
    tpl = _env.get_template(f"{lang}.md.j2")
    return tpl.render(d=data, recs=recommendations, pct=lambda x: "-" if x is None else f"{x*100:.1f}%", num=lambda x, n=1: "-" if x is None else f"{x:.{n}f}")
