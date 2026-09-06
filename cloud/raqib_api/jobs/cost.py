"""Cost per site per day: the sum of persisted LLM spans (requests, tokens, dollars per provider) plus tool-call cost."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from ..models import LlmSpan, ToolCall


def daily_cost(session: Session, site: str | None, days: int = 7, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    q = select(LlmSpan).where(LlmSpan.ts >= start.replace(tzinfo=None))
    if site:
        q = q.where(LlmSpan.site.in_([site, "-"]))
    spans = session.exec(q).all()
    tq = select(ToolCall).where(ToolCall.created_at >= start.replace(tzinfo=None))
    if site:
        tq = tq.where(ToolCall.site == site)
    calls = session.exec(tq).all()
    by_day: dict[str, dict[str, Any]] = {}
    for i in range(days):
        d = (start + timedelta(days=i)).date().isoformat()
        by_day[d] = {"day": d, "requests": 0, "tokens_in": 0, "tokens_out": 0, "llm_usd": 0.0, "tool_usd": 0.0, "usd": 0.0, "providers": {}}
    for s in spans:
        d = s.ts.date().isoformat()
        if d not in by_day:
            continue
        row = by_day[d]
        row["requests"] += 1
        row["tokens_in"] += s.tokens_in
        row["tokens_out"] += s.tokens_out
        row["llm_usd"] += s.cost_usd
        pv = row["providers"].setdefault(s.provider, {"requests": 0, "tokens": 0, "usd": 0.0})
        pv["requests"] += 1
        pv["tokens"] += s.tokens_in + s.tokens_out
        pv["usd"] += s.cost_usd
    for c in calls:
        d = c.created_at.date().isoformat()
        if d in by_day:
            by_day[d]["tool_usd"] += c.cost_usd
    for row in by_day.values():
        row["usd"] = round(row["llm_usd"] + row["tool_usd"], 6)
        row["llm_usd"] = round(row["llm_usd"], 6)
        row["tool_usd"] = round(row["tool_usd"], 6)
        for pv in row["providers"].values():
            pv["usd"] = round(pv["usd"], 6)
    days_list = list(by_day.values())
    today = days_list[-1]
    return {"site": site, "days": days, "today": today, "total_usd": round(sum(r["usd"] for r in days_list), 6),
            "total_requests": sum(r["requests"] for r in days_list), "total_tokens": sum(r["tokens_in"] + r["tokens_out"] for r in days_list),
            "by_day": days_list, "spans_today": sum(1 for s in spans if s.ts.date() == date.fromisoformat(today["day"]))}
