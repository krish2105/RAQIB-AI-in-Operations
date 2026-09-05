from datetime import UTC, datetime

from conftest import make_event

from raqib_api.agent.backends import DryRunBackend
from raqib_api.models import Event
from raqib_api.notify import available, render_alert


def test_dryrun_proposes_open_till_only_when_rho_high():
    e = Event(id="01AAAAAAAAAAAAAAAAAAAAAAAB", site="demo", camera="cam1", ts=datetime(2026, 9, 6, 18, 0, tzinfo=UTC),
              kind="queue_over", severity=2, payload={"zone": "queue_till_1", "count": 6, "sustained_s": 75, "confidence": 0.8}, rule_id="R10")
    d_low = DryRunBackend().decide(e, {"rho": 0.5, "tills": 3, "next_till": 2, "window": "18:00-18:30", "lang": "en"})
    assert [c.tool for c in d_low.calls] == ["send_alert"]
    assert "0.50" in d_low.rationale and "R10" in d_low.rationale
    d_high = DryRunBackend().decide(e, {"rho": 0.92, "tills": 3, "next_till": 2, "window": "18:00-18:30", "lang": "en"})
    assert [c.tool for c in d_high.calls] == ["send_alert", "propose_open_till"]
    assert d_high.calls[1].args["rho"] == 0.92


def test_alert_templates_exist_for_every_template_and_language():
    av = available()
    assert set(av) == {"en", "hi", "ar"}
    for lang, names in av.items():
        assert set(names) == set(av["en"]), lang
    text = render_alert("queue_over", "ar", {"zone": "queue_till_1", "count": 5, "time": "18:05"})
    assert "5" in text and "queue_till_1" in text
    assert render_alert("shelf_gap", "hi", {"shelf_id": "A1"}).count("-") >= 1  # missing vars render as '-'


def test_sev3_event_creates_executed_escalation_and_alert(client):
    ev = make_event(0, kind="zone_breach", severity=3, payload={"zone": "press_1_exclusion", "machine_id": 1, "track_id": 4, "confidence": 0.9}, rule="R02", site="greenlam_unit1")
    r = client.post("/events/batch", json={"events": [ev]})
    assert r.status_code == 201 and r.json()["actions_created"] >= 2
    acts = client.get("/actions", params={"site": "greenlam_unit1"}).json()
    tools = {a["tool"]: a for a in acts}
    assert tools["escalate"]["status"] == "executed" and tools["escalate"]["autonomous"] is True
    assert tools["send_alert"]["status"] == "executed"
    assert "MUSHRIF" in tools["send_alert"]["result"]["text"]
    calls = client.get("/toolcalls", params={"site": "greenlam_unit1"}).json()
    assert {c["tool"] for c in calls} >= {"escalate", "send_alert"}
    assert all(c["ok"] for c in calls)
    summary = client.get("/toolcalls/summary", params={"site": "greenlam_unit1"}).json()
    assert summary["total_calls"] >= 2


def test_queue_proposal_approve_and_reject_flow(client):
    # seed one hour of heavy arrivals so rho > 0.85 in the context, then a queue_over event
    base = datetime(2026, 9, 6, 18, 0, tzinfo=UTC)
    arrivals = [make_event(i, ts=base.replace(minute=i % 60, second=i // 60)) for i in range(140)]
    client.post("/events/batch", json={"events": arrivals})
    q = make_event(999, kind="queue_over", severity=2, payload={"zone": "queue_till_1", "till": 1, "count": 7, "sustained_s": 90, "confidence": 0.85}, rule="R10", ts=base.replace(minute=59, second=30))
    r = client.post("/events/batch", json={"events": [q]})
    assert r.json()["actions_created"] >= 2
    proposals = client.get("/actions", params={"status": "proposed"}).json()
    assert proposals and proposals[0]["tool"] == "propose_open_till"
    pid = proposals[0]["id"]
    ok = client.post(f"/actions/{pid}/approve", json={"by": "krishna", "note": "opening till 2"})
    assert ok.status_code == 200 and ok.json()["status"] == "executed" and ok.json()["decided_by"] == "krishna"
    assert client.post(f"/actions/{pid}/approve").status_code == 409
    # a second proposal path: reject
    q2 = make_event(1000, kind="queue_over", severity=2, payload={"zone": "queue_till_1", "till": 1, "count": 8, "sustained_s": 120, "confidence": 0.85}, rule="R10", ts=base.replace(minute=59, second=45))
    client.post("/events/batch", json={"events": [q2]})
    p2 = [a for a in client.get("/actions", params={"status": "proposed"}).json()]
    assert p2
    rej = client.post(f"/actions/{p2[0]['id']}/reject", json={"by": "krishna"})
    assert rej.json()["status"] == "rejected"
    assert client.get("/actions/999999").status_code == 404
