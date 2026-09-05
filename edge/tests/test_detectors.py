"""Detector adapter tests. These load real weights and run on MPS/CPU; ~10 s total."""

import time
from pathlib import Path

import cv2
import pytest

from raqib_edge.detectors import WEIGHTS_DIR, Detector, make_detector

FRAMES = sorted((Path(__file__).parent / "fixtures" / "frames").glob("*.jpg"))


@pytest.fixture(scope="module")
def frames():
    imgs = [cv2.imread(str(p)) for p in FRAMES]
    assert len(imgs) == 5 and all(im is not None for im in imgs)
    return imgs


@pytest.fixture(scope="module")
def yolo() -> Detector:
    return make_detector("yolo")


def test_yolo_detects_a_person_in_every_fixture(yolo, frames):
    for im in frames:
        h, w = im.shape[:2]
        dets = yolo.detect(im)
        persons = [d for d in dets if d.cls == "person"]
        assert persons, "expected at least one person"
        for d in persons:
            assert 0 < d.conf <= 1
            x1, y1, x2, y2 = d.xyxy
            assert 0 <= x1 < x2 <= w + 1 and 0 <= y1 < y2 <= h + 1


def test_yolo_only_returns_kept_classes(yolo, frames):
    for im in frames:
        assert {d.cls for d in yolo.detect(im)} <= {"person"}


def test_tracking_keeps_a_stable_id_across_consecutive_frames(yolo):
    cap = cv2.VideoCapture(str(WEIGHTS_DIR.parent / "video" / "checkout_39221979.mp4"))
    ids_per_frame = []
    for _ in range(10):
        ok, frame = cap.read()
        assert ok
        ids_per_frame.append({t.track_id for t in yolo.track(frame)})
    cap.release()
    later = [s for s in ids_per_frame[3:] if s]
    assert later, "no tracks at all"
    common = set.intersection(*later)
    assert common, f"no id survived frames 4-10: {ids_per_frame}"


def test_yolo_latency_is_realtime_on_this_machine(yolo, frames):
    yolo.detect(frames[0])  # warm-up
    t0 = time.perf_counter()
    for im in frames:
        yolo.detect(im)
    per_frame = (time.perf_counter() - t0) / len(frames)
    assert per_frame < 0.2, f"{per_frame*1000:.0f} ms/frame is slower than 5 fps"


@pytest.mark.skipif(not (WEIGHTS_DIR / "rtdetr-l.pt").exists(), reason="rtdetr-l.pt not downloaded")
def test_rtdetr_adapter_detects_persons(frames):
    det = make_detector("rtdetr")
    dets = det.detect(frames[1])
    assert any(d.cls == "person" for d in dets)


def test_rules_module_does_not_import_detectors():
    import importlib
    import sys

    for m in list(sys.modules):
        if m.startswith("raqib_edge.detectors"):
            del sys.modules[m]
    importlib.import_module("raqib_edge.rules")
    assert not any(m.startswith("raqib_edge.detectors") for m in sys.modules)
