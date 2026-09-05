from datetime import UTC, datetime

import httpx

from raqib_edge.events import new_event
from raqib_edge.store import EventStore
from raqib_edge.sync import Syncer


def make_store(tmp_path, n=3):
    st = EventStore(tmp_path / "e.db")
    for i in range(n):
        st.append(new_event("s", "cam1", datetime(2026, 9, 6, 1, 0, i, tzinfo=UTC), "footfall_tick", 1, {}, "R12"))
    return st


def test_offline_then_online(tmp_path):
    st = make_store(tmp_path)
    calls = {"n": 0, "bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        calls["bodies"].append(request.read())
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(201, json={"inserted": 3})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    s = Syncer(st, "http://api.test", client=client)
    assert s.push_once() == 0
    assert s.online is False
    assert len(st.unsynced()) == 3
    assert s.push_once() == 3
    assert s.online is True
    assert st.unsynced() == []
    assert b'"events"' in calls["bodies"][1] and b'"rule_id":"R12"' in calls["bodies"][1]


def test_connection_error_keeps_events(tmp_path):
    st = make_store(tmp_path, 2)

    def handler(request):
        raise httpx.ConnectError("no route")

    s = Syncer(st, "http://api.test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert s.push_once() == 0
    assert len(st.unsynced()) == 2


def test_clip_uploaded_after_events(tmp_path):
    st = make_store(tmp_path, 1)
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"\x00" * 100)
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        return httpx.Response(201, json={"inserted": 1})

    s = Syncer(st, "http://api.test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    s.queue_clip(st.unsynced()[0].id, str(clip))
    s.push_once()
    assert seen[0] == ("POST", "/events/batch")
    assert seen[1][0] == "PUT" and seen[1][1].startswith("/clips/")
