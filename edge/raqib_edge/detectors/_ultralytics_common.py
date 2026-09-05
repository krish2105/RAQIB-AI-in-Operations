"""Shared result conversion for Ultralytics-backed detectors (YOLO and RT-DETR)."""

from __future__ import annotations

from typing import Any

from ..events import Det, Track
from .base import KEEP_CLASSES


def results_to_dets(result: Any, names: dict[int, str]) -> list[Det]:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return []
    xyxy = boxes.xyxy.cpu().numpy()
    conf = boxes.conf.cpu().numpy()
    cls = boxes.cls.cpu().numpy().astype(int)
    out: list[Det] = []
    for (x1, y1, x2, y2), c, k in zip(xyxy, conf, cls, strict=True):
        label = names.get(int(k), str(k))
        if label not in KEEP_CLASSES:
            continue
        out.append(Det(cls=label, conf=float(c), xyxy=(float(x1), float(y1), float(x2), float(y2))))
    return out


def results_to_tracks(result: Any, names: dict[int, str]) -> list[Track]:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0 or boxes.id is None:
        return []
    xyxy = boxes.xyxy.cpu().numpy()
    conf = boxes.conf.cpu().numpy()
    cls = boxes.cls.cpu().numpy().astype(int)
    ids = boxes.id.cpu().numpy().astype(int)
    out: list[Track] = []
    for (x1, y1, x2, y2), c, k, tid in zip(xyxy, conf, cls, ids, strict=True):
        label = names.get(int(k), str(k))
        if label not in KEEP_CLASSES:
            continue
        out.append(
            Track(
                track_id=int(tid),
                cls=label,
                conf=float(c),
                xyxy=(float(x1), float(y1), float(x2), float(y2)),
            )
        )
    return out
