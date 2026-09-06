"""Per-run budget: tool calls, dollars (0 in v2), wall-clock seconds."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..config import settings


class BudgetExceeded(RuntimeError):
    def __init__(self, what: str, limit, value) -> None:
        super().__init__(f"budget exceeded: {what} {value} > {limit}")
        self.what, self.limit, self.value = what, limit, value


@dataclass(frozen=True)
class Budget:
    max_tool_calls: int = 6
    max_usd: float = 0.0
    max_seconds: int = 60

    @classmethod
    def default(cls) -> Budget:
        return cls(settings.crew_max_tool_calls, settings.crew_max_usd, settings.crew_max_seconds)


@dataclass
class BudgetMeter:
    budget: Budget
    started: float = field(default_factory=time.perf_counter)
    tool_calls: int = 0
    usd: float = 0.0

    def check_time(self) -> None:
        elapsed = time.perf_counter() - self.started
        if elapsed > self.budget.max_seconds:
            raise BudgetExceeded("seconds", self.budget.max_seconds, round(elapsed, 1))

    def charge_call(self, usd: float = 0.0) -> None:
        self.tool_calls += 1
        self.usd += usd
        if self.tool_calls > self.budget.max_tool_calls:
            raise BudgetExceeded("tool_calls", self.budget.max_tool_calls, self.tool_calls)
        if self.usd > self.budget.max_usd + 1e-9:
            raise BudgetExceeded("usd", self.budget.max_usd, round(self.usd, 4))
        self.check_time()

    @property
    def seconds(self) -> float:
        return time.perf_counter() - self.started
