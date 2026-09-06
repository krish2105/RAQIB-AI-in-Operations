"""Edge telemetry to the cloud: a heartbeat every minute (fps, temperature, sync queue depth, model hash) and one
drift sample per camera every two minutes (mean detection count, mean confidence, brightness, blur over that
window; the cloud's PSI needs about 60 samples per two-hour window). Boxes only, never pixels."""

from __future__ import annotations

import hashlib
import logging
import platform
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

log = logging.getLogger(__name__)
VERSION = "0.2.0"


def model_hash(weights: str | Path | None) -> str:
    """SHA-256 of the weights file (what the box is actually running); empty when unknown."""
    if not weights or not Path(weights).exists():
        return ""
    h = hashlib.sha256()
    with Path(weights).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cpu_temp_c() -> float | None:
    """Best effort: Linux thermal zones (Jetson, Pi); macOS exposes nothing without extra tooling."""
    try:
        for p in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
            v = float(p.read_text().strip())
            return v / 1000.0 if v > 1000 else v
    except Exception:  # noqa: BLE001
        pass
    return None


def frame_stats(frame: np.ndarray) -> tuple[float, float]:
    """(brightness, blur): mean grey level and Laplacian variance (low = blurred / dirty lens)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return float(gray.mean()), float(cv2.Laplacian(gray, cv2.CV_64F).var())


@dataclass
class HourAgg:
    det: list[float] = field(default_factory=list)
    conf: list[float] = field(default_factory=list)
    bright: list[float] = field(default_factory=list)
    blur: list[float] = field(default_factory=list)

    def add(self, tracks: list[Any], frame: np.ndarray) -> None:
        self.det.append(float(len(tracks)))
        if tracks:
            self.conf.append(float(np.mean([t.conf for t in tracks])))
        b, bl = frame_stats(frame)
        self.bright.append(b)
        self.blur.append(bl)

    def sample(self, site: str, camera: str, ts: datetime) -> dict[str, Any]:
        mean = lambda xs, d=0.0: float(np.mean(xs)) if xs else d  # noqa: E731
        return {"site": site, "camera": camera, "ts": ts.isoformat(), "det_count": mean(self.det), "mean_conf": mean(self.conf),
                "brightness": mean(self.bright), "blur": mean(self.blur)}


class Telemetry:
    def __init__(self, api_url: str, site: str, box_id: str | None = None, weights: str | Path | None = None, detector: str = "",
                 client=None, heartbeat_every_s: float = 60.0, drift_every_s: float = 120.0, sample_every_frames: int = 30, timeout: float = 5.0) -> None:
        import httpx

        self.api_url = api_url.rstrip("/")
        self.site = site
        self.box_id = box_id or platform.node().split(".")[0] or "edge"
        self.model_hash = model_hash(weights)
        self.detector = detector
        self.client = client or httpx.Client(timeout=timeout)
        self.heartbeat_every_s, self.drift_every_s, self.sample_every_frames = heartbeat_every_s, drift_every_s, sample_every_frames
        self._last_hb = 0.0
        self._last_drift = time.monotonic()
        self._n = 0
        self._agg: dict[str, HourAgg] = {}
        self.heartbeats = 0
        self.drift_posts = 0
        self.failed = 0

    def observe(self, camera: str, tracks: list[Any], blurred_frame: np.ndarray) -> None:
        self._n += 1
        if self._n % self.sample_every_frames == 0:
            self._agg.setdefault(camera, HourAgg()).add(tracks, blurred_frame)

    def maybe_send(self, fps: float, queue_depth: int, cameras: list[str], force: bool = False) -> dict[str, bool]:
        now = time.monotonic()
        out = {"heartbeat": False, "drift": False}
        if force or now - self._last_hb >= self.heartbeat_every_s:
            self._last_hb = now
            out["heartbeat"] = self._post("/fleet/heartbeat", {"site": self.site, "box_id": self.box_id, "ts": datetime.now(UTC).isoformat(), "fps": round(fps, 2),
                                                               "temp_c": cpu_temp_c(), "queue_depth": int(queue_depth), "model_hash": self.model_hash,
                                                               "detector": self.detector, "version": VERSION, "cameras": cameras,
                                                               "meta": {"platform": platform.platform()}})
            if out["heartbeat"]:
                self.heartbeats += 1
        if (force or now - self._last_drift >= self.drift_every_s) and self._agg:
            self._last_drift = now
            ts = datetime.now(UTC)
            samples = [agg.sample(self.site, cam, ts) for cam, agg in self._agg.items() if agg.det]
            self._agg = {}
            if samples:
                out["drift"] = self._post("/fleet/drift", samples)
                if out["drift"]:
                    self.drift_posts += 1
        return out

    def _post(self, path: str, body: Any) -> bool:
        try:
            r = self.client.post(f"{self.api_url}{path}", json=body)
            r.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001 — telemetry is best effort
            self.failed += 1
            if self.failed in (1, 10, 100):
                log.warning("telemetry post %s failed (%d): %s", path, self.failed, exc)
            return False


def git_describe() -> str:
    try:
        return subprocess.check_output(["git", "describe", "--always", "--dirty"], text=True, timeout=2).strip()
    except Exception:  # noqa: BLE001
        return VERSION
