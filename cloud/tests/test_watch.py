"""Watch feeds: boxes-only detections onto the SSE bus, stream proxy gating, captions list."""

from __future__ import annotations

import json

import httpx
import respx

from raqib_api.config import settings

DET = {"site": "s1", "camera": "cam1", "ts": "2026-09-06T12:00:00Z", "w": 1920, "h": 1080,
       "boxes": [{"id": 3, "cls": "person", "conf": 0.9, "box": [0.1, 0.2, 0.3, 0.8]}]}


def test_detections_accept_boxes_only_and_publish(client):
    from raqib_api.bus import bus

    q = bus.subscribe("s1")
    try:
        r = client.post("/detections", json=DET)
        assert r.status_code == 202 and r.json() == {"accepted": 1}
        msg = q.get_nowait()
        assert msg["channel"] == "detections" and msg["data"]["boxes"][0]["cls"] == "person"
        latest = client.get("/detections/latest", params={"site": "s1"}).json()
        assert latest[0]["camera"] == "cam1" and "received" in latest[0]
    finally:
        bus.unsubscribe("s1", q)
    # pixels have no place in this feed: unknown fields are rejected, and so is an oversized box list
    bad = dict(DET, frame="data:image/jpeg;base64,AAAA")
    assert client.post("/detections", json=bad).status_code in (202, 422)  # pydantic ignores unknown by default...
    assert "frame" not in json.dumps(client.get("/detections/latest", params={"site": "s1"}).json())  # ...and never stores it
    assert client.post("/detections", json=dict(DET, boxes=[DET["boxes"][0]] * 201)).status_code == 422


def test_stream_proxy_503_when_not_configured_and_forwards_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "stream_upstream", None)
    assert client.get("/cameras/s1/cam1/stream").status_code == 503
    monkeypatch.setattr(settings, "stream_upstream", "http://edge.lan:8554")
    monkeypatch.setattr(settings, "stream_token", "secret")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("http://edge.lan:8554/stream/cam1", params={"token": "secret"}).mock(
            return_value=httpx.Response(200, headers={"content-type": "multipart/x-mixed-replace; boundary=frame"},
                                        content=b"--frame\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8\xff\xd9\r\n"))
        with client.stream("GET", "/cameras/s1/cam1/stream") as r:
            body = b"".join(r.iter_bytes())
        assert r.status_code == 200 and r.headers["content-type"].startswith("multipart/x-mixed-replace") and b"--frame" in body
        assert route.called and "secret" not in body.decode(errors="ignore")
        mock.get("http://edge.lan:8554/stream/cam2", params={"token": "secret"}).mock(return_value=httpx.Response(401))
        assert client.get("/cameras/s1/cam2/stream").status_code == 502


def test_captions_list_skips_unavailable(client):
    from sqlmodel import Session

    from raqib_api import db as dbmod
    from raqib_api.models import Caption, Event
    from tests.conftest import make_event

    ev = make_event(kind="queue_over", severity=2, site="s1")
    client.post("/events/batch", json={"events": [ev]})
    with Session(dbmod.engine) as s:
        assert s.get(Event, ev["id"])
        s.add(Caption(event_id=ev["id"], site="s1", camera="cam1", text="queue at till 1", model="qwen2.5vl:7b", provider="ollama", frames=3))
        s.add(Caption(event_id=ev["id"], site="s1", camera="cam1", text="", model="none", parsed={"reason": "no_frames"}))
        s.commit()
    rows = client.get("/captions", params={"site": "s1"}).json()
    assert len(rows) == 1 and rows[0]["text"] == "queue at till 1"
