"""Security posture: the OWASP ASI scorecard (latest harness result), red-team runs, and the memory-guard log."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..auth.deps import current_principal, require
from ..auth.rbac import Principal
from ..db import get_session
from ..models import Action, AgentRun, Memory, MemorySnapshot

router = APIRouter(prefix="/security", tags=["security"])
RESULTS = Path(__file__).resolve().parents[3] / "docs" / "results" / "security_eval.json"
ASI_DOC = Path(__file__).resolve().parents[3] / "docs" / "security" / "asi_mapping.md"


def load_scorecard() -> dict:
    if not RESULTS.exists():
        return {"date": None, "passed": 0, "failed": 0, "total": 0, "results": []}
    try:
        return json.loads(RESULTS.read_text())
    except json.JSONDecodeError:
        return {"date": None, "passed": 0, "failed": 0, "total": 0, "results": [], "error": "unreadable results file"}


@router.get("/scorecard")
def scorecard(_: Principal = Depends(current_principal)) -> dict:
    """The committed result of the last `security/run.py` run (CI gates on it)."""
    data = load_scorecard()
    return {**data, "source": "docs/results/security_eval.json", "mapping_doc": "docs/security/asi_mapping.md"}


@router.get("/redteam")
def redteam_runs(_: Principal = Depends(current_principal)) -> dict:
    """The attack tests as a list of runs (one entry per ASI risk) with their evidence."""
    data = load_scorecard()
    runs = [{"asi": r["asi"], "risk": r["risk"], "test": r["test"], "passed": r["passed"], "seconds": r.get("evidence", {}).get("seconds"),
             "evidence": {k: v for k, v in r.get("evidence", {}).items() if k != "seconds"}, "error": r.get("error")} for r in data.get("results", [])]
    return {"date": data.get("date"), "runs": runs, "command": "cd cloud && uv run python security/run.py --gate --md"}


@router.get("/memory-guard")
def memory_guard(site: str = Query(...), limit: int = Query(50, le=200), p: Principal = Depends(require("manage")), session: Session = Depends(get_session)) -> dict:
    """What the memory guard refused or quarantined, plus snapshots available for rollback."""
    if not p.may_see(site):
        raise HTTPException(403, "site not allowed")
    q = session.exec(select(Memory).where(Memory.site == site, Memory.quarantined == True).order_by(Memory.ts.desc()).limit(limit)).all()  # noqa: E712
    quarantines = [a for a in session.exec(select(Action).where(Action.site == site, Action.tool == "quarantine_memory").order_by(Action.created_at.desc()).limit(limit)).all()]
    snaps = session.exec(select(MemorySnapshot).where(MemorySnapshot.site == site).order_by(MemorySnapshot.taken_at.desc()).limit(10)).all()
    return {
        "site": site,
        "quarantined": [{"id": m.id, "agent": m.agent, "key": m.key, "reason": m.quarantine_reason, "written_by": m.written_by, "source": m.source, "ts": m.ts.isoformat(), "preview": m.value[:120]} for m in q],
        "quarantine_actions": [{"id": a.id, "ts": a.created_at.isoformat(), "agent": a.agent, "args": a.args} for a in quarantines],
        "snapshots": [{"id": s.id, "ts": s.taken_at.isoformat(), "count": s.entries, "taken_by": s.taken_by} for s in snaps],
    }


@router.get("/audit")
def audit_findings(site: str = Query(...), limit: int = Query(50, le=200), p: Principal = Depends(require("manage")), session: Session = Depends(get_session)) -> dict:
    """Runs the Auditor flagged (tool misuse, budget anomalies, disagreement spikes)."""
    if not p.may_see(site):
        raise HTTPException(403, "site not allowed")
    flagged = session.exec(select(AgentRun).where(AgentRun.site == site, AgentRun.status == "flagged").order_by(AgentRun.started.desc()).limit(limit)).all()
    return {"site": site, "flagged": [{"id": r.id, "agent": r.agent, "trigger": r.trigger, "started": r.started.isoformat(), "flag": (r.meta or {}).get("flag")} for r in flagged]}
