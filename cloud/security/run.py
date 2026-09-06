"""Red-team harness: runs the ten ASI attack tests against an in-process API with a fresh SQLite store, writes
docs/results/security_eval.json and a markdown scorecard; --gate exits 1 on any failure.

  cd cloud && uv run python security/run.py --gate --md
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("EMBED_MODEL", "fake:64")
os.environ.setdefault("LLM_PROVIDER", "groq")
os.environ.setdefault("LLM_PROVIDER_ORDER", "groq")
os.environ.setdefault("AUTH_REQUIRED", "false")

from security.scorecard import ASI, AttackResult  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MODULES = ["asi01_goal_hijack", "asi02_tool_misuse", "asi03_identity", "asi04_supply_chain", "asi05_code_execution", "asi06_memory_poisoning",
           "asi07_inter_agent", "asi08_cascading", "asi09_human_trust", "asi10_rogue_agent"]


def build_ctx():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, create_engine

    from raqib_api import db as dbmod
    from raqib_api.config import settings

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    dbmod.engine = eng
    settings.embed_model = "fake:64"
    settings.llm_provider = "groq"
    settings.llm_provider_order = "groq"
    from fastapi.testclient import TestClient

    from raqib_api.main import app

    client = TestClient(app)
    client.__enter__()
    return {"engine": eng, "client": client}


def run_all(only: set[str] | None = None) -> list[AttackResult]:
    ctx = build_ctx()
    results = []
    for name in MODULES:
        asi = name[:5].upper()
        if only and asi not in only:
            continue
        t0 = time.perf_counter()
        try:
            mod = importlib.import_module(f"security.attacks.{name}")
            r = mod.run(ctx)
        except Exception as exc:  # noqa: BLE001 — a crashing attack is a failed control, never a hidden one
            r = AttackResult(asi, name, False, error=f"{exc.__class__.__name__}: {exc}"[:300])
        r.evidence["seconds"] = round(time.perf_counter() - t0, 2)
        results.append(r)
        print(f"{r.asi} {'PASS' if r.passed else 'FAIL'} {ASI[r.asi][0]:24s} {r.evidence.get('seconds')}s {r.error or ''}", flush=True)
    ctx["client"].__exit__(None, None, None)
    return results


def markdown(results: list[AttackResult]) -> str:
    lines = ["| ASI | Risk | Control | Attack test | Result |", "|---|---|---|---|---|"]
    for r in results:
        risk, control = ASI[r.asi]
        lines.append(f"| {r.asi} | {risk} | {control} | {r.name} | {'pass' if r.passed else 'FAIL'} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "docs/results/security_eval.json"))
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    results = run_all({x.strip().upper() for x in a.only.split(",") if x.strip()} or None)
    passed = sum(1 for r in results if r.passed)
    out = {"date": datetime.now(UTC).isoformat(), "passed": passed, "failed": len(results) - passed, "total": len(results),
           "results": [r.as_dict() for r in results]}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(f"\n{passed}/{len(results)} passed -> {a.out}")
    if a.md:
        print(markdown(results))
    return 1 if (a.gate and passed < len(results)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
