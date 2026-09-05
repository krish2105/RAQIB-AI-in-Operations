"""RT-DETR detector via Ultralytics. Architecture Apache-2.0 (Baidu); this checkpoint AGPL-3.0.

Exists to prove the adapter: the pipeline runs unchanged with `--detector rtdetr`.
"""

from __future__ import annotations

import numpy as np

from ..events import Det, Track
from ._ultralytics_common import results_to_dets, results_to_tracks


class RtDetrDetector:
    name = "rtdetr"

    def __init__(self, conf: float = 0.4, imgsz: int = 640) -> None:
        self.conf = conf
        self.imgsz = imgsz
        self._model = None
        self._device = "cpu"
        self._names: dict[int, str] = {}

    def load(self, weights: str, device: str) -> None:
        from ultralytics import RTDETR

        self._model = RTDETR(weights)
        self._device = device
        self._names = dict(self._model.names)

    def detect(self, frame: np.ndarray) -> list[Det]:
        assert self._model is not None, "call load() first"
        res = self._model.predict(
            frame, conf=self.conf, imgsz=self.imgsz, device=self._device, verbose=False, classes=[0]
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
            classes=[0],
        )[0]
        return results_to_tracks(res, self._names)
