"""RBAC: viewer 403 on approve; operator cannot edit policy; site-scoped user cannot read another site; unauthenticated /ask is 401; rate limits."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from raqib_api.auth.deps import RateLimiter
from raqib_api.auth.jwt import AuthError, mint_dev_token, verify
from raqib_api.auth.rbac import Principal
from raqib_api.config import settings
from raqib_api.models import User
from tests.conftest import make_event

SECRET = "test-jwt-secret-please-change"


@pytest.fixture()
def authed(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "auth_admin_emails", "owner@raqib.test")

    def as_user(sub: str, email: str, role: str | None = None, site_ids: list[str] | None = None):
        from raqib_api import db as dbmod

        if role is not None or site_ids is not None:
            with Session(dbmod.engine) as s:
                u = s.get(User, sub) or User(id=sub, email=email, role=role or "viewer", site_ids=site_ids or [])
                if role:
                    u.role = role
                if site_ids is not None:
                    u.site_ids = site_ids
                s.add(u)
                s.commit()
        return {"Authorization": f"Bearer {mint_dev_token(sub, email, SECRET)}"}

    return as_user


def test_verify_hs256_and_rejects_bad_tokens():
    tok = mint_dev_token("u1", "a@b.c", SECRET)
    c = verify(tok, secret=SECRET)
    assert c.sub == "u1" and c.email == "a@b.c"
    with pytest.raises(AuthError):
        verify(tok, secret="wrong")
    with pytest.raises(AuthError, match="expired"):
        verify(mint_dev_token("u1", "a@b.c", SECRET, ttl_s=-10), secret=SECRET)
    with pytest.raises(AuthError, match="not configured"):
        verify(tok, secret=None, jwks_url=None)


def test_roles_and_scoping_pure():
    v = Principal("1", "v@x", "viewer")
    assert v.can("read") and v.can("ask") and not v.can("approve") and not v.can("policy")
    op = Principal("2", "o@x", "operator", ("s1",))
    assert op.can("approve") and not op.can("manage") and op.may_see("s1") and not op.may_see("s2") and op.may_see(None)


def test_unauthenticated_ask_is_401_when_auth_required(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    assert client.post("/ask", json={"q": "queues today", "site": "raqib_demo_store"}).status_code == 401
    assert client.get("/events", params={"site": "raqib_demo_store"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_viewer_403_on_approve_operator_cannot_edit_policy_admin_can(client, authed):
    admin = authed("adm", "owner@raqib.test")  # first login -> admin via AUTH_ADMIN_EMAILS
    assert client.get("/auth/me", headers=admin).json()["role"] == "admin"
    # seed as admin, then create a proposal through the crew path
    client.post("/admin/seed", params={"site": "raqib_demo_store", "days": 2, "run_agent_last_hours": 0}, headers=admin)
    from tests.conftest import make_event as mk

    q = mk(kind="queue_over", severity=2, payload={"zone": "queue_till_1", "till": 1, "count": 8, "sustained_s": 120, "confidence": 0.9}, rule="R10")
    assert client.post("/events/batch", json={"events": [q]}, headers=admin).status_code == 201
    acts = client.get("/actions", params={"site": "raqib_demo_store", "status": "proposed"}, headers=admin).json()
    viewer = authed("v1", "viewer@raqib.test")  # default role viewer
    assert client.get("/auth/me", headers=viewer).json()["role"] == "viewer"
    assert client.get("/actions", params={"site": "raqib_demo_store"}, headers=viewer).status_code == 200
    if acts:
        assert client.post(f"/actions/{acts[0]['id']}/approve", json={"by": "viewer"}, headers=viewer).status_code == 403
    operator = authed("op1", "op@raqib.test", role="operator")
    assert client.put("/policy", params={"site": "raqib_demo_store"}, json={"rho_threshold": 0.9}, headers=operator).status_code == 403
    assert client.post("/crew/kill", json={"confirm": "KILL"}, headers=operator).status_code == 403
    assert client.post("/admin/seed", params={"site": "raqib_demo_store", "days": 1}, headers=operator).status_code == 403
    r = client.put("/policy", params={"site": "raqib_demo_store", "note": "peak season"}, json={"rho_threshold": 0.9}, headers=admin)
    assert r.status_code == 200 and r.json()["diff"]["rho_threshold"] == {"before": 0.85, "after": 0.9}
    assert client.get("/policy", params={"site": "raqib_demo_store"}, headers=viewer).json()["values"]["rho_threshold"] == 0.9
    users = client.get("/auth/users", headers=admin).json()
    assert {u["email"] for u in users} >= {"owner@raqib.test", "viewer@raqib.test", "op@raqib.test"}
    assert client.get("/auth/users", headers=viewer).status_code == 403
    assert client.patch("/auth/users/v1", json={"role": "operator"}, headers=admin).json()["role"] == "operator"
    assert client.get("/auth/me", headers=viewer).json()["role"] == "operator"


def test_site_scoped_user_cannot_read_another_site(client, authed):
    admin = authed("adm", "owner@raqib.test")
    e1 = make_event(0, site="raqib_demo_store", payload={"zone": "entrance"})
    e2 = make_event(1, site="greenlam_unit1", camera="cam1", payload={"zone": "entrance"})
    assert client.post("/events/batch", json={"events": [e1, e2]}, headers=admin).status_code == 201
    scoped = authed("s1", "store@raqib.test", role="operator", site_ids=["raqib_demo_store"])
    assert client.get("/events", params={"site": "greenlam_unit1"}, headers=scoped).status_code == 403
    assert client.get(f"/events/{e2['id']}", headers=scoped).status_code == 403
    ok = client.get("/events", params={"site": "raqib_demo_store", "limit": 5}, headers=scoped)
    assert ok.status_code == 200 and all(e["site"] == "raqib_demo_store" for e in ok.json())
    unscoped = client.get("/events", params={"limit": 50}, headers=scoped).json()
    assert unscoped and all(e["site"] == "raqib_demo_store" for e in unscoped)  # no site filter -> only their sites
    assert client.post("/ask", json={"q": "queues", "site": "greenlam_unit1"}, headers=scoped).status_code == 403
    assert client.post("/actions/999999/approve", json={}, headers=scoped).status_code == 404


def test_policy_thresholds_change_decisions(client):
    """An admin-raised rho threshold drops a proposal that the default would have allowed."""
    from datetime import UTC, datetime

    from sqlmodel import Session

    from raqib_api import db as dbmod
    from raqib_api.agent.policies import Policy
    from raqib_api.agent.tools import Call
    from raqib_api.models import Event

    ev = Event(id="01P" + "0" * 23, site="s9", camera="c", ts=datetime.now(UTC), kind="queue_over", severity=2, payload={"count": 5}, rule_id="R10")
    call = lambda: [Call("propose_open_till", {"till": 2, "window": "now", "rho": 0.88}, "x")]  # noqa: E731
    with Session(dbmod.engine) as s:
        assert [c.tool for c in Policy(s).check(ev, call(), 0.9).calls] == ["propose_open_till"]
    assert client.put("/policy", params={"site": "s9"}, json={"rho_threshold": 0.9}).status_code == 200
    with Session(dbmod.engine) as s:
        out = Policy(s).check(ev, call(), 0.9)
        assert out.calls == [] and "P4" in out.dropped[0][1]


def test_rate_limiter():
    rl = RateLimiter(3)
    t = 100.0
    assert all(rl.hit("u", t + i) for i in range(3)) and not rl.hit("u", t + 3) and rl.hit("v", t + 3)
    assert rl.hit("u", t + 61)


def test_ask_rate_limit_returns_429(client, monkeypatch):
    from raqib_api.routers import ask as ask_router

    monkeypatch.setattr(ask_router.ASK_LIMIT, "per_min", 2)
    monkeypatch.setattr(ask_router.ASK_LIMIT, "_hits", __import__("collections").defaultdict(__import__("collections").deque))
    codes = [client.post("/ask", json={"q": "queues today", "site": "raqib_demo_store"}).status_code for _ in range(3)]
    assert codes[:2] == [200, 200] and codes[2] == 429
