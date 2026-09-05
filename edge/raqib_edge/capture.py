"""Frame capture and face blurring.

`FrameSource` wraps OpenCV for webcam, file (looped) and RTSP inputs and yields
(timestamp, frame) pairs at a target rate.

`blur_faces` is the privacy gate. It runs on every frame before the frame is
drawn, stored in a clip, or sent anywhere. Design choice (stated assumption):
we do not run a face detector at all. Every detected person gets the top band
of their box (where the head is) pixelated and blurred, unconditionally. A face
detector can miss; a head band cannot. The cost is a blurred hat or hair, which
is fine for an operations tool that never needs identity.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime

import cv2
import numpy as np

XYXY = tuple[float, float, float, float]

HEAD_BAND = 0.28  # fraction of the person box height treated as head


class FrameSource:
    """Iterate frames from a webcam index, a video file (looping), or an RTSP URL."""

    def __init__(self, uri: str | int, loop: bool = True, target_fps: float | None = None) -> None:
        self.uri = uri
        self.loop = loop and not isinstance(uri, int) and not str(uri).startswith("rtsp")
        self.target_fps = target_fps
        self._cap: cv2.VideoCapture | None = None
        self.loops = 0

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self.uri)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open video source {self.uri!r}")

    @property
    def fps(self) -> float:
        assert self._cap is not None
        f = self._cap.get(cv2.CAP_PROP_FPS)
        return float(f) if f and f > 0 else 25.0

    @property
    def size(self) -> tuple[int, int]:
        assert self._cap is not None
        return (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    def frames(self) -> Iterator[tuple[datetime, np.ndarray]]:
        if self._cap is None:
            self.open()
        assert self._cap is not None
        interval = 1.0 / self.target_fps if self.target_fps else 0.0
        last = 0.0
        while True:
            ok, frame = self._cap.read()
            if not ok:
                if self.loop:
                    self.loops += 1
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break
            if interval:
                now = time.perf_counter()
                wait = interval - (now - last)
                if wait > 0:
                    time.sleep(wait)
                last = time.perf_counter()
            yield datetime.now(UTC), frame
        self.release()

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def blur_faces(frame: np.ndarray, person_boxes: list[XYXY], strength: int = 31) -> np.ndarray:
    """Return a copy of `frame` with the head band of every person box anonymised."""
    out = frame.copy()
    h, w = out.shape[:2]
    k = strength if strength % 2 == 1 else strength + 1
    for x1, y1, x2, y2 in person_boxes:
        x1i, y1i = max(0, int(x1)), max(0, int(y1))
        x2i, y2i = min(w, int(x2)), min(h, int(y2))
        if x2i - x1i < 4 or y2i - y1i < 8:
            continue
        head_bottom = y1i + max(8, int((y2i - y1i) * HEAD_BAND))
        _anonymise(out, x1i, y1i, x2i, min(head_bottom, y2i), k)
    return out


def _anonymise(img: np.ndarray, x1: int, y1: int, x2: int, y2: int, k: int) -> None:
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    region = img[y1:y2, x1:x2]
    # Pixelate then blur: cheap, and not reversible by simple deconvolution.
    small = cv2.resize(
        region, (max(1, (x2 - x1) // 12), max(1, (y2 - y1) // 12)), interpolation=cv2.INTER_LINEAR
    )
    pix = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
    img[y1:y2, x1:x2] = cv2.GaussianBlur(pix, (k, k), 0)
