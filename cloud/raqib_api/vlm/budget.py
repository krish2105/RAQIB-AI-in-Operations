"""Daily budget for VLM opinions: a request cap on the shared Quota (key "vlm"), dollars stay 0."""

from __future__ import annotations

from ..config import settings
from ..llm import Quota

KEY = "vlm"


def opinion_quota(quota: Quota | None = None) -> Quota:
    q = quota if quota is not None else Quota.default()
    q.limits.setdefault(KEY, settings.vlm_daily_requests)
    return q


def can_spend(q: Quota) -> bool:
    return q.check(KEY)


def spend(q: Quota, tokens: int) -> None:
    q.record(KEY, tokens)
