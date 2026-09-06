"""Blurred MJPEG stream and a boxes-only detections feed for the Watch tab.

Privacy: `MjpegServer.publish()` only ever receives frames that came out of the pipeline's blur gate
(`CameraWorker.last_frame`). Detections carry boxes, classes and session track ids, never pixels.
The stream is LAN-only by default (bind 127.0.0.1 unless --stream-host is set) and protected by
an optional token (`?token=`) so the cloud proxy is the only other consumer.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class _Latest:
    jpeg: dict[str, bytes] = field(default_factory=dict)
    ts: dict[str, float] = field(default_factory=dict)
    boxes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


class MjpegServer:
    """Serves GET /stream/<camera>[?token=] as multipart/x-mixed-replace and /boxes/<camera> as JSON."""

    def __init__(self, port: int = 8554, host: str = "127.0.0.1", token: str | None = None, quality: int = 75, max_side: int = 960,
                 fps: float = 12.0) -> None:
        self.port, self.host, self.token, self.quality, self.max_side, self.fps = port, host, token, quality, max_side, fps
        self.latest = _Latest()
        self.frames_published = 0
        srv = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def do_GET(self):  # noqa: N802
                u = urlparse(self.path)
                qs = parse_qs(u.query)
                if srv.token and qs.get("token", [None])[0] != srv.token:
                    self.send_response(401)
                    self.end_headers()
                    return
                parts = u.path.strip("/").split("/")
                if len(parts) == 2 and parts[0] == "stream":
                    return self._stream(parts[1])
                if len(parts) == 2 and parts[0] == "boxes":
                    return self._boxes(parts[1])
                if u.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok","cameras":%d}' % len(srv.latest.jpeg))
                    return
                self.send_response(404)
                self.end_headers()

            def _boxes(self, cam):
                import json

                with srv.latest.lock:
                    body = json.dumps({"camera": cam, "ts": srv.latest.ts.get(cam), "boxes": srv.latest.boxes.get(cam, [])}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _stream(self, cam):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                last = -1.0
                try:
                    while True:
                        with srv.latest.lock:
                            jpeg, ts = srv.latest.jpeg.get(cam), srv.latest.ts.get(cam, 0.0)
                        if jpeg is None or ts == last:
                            time.sleep(1.0 / max(srv.fps, 1.0) / 2)
                            continue
                        last = ts
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpeg))
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="raqib-mjpeg")
        self._last_pub: dict[str, float] = {}

    def start(self) -> MjpegServer:
        self._thread.start()
        log.info("blurred MJPEG stream on http://%s:%d/stream/<camera>", self.host, self.port)
        return self

    def publish(self, camera: str, blurred_frame: np.ndarray, boxes: list[dict[str, Any]] | None = None) -> bool:
        """Encode and expose the latest blurred frame at most `fps` times per second. Returns True when published."""
        now = time.monotonic()
        if now - self._last_pub.get(camera, 0.0) < 1.0 / max(self.fps, 1.0):
            return False
        f = blurred_frame
        h, w = f.shape[:2]
        s = min(1.0, self.max_side / max(h, w))
        if s < 1.0:
            f = cv2.resize(f, (int(w * s), int(h * s)))
        ok, buf = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
        if not ok:
            return False
        with self.latest.lock:
            self.latest.jpeg[camera] = bytes(buf)
            self.latest.ts[camera] = time.time()
            if boxes is not None:
                self.latest.boxes[camera] = boxes
        self._last_pub[camera] = now
        self.frames_published += 1
        return True

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def boxes_from_tracks(tracks, frame_wh: tuple[int, int]) -> list[dict[str, Any]]:
    """Normalised boxes (0..1) with class, confidence and the session-scoped track id. No pixels."""
    w, h = frame_wh
    out = []
    for t in tracks:
        x1, y1, x2, y2 = t.xyxy
        out.append({"id": int(t.track_id), "cls": t.cls, "conf": round(float(t.conf), 3),
                    "box": [round(x1 / w, 4), round(y1 / h, 4), round(x2 / w, 4), round(y2 / h, 4)]})
    return out


class DetectionsPoster:
    """Posts the latest boxes per camera to the cloud (`POST /detections`) at most every `every_s`."""

    def __init__(self, api_url: str, site: str, client=None, every_s: float = 1.0, timeout: float = 3.0) -> None:
        import httpx

        self.api_url = api_url.rstrip("/")
        self.site = site
        self.client = client or httpx.Client(timeout=timeout)
        self.every_s = every_s
        self._last: dict[str, float] = {}
        self.posted = 0
        self.failed = 0

    def maybe_post(self, camera: str, ts, boxes: list[dict[str, Any]], frame_wh: tuple[int, int]) -> bool:
        now = time.monotonic()
        if now - self._last.get(camera, 0.0) < self.every_s:
            return False
        self._last[camera] = now
        try:
            r = self.client.post(f"{self.api_url}/detections", json={"site": self.site, "camera": camera, "ts": ts.isoformat(),
                                                                       "w": frame_wh[0], "h": frame_wh[1], "boxes": boxes})
            r.raise_for_status()
            self.posted += 1
            return True
        except Exception as exc:  # noqa: BLE001 — the feed is best effort
            self.failed += 1
            if self.failed in (1, 10, 100):
                log.warning("detections post failed (%d): %s", self.failed, exc)
            return False
