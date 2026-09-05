"""Ultralytics YOLO (YOLO26 default) detector. Licence: AGPL-3.0."""

from __future__ import annotations

import numpy as np

from ..events import Det, Track
from ._ultralytics_common import results_to_dets, results_to_tracks

# COCO person class id; restricting `classes=` at inference skips 79 other heads.
_PERSON = 0


class YoloDetector:
    name = "yolo"

    def __init__(self, conf: float = 0.25, imgsz: int = 640) -> None:
        self.conf = conf
        self.imgsz = imgsz
        self._model = None
        self._device = "cpu"
        self._names: dict[int, str] = {}
        self._classes: list[int] | None = None

    def load(self, weights: str, device: str) -> None:
        from ultralytics import YOLO

        self._model = YOLO(weights)
        self._device = device
        self._names = dict(self._model.names)
        # Only restrict classes for COCO weights; fine-tuned PPE weights keep everything.
        if self._names.get(0) == "person" and len(self._names) == 80:
            self._classes = [_PERSON]

    def detect(self, frame: np.ndarray) -> list[Det]:
        assert self._model is not None, "call load() first"
        res = self._model.predict(
            frame, conf=self.conf, imgsz=self.imgsz, device=self._device, verbose=False, classes=self._classes
        )[0]
        return results_to_dets(res, self._names)

    def track(self, frame: np.ndarray) -> list[Track]:
        assert self._model is not None, "call load() first"
        res = self._model.track(
            frame,
            conf=self.conf,
            imgsz=self.imgsz,
            device=self._device,
            verbose=False,
            persist=True,
            tracker="bytetrack.yaml",
            classes=self._classes,
        )[0]
        return results_to_tracks(res, self._names)
