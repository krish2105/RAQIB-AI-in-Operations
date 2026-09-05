from pathlib import Path

import cv2
import numpy as np

from raqib_edge.machine_state import MachineStateTracker, classify_machine_state
from raqib_edge.shelf import shelf_empty_ratio

FRAME = Path(__file__).parent / "fixtures" / "frames" / "checkout_t16.jpg"
FULL = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def test_flat_grey_shelf_reads_empty():
    flat = np.full((240, 480, 3), 120, dtype=np.uint8)
    assert shelf_empty_ratio(flat, FULL) > 0.8


def test_busy_display_reads_stocked():
    img = cv2.imread(str(FRAME))
    # confectionery display, bottom-left of the fixture frame
    poly = [(0.0, 0.66), (0.2, 0.66), (0.2, 1.0), (0.0, 1.0)]
    assert shelf_empty_ratio(img, poly) < 0.4


def test_tiny_polygon_is_zero_not_crash():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    assert shelf_empty_ratio(img, [(0.5, 0.5), (0.51, 0.5), (0.51, 0.51)]) == 0.0


def test_machine_state_identical_rois_are_stopped_and_noisy_are_running():
    rng = np.random.default_rng(1)
    a = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    assert classify_machine_state(a, a.copy()) == "stopped"
    b = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    assert classify_machine_state(a, b) == "running"


def test_machine_state_tracker_smooths_and_settles():
    rng = np.random.default_rng(2)
    trk = MachineStateTracker(alpha=0.5)
    base = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    assert trk.update("press", base) == "idle"  # first frame, no history
    for _ in range(6):
        state = trk.update("press", base.copy())
    assert state == "stopped"
    for _ in range(6):
        state = trk.update("press", rng.integers(0, 255, (64, 64, 3), dtype=np.uint8))
    assert state == "running"
