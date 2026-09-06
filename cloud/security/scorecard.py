"""OWASP Top 10 for Agentic Applications (2026): ASI01-ASI10 mapped to a RAQIB control and an attack test."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ASI = {
    "ASI01": ("Goal hijack", "Policy-gated tools; retrieved content and memories are wrapped as data (<retrieved>, <memory>) and never instructions"),
    "ASI02": ("Tool misuse", "Per-agent tool allow-list enforced in the runtime before Policy; JSON-schema validation on every call"),
    "ASI03": ("Identity and privilege", "Supabase JWT verified server-side; roles viewer/operator/manager/admin; site scoping; HMAC-signed bus"),
    "ASI04": ("Supply chain", "Pinned dependencies (uv.lock, package-lock), pip-audit and npm audit in CI, weights hash pin (RAQIB_WEIGHTS_SHA256) and hash in heartbeats"),
    "ASI05": ("Code execution", "No shell or eval tools; tool arguments are validated data; the runner never spawns processes"),
    "ASI06": ("Memory poisoning", "Memory guard: injection quarantine, protected keys, secrets redaction, size and churn limits, snapshots and rollback"),
    "ASI07": ("Inter-agent trust", "Typed, schema-validated messages signed with a per-agent HMAC key; nonce and time-window replay protection"),
    "ASI08": ("Cascading failure", "Per-run budgets (calls, dollars, seconds), Greenlam circuit breaker, global kill switch with a deterministic fallback"),
    "ASI09": ("Human-agent trust", "Proposals must cite evidence (event and chunk ids) or are refused; VLM disagreement is a metric that never lowers severity"),
    "ASI10": ("Rogue agent", "Auditor after every run flags tool misuse, budget anomalies and disagreement spikes; per-agent telemetry"),
}


@dataclass
class AttackResult:
    asi: str
    name: str
    passed: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        risk, control = ASI[self.asi]
        return {"asi": self.asi, "risk": risk, "control": control, "test": self.name, "passed": self.passed, "evidence": self.evidence, "error": self.error}
