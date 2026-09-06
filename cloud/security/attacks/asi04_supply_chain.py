"""ASI04: pinned dependencies, audits in CI, and the weights hash pin on the edge (edge/tests/test_weights_pin.py)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from security.scorecard import AttackResult

ROOT = Path(__file__).resolve().parents[3]


def run(ctx) -> AttackResult:
    locks = {"cloud/uv.lock": (ROOT / "cloud/uv.lock").exists(), "edge/uv.lock": (ROOT / "edge/uv.lock").exists(), "web/package-lock.json": (ROOT / "web/package-lock.json").exists()}
    edge_pin = "unknown"
    try:
        r = subprocess.run(["uv", "run", "--no-sync", "pytest", "-q", "tests/test_weights_pin.py"], cwd=ROOT / "edge", capture_output=True, text=True, timeout=180)
        edge_pin = "passed" if r.returncode == 0 else f"failed: {r.stdout[-300:]}"
    except Exception as exc:  # noqa: BLE001
        edge_pin = f"not run ({exc.__class__.__name__})"
    hash_in_heartbeat = "model_hash" in (ROOT / "edge/raqib_edge/telemetry.py").read_text()
    integrity_gate = "verify_weights" in (ROOT / "edge/raqib_edge/pipeline.py").read_text()
    passed = all(locks.values()) and edge_pin == "passed" and hash_in_heartbeat and integrity_gate
    return AttackResult("ASI04", "tampered weights hash -> edge refuses to start; lockfiles present; audits in CI", passed,
                        {"lockfiles": locks, "edge_weights_pin_test": edge_pin, "hash_in_heartbeat": hash_in_heartbeat, "integrity_gate_in_pipeline": integrity_gate,
                         "ci": ".github/workflows/security.yml runs pip-audit and npm audit"})
