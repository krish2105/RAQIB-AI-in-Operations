import httpx

from raqib_api.greenlam import GreenlamClient, priority_for_severity


def test_raise_ticket_matches_tracker_contract():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/api/auth/login":
            body = req.read()
            assert b'"employee_id":"E100"' in body and b'"pin":"123456"' in body
            return httpx.Response(200, json={"access_token": "tok123", "token_type": "bearer"})
        if req.url.path == "/api/tickets":
            assert req.headers["authorization"] == "Bearer tok123"
            import json

            b = json.loads(req.read())
            assert isinstance(b["machine_id"], int) and b["priority"] in ("Low", "Medium", "High", "Critical")
            assert b["raised_via"] == "web" and b["input_language"] == "en" and len(b["id"]) == 36
            assert b["downtime_type"] in ("breakdown", "planned", "changeover", "no_downtime")
            return httpx.Response(201, json={"id": b["id"], "ticket_no": "PR-2609-0001", "stage": "raised", "machine_code": "PR-01"})
        return httpx.Response(404)

    c = GreenlamClient("https://tracker.test/api", "E100", "123456", client=httpx.Client(transport=httpx.MockTransport(handler)))
    out = c.raise_ticket(machine_id=1, description="Press 1 stopped 12 min", priority=priority_for_severity(2), location="press_1_roi")
    assert out["ticket_no"] == "PR-2609-0001" and out["tracker"] == "greenlam" and out["priority"] == "Medium"
    assert [r.url.path for r in seen] == ["/api/auth/login", "/api/tickets"]


def test_expired_token_is_refreshed_once():
    calls = {"tickets": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": f"t{calls['tickets']}"})
        calls["tickets"] += 1
        if calls["tickets"] == 1:
            return httpx.Response(401)
        return httpx.Response(201, json={"id": "x", "ticket_no": "PR-1", "stage": "raised"})

    c = GreenlamClient("https://tracker.test", "E1", "000000", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert c.raise_ticket(1, "x", "Critical")["ticket_no"] == "PR-1"
    assert calls["tickets"] == 2


def test_priority_mapping():
    assert priority_for_severity(1) == "Low" and priority_for_severity(2) == "Medium" and priority_for_severity(3) == "Critical"
