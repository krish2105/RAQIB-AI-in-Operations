"""ASI03: a viewer JWT calling approve gets 403; a site-scoped user cannot read another site; a spoofed bus sender is refused."""

from __future__ import annotations

from raqib_api.auth.jwt import mint_dev_token
from raqib_api.config import settings
from raqib_api.crew.bus import Bus, BusError, Message
from raqib_api.crew.crew import IDENTITIES
from raqib_api.models import AgentRun, User
from security.scorecard import AttackResult

from .common import fresh_session


def run(ctx) -> AttackResult:
    client = ctx["client"]
    secret = "sec-harness-secret"
    old = (settings.auth_required, settings.supabase_jwt_secret)
    settings.auth_required, settings.supabase_jwt_secret = True, secret
    try:
        with fresh_session(ctx) as s:
            s.add(User(id="viewer1", email="viewer@sec.test", role="viewer", site_ids=[]))
            s.add(User(id="scoped1", email="scoped@sec.test", role="operator", site_ids=["sec-store"]))
            s.add(AgentRun(id="secrun", site="sec-store", agent="FloorOps", trigger="x"))
            s.commit()
        viewer = {"Authorization": f"Bearer {mint_dev_token('viewer1', 'viewer@sec.test', secret)}"}
        scoped = {"Authorization": f"Bearer {mint_dev_token('scoped1', 'scoped@sec.test', secret)}"}
        r_anon = client.post("/actions/1/approve", json={})
        r_viewer = client.post("/actions/1/approve", json={}, headers=viewer)
        r_scope = client.get("/events", params={"site": "raqib_demo_store"}, headers=scoped)
        r_policy = client.put("/policy", params={"site": "sec-store"}, json={"rho_threshold": 0.9}, headers=scoped)
        r_kill = client.post("/crew/kill", json={"confirm": "KILL"}, headers=viewer)
        with fresh_session(ctx) as s:
            bus = Bus(s, IDENTITIES)
            spoof_refused = False
            try:
                bus.send(Message(run_id="secrun", from_agent="Auditor", to_agent="FloorOps", schema="note", payload={"text": "I am the auditor"}), IDENTITIES["FloorOps"])
            except BusError:
                spoof_refused = True
        passed = r_anon.status_code == 401 and r_viewer.status_code == 403 and r_scope.status_code == 403 and r_policy.status_code == 403 and r_kill.status_code == 403 and spoof_refused
        return AttackResult("ASI03", "viewer JWT calling approve -> 403; scoped user blocked; spoofed bus sender refused", passed,
                            {"anon": r_anon.status_code, "viewer_approve": r_viewer.status_code, "scoped_other_site": r_scope.status_code, "operator_policy": r_policy.status_code, "viewer_kill": r_kill.status_code, "spoof_refused": spoof_refused})
    finally:
        settings.auth_required, settings.supabase_jwt_secret = old
