"""Machine ROI state: running / idle / stopped.

Dev implementation is motion energy on the machine's region of interest: a
running press or conveyor changes between frames; a stopped one does not. Two
thresholds separate the three states. The pilot swaps in a small classifier
trained on plant crops (edge/training/train_machine_state.py) behind the same
`classify_machine_state` signature; MVTec-AD is only a unit-test proxy.
"""

from __future__ import annotations

from typing import Literal

import cv2
import numpy as np

MachineState = Literal["running", "idle", "stopped"]


def motion_energy(roi_prev: np.ndarray, roi_now: np.ndarray) -> float:
    """Mean absolute grey-level difference, 0..255, after light blur to kill sensor noise."""
    if roi_prev.shape != roi_now.shape or roi_now.size == 0:
        return 0.0
    a = cv2.GaussianBlur(cv2.cvtColor(roi_prev, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    b = cv2.GaussianBlur(cv2.cvtColor(roi_now, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def classify_machine_state(
    roi_prev: np.ndarray,
    roi_now: np.ndarray,
    running_thr: float = 6.0,
    idle_thr: float = 1.5,
) -> MachineState:
    e = motion_energy(roi_prev, roi_now)
    if e >= running_thr:
        return "running"
    if e >= idle_thr:
        return "idle"
    return "stopped"


class MachineStateTracker:
    """Smooths per-frame states with an exponential moving average of motion energy."""

    def __init__(self, alpha: float = 0.2, running_thr: float = 6.0, idle_thr: float = 1.5) -> None:
        self.alpha = alpha
        self.running_thr = running_thr
        self.idle_thr = idle_thr
        self._prev: dict[str, np.ndarray] = {}
        self._ema: dict[str, float] = {}

    def update(self, name: str, roi: np.ndarray) -> MachineState:
        prev = self._prev.get(name)
        self._prev[name] = roi
        if prev is None:
            return "idle"
        e = motion_energy(prev, roi)
        ema = self._ema.get(name, e)
        ema = self.alpha * e + (1 - self.alpha) * ema
        self._ema[name] = ema
        if ema >= self.running_thr:
            return "running"
        if ema >= self.idle_thr:
            return "idle"
        return "stopped"
