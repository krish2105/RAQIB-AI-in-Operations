"""Telemetry: heartbeat payload (fps, queue depth, model hash), hourly drift samples from boxes only, best-effort posting."""

from __future__ import annotations

import json

import httpx
import numpy as np

from raqib_edge.events import Track
from raqib_edge.telemetry import HourAgg, Telemetry, frame_stats, model_hash


def test_model_hash_and_frame_stats(tmp_path):
    w = tmp_path / "w.pt"
    w.write_bytes(b"weights" * 100)
    h = model_hash(w)
    assert len(h) == 64 and h == model_hash(w) and model_hash(None) == "" and model_hash(tmp_path / "missing") == ""
    flat = np.full((60, 80, 3), 120, np.uint8)
    noisy = np.random.RandomState(0).randint(0, 255, (60, 80, 3)).astype(np.uint8)
    b1, bl1 = frame_stats(flat)
    b2, bl2 = frame_stats(noisy)
    assert abs(b1 - 120) < 1 and bl1 < 1 and bl2 > bl1 * 100


def test_heartbeat_and_drift_posts_carry_no_pixels():
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.url.path, json.loads(req.content)))
        return httpx.Response(202, json={"accepted": True})

    tele = Telemetry("http://api", "s1", box_id="mac-1", client=httpx.Client(transport=httpx.MockTransport(handler)), detector="yolo", sample_every_frames=1)
    frame = np.full((60, 80, 3), 100, np.uint8)
    for i in range(5):
        tele.observe("cam1", [Track(track_id=i, cls="person", conf=0.8, xyxy=(0, 0, 10, 10))], frame)
    out = tele.maybe_send(fps=17.5, queue_depth=4, cameras=["cam1"], force=True)
    assert out == {"heartbeat": True, "drift": True} and tele.heartbeats == 1 and tele.drift_posts == 1
    paths = [p for p, _ in seen]
    assert paths == ["/fleet/heartbeat", "/fleet/drift"]
    hb = seen[0][1]
    assert hb["box_id"] == "mac-1" and hb["fps"] == 17.5 and hb["queue_depth"] == 4 and hb["detector"] == "yolo" and hb["cameras"] == ["cam1"]
    drift = seen[1][1]
    assert drift[0]["camera"] == "cam1" and drift[0]["det_count"] == 1.0 and abs(drift[0]["mean_conf"] - 0.8) < 1e-6 and drift[0]["brightness"] > 0
    assert "frame" not in json.dumps(seen) and "jpeg" not in json.dumps(seen)
    # nothing to send before the interval, and the aggregation was reset
    assert tele.maybe_send(fps=17.5, queue_depth=0, cameras=["cam1"]) == {"heartbeat": False, "drift": False}


def test_posting_failures_are_counted_not_raised():
    tele = Telemetry("http://api", "s1", box_id="b", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    out = tele.maybe_send(fps=1, queue_depth=0, cameras=[], force=True)
    assert out["heartbeat"] is False and tele.failed == 1 and tele.heartbeats == 0


def test_hour_agg_means():
    a = HourAgg()
    frame = np.full((20, 20, 3), 50, np.uint8)
    a.add([], frame)
    a.add([Track(1, "person", 0.6, (0, 0, 5, 5)), Track(2, "person", 1.0, (0, 0, 5, 5))], frame)
    s = a.sample("s1", "c", __import__("datetime").datetime(2026, 9, 6, tzinfo=__import__("datetime").UTC))
    assert s["det_count"] == 1.0 and abs(s["mean_conf"] - 0.8) < 1e-6 and s["camera"] == "c"
