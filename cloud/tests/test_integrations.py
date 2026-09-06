"""WhatsApp templates only; Greenlam idempotency, retries and circuit breaker; opt-in roster; integration status."""

from __future__ import annotations

import json

import httpx
import pytest

from raqib_api.greenlam import CircuitBreaker, CircuitOpen, GreenlamClient
from raqib_api.integrations.whatsapp import (
    Recipient,
    TemplateOnly,
    WhatsAppClient,
    send_alert_to_roster,
)


def _wa(handler):
    return WhatsAppClient(phone_number_id="12345", token="tok", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_whatsapp_sends_approved_templates_only():
    seen = []

    def handler(req: httpx.Request):
        seen.append(json.loads(req.content))
        assert req.headers["authorization"] == "Bearer tok" and req.url.path.endswith("/12345/messages")
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    wa = _wa(handler)
    out = wa.send_template("971500000000", "queue_over", "hi", {"zone": "queue_till_1", "count": 7, "time": "18:30"})
    assert out["message_id"] == "wamid.1" and out["template"] == "raqib_queue_over"
    body = seen[0]
    assert body["type"] == "template" and body["template"]["language"]["code"] == "hi"
    assert [p["text"] for p in body["template"]["components"][0]["parameters"]] == ["queue_till_1", "7", "18:30"]
    assert "text" not in body  # never a free-text message
    with pytest.raises(TemplateOnly):
        wa.send("971500000000", "hello there")
    with pytest.raises(TemplateOnly):
        wa.send_text("971500000000", "hello there")
    with pytest.raises(TemplateOnly):
        wa.send_template("971500000000", "made_up_template", "en", {})
    with pytest.raises(TemplateOnly):
        wa.send_template("971500000000", "queue_over", "fr", {})
    assert not WhatsAppClient(phone_number_id=None, token=None).enabled


def test_roster_filters_by_role_and_uses_recipient_language():
    sent = []

    def handler(req: httpx.Request):
        b = json.loads(req.content)
        sent.append((b["to"], b["template"]["language"]["code"]))
        return httpx.Response(200, json={"messages": [{"id": f"wamid.{len(sent)}"}]})

    roster = [Recipient("971500000001", "floor_manager", "hi"), Recipient("971500000002", "safety_officer", "ar"), Recipient("971500000003", "floor_manager", "en")]
    out = send_alert_to_roster(_wa(handler), roster, "queue_over", "en", {"zone": "q", "count": 5, "time": "10:00"}, role="floor_manager")
    assert sent == [("971500000001", "hi"), ("971500000003", "en")] and all("message_id" in x for x in out)


def _greenlam(handler, **kw):
    return GreenlamClient("https://tracker.test/api", "E100", "123456", client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None, **kw)


def test_same_idempotency_key_is_not_duplicated():
    posts = []

    def handler(req: httpx.Request):
        if req.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "t"})
        if req.url.path == "/api/tickets" and req.method == "POST":
            posts.append(json.loads(req.content)["id"])
            return httpx.Response(201, json={"id": posts[-1], "ticket_no": f"PR-{len(posts)}", "stage": "raised"})
        return httpx.Response(404)

    from uuid import uuid4

    key = uuid4()
    c = _greenlam(handler)
    a = c.raise_ticket(1, "stop", "Medium", client_id=key)
    b = c.raise_ticket(1, "stop", "Medium", client_id=key)
    assert a["ticket_no"] == "PR-1" and b["ticket_no"] == "PR-1" and b["deduplicated"] is True and len(posts) == 1
    c.raise_ticket(1, "another", "Medium")
    assert len(posts) == 2


def test_retries_on_5xx_then_succeeds_and_409_is_success():
    calls = {"n": 0}

    def handler(req: httpx.Request):
        if req.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "t"})
        if req.url.path == "/api/tickets" and req.method == "POST":
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(503)
            return httpx.Response(201, json={"id": json.loads(req.content)["id"], "ticket_no": "PR-9", "stage": "raised"})
        if req.url.path.startswith("/api/tickets/"):
            return httpx.Response(200, json={"id": req.url.path.rsplit("/", 1)[1], "ticket_no": "PR-EXISTING", "stage": "raised"})
        return httpx.Response(404)

    c = _greenlam(handler)
    out = c.raise_ticket(1, "stop", "Medium")
    assert out["ticket_no"] == "PR-9" and out["attempts"] == 3 and c.breaker.state == "closed"

    def conflict(req: httpx.Request):
        if req.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "t"})
        if req.method == "POST":
            return httpx.Response(409)
        return httpx.Response(200, json={"id": "x", "ticket_no": "PR-EXISTING", "stage": "raised"})

    assert _greenlam(conflict).raise_ticket(1, "stop", "Medium")["ticket_no"] == "PR-EXISTING"


def test_breaker_opens_after_three_failures_and_half_opens_after_cooldown():
    now = [1000.0]
    br = CircuitBreaker(failures=3, cooldown_s=60, clock=lambda: now[0])

    def down(req: httpx.Request):
        if req.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "t"})
        return httpx.Response(502)

    c = _greenlam(down, retries=1, breaker=br)
    for _ in range(3):
        with pytest.raises(httpx.HTTPStatusError):
            c.raise_ticket(1, "stop", "Medium")
    assert br.state == "open"
    with pytest.raises(CircuitOpen):
        c.raise_ticket(1, "stop", "Medium")  # refused without touching the tracker
    now[0] += 61
    assert br.state == "half_open"
    with pytest.raises(httpx.HTTPStatusError):
        c.raise_ticket(1, "probe", "Medium")  # the single probe fails -> open again
    assert br.state == "open"
    now[0] += 61
    ok = [0]

    def up(req: httpx.Request):
        if req.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "t"})
        ok[0] += 1
        return httpx.Response(201, json={"id": json.loads(req.content)["id"], "ticket_no": "PR-OK", "stage": "raised"})

    c2 = _greenlam(up, retries=1, breaker=br)
    assert c2.raise_ticket(1, "probe", "Medium")["ticket_no"] == "PR-OK" and br.state == "closed"


def test_optins_and_status_api(client, monkeypatch):
    r = client.post("/notify/optins", json={"site": "s1", "phone": "+971 50 000 0001", "role": "floor_manager", "lang": "hi"})
    assert r.status_code == 201 and r.json()["created"]
    assert client.post("/notify/optins", json={"site": "s1", "phone": "971500000001", "role": "floor_manager"}).json()["created"] is False
    rows = client.get("/notify/optins", params={"site": "s1"}).json()
    assert rows[0]["phone"] == "…0001" and rows[0]["lang"] == "hi"
    assert client.post("/notify/optins", json={"site": "s1", "phone": "abc", "role": "floor_manager"}).status_code == 422
    assert client.delete(f"/notify/optins/{rows[0]['id']}").json()["opted_out"] and client.get("/notify/optins", params={"site": "s1"}).json() == []
    st = client.get("/integrations/status").json()
    assert st["whatsapp"]["free_text"] is False and st["greenlam"]["retries"] == 3 and "queue_over" in st["whatsapp"]["templates"]
    assert st["whatsapp"]["configured"] is False


def test_send_alert_whatsapp_channel_is_template_only_and_skips_when_unconfigured(client):
    from sqlmodel import Session

    from raqib_api import db as dbmod
    from raqib_api.agent.tools import Call, ToolRunner

    with Session(dbmod.engine) as s:
        res = ToolRunner(s, "s1", "test").execute(Call("send_alert", {"channel": "whatsapp", "lang": "ar", "template": "queue_over", "vars": {"zone": "q", "count": 4, "time": "10:00"}}))
    assert res.ok and res.output["whatsapp"] == {"skipped": "not configured"} and "console" in res.output["delivered"]
