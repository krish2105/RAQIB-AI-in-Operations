"""Blurred MJPEG stream and boxes-only detections: privacy and protocol checks without a detector."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from datetime import UTC, datetime

import httpx
import numpy as np

from raqib_edge.events import Track
from raqib_edge.stream import DetectionsPoster, MjpegServer, boxes_from_tracks


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _frame(v=0):
    f = np.zeros((120, 160, 3), dtype=np.uint8)
    f[:, :, 1] = v
    return f


def test_mjpeg_stream_serves_latest_blurred_frames_and_boxes():
    port = _free_port()
    srv = MjpegServer(port=port, token="t0k", fps=50).start()
    stop = threading.Event()

    def pump():  # the pipeline keeps publishing blurred frames while clients read
        i = 0
        while not stop.is_set():
            srv.publish("cam1", _frame(i % 200), [{"id": 1, "cls": "person", "conf": 0.9, "box": [0.1, 0.1, 0.3, 0.6]}])
            i += 1
            time.sleep(0.01)

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    try:
        # token required
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/stream/cam1", timeout=2)
            raise AssertionError("expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401
        sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        sock.sendall(b"GET /stream/cam1?token=t0k HTTP/1.0\r\nHost: x\r\n\r\n")
        buf = b""
        deadline = time.time() + 3
        while buf.count(b"--frame") < 3 and time.time() < deadline:
            buf += sock.recv(65536)
        sock.close()
        assert b"multipart/x-mixed-replace" in buf and buf.count(b"--frame") >= 3 and b"\xff\xd8\xff" in buf  # JPEG SOI
        boxes = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/boxes/cam1?token=t0k", timeout=2))
        assert boxes["boxes"][0]["cls"] == "person" and "box" in boxes["boxes"][0]
        assert srv.frames_published >= 3
    finally:
        stop.set()
        t.join(timeout=1)
        srv.close()


def test_publish_is_rate_limited_to_fps():
    srv = MjpegServer(port=_free_port(), fps=5)
    assert srv.publish("c", _frame()) and not srv.publish("c", _frame())  # second call within 200 ms is dropped


def test_boxes_are_normalised_and_carry_no_pixels():
    t = Track(track_id=7, cls="person", conf=0.87, xyxy=(16.0, 12.0, 80.0, 108.0))
    b = boxes_from_tracks([t], (160, 120))
    assert b == [{"id": 7, "cls": "person", "conf": 0.87, "box": [0.1, 0.1, 0.5, 0.9]}]


def test_detections_poster_batches_and_survives_failures():
    seen = []

    def handler(req: httpx.Request):
        seen.append(json.loads(req.content))
        return httpx.Response(503) if len(seen) == 1 else httpx.Response(200, json={"ok": True})

    poster = DetectionsPoster("http://api", "s1", client=httpx.Client(transport=httpx.MockTransport(handler)), every_s=0.0)
    ts = datetime(2026, 9, 6, tzinfo=UTC)
    assert poster.maybe_post("cam1", ts, [], (160, 120)) is False and poster.failed == 1
    assert poster.maybe_post("cam1", ts, [{"id": 1, "cls": "person", "conf": 0.5, "box": [0, 0, 1, 1]}], (160, 120)) is True
    assert seen[1]["site"] == "s1" and seen[1]["w"] == 160 and seen[1]["boxes"][0]["cls"] == "person"
    assert "jpeg" not in json.dumps(seen[1]) and "frame" not in json.dumps(seen[1])
