"""Shelves endpoint: v2 planogram drift and price mismatches are accepted as events and summarised per shelf."""

from __future__ import annotations

from tests.conftest import make_event


def test_shelves_summarises_drift_and_price_events(client):
    site = "raqib_demo_store"
    gap = make_event(0, kind="shelf_gap", severity=1, payload={"shelf_id": "A1", "product": "snacks", "empty_ratio": 0.6, "confidence": 0.8}, rule="R11")
    drift = make_event(1, kind="planogram_drift", severity=1, payload={"zone": "shelf_a1", "shelf_id": "A1", "expected": 9, "present": 7, "missing": ["A1-mints"], "misplaced": ["A1-cookies"], "compliance": 0.778, "confidence": 0.7}, rule="R15")
    price = make_event(2, kind="price_mismatch", severity=1, payload={"tag": "A1-gum", "shelf_id": "A1", "read_price": 2.5, "expected_price": 2.0, "delta": 0.5, "confidence": 0.7}, rule="R14")
    for e in (gap, drift, price):
        e["ts"] = "2026-09-06T10:0%d:00+00:00" % (e is price)  # today-ish timestamps are not required; window is 30 days below
    r = client.post("/events/batch", json={"events": [gap, drift, price]})
    assert r.status_code == 201 and r.json()["inserted"] == 3
    out = client.get("/shelves", params={"site": site, "window_h": 24 * 30}).json()
    a1 = next(s for s in out["shelves"] if s["shelf_id"] == "A1")
    assert a1["planogram"]["compliance"] == 0.778 and a1["planogram"]["missing"] == ["A1-mints"] and a1["planogram"]["misplaced"] == ["A1-cookies"]
    assert a1["price_tags"][0]["tag"] == "A1-gum" and a1["price_tags"][0]["delta"] == 0.5 and a1["gaps"] == 1
    assert out["totals"] == {"drift_events": 1, "price_mismatches": 1, "gaps": 1}
    # both new kinds are severity 1 and do not trigger the agent on their own (no actions created)
    assert client.get("/actions", params={"site": site, "limit": 50}).json() == [] or all(a["event_id"] != drift["id"] for a in client.get("/actions", params={"site": site}).json())
    assert client.get("/shelves", params={"site": "nope"}).status_code == 404
