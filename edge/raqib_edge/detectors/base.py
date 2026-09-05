"""Detector adapter.

Two methods matter: `detect(frame)` and `track(frame)`. Everything outside this
package talks to the Protocol only, so swapping YOLO (AGPL-3.0) for RT-DETR
(Apache-2.0 architecture) is a one-line change in the CLI and touches nothing
else. That is the whole point of the adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import numpy as np

from ..events import Det, Track

DetectorName = Literal["yolo", "rtdetr"]

# Repo-relative default weights. Overridable with RAQIB_WEIGHTS_DIR.
WEIGHTS_DIR = Path(__file__).resolve().parents[2] / "data" / "weights"

DEFAULT_WEIGHTS: dict[str, str] = {
    "yolo": "yolo26n.pt",
    "rtdetr": "rtdetr-l.pt",
}

# Classes the rules care about. COCO gives us `person`; PPE classes only exist
# in fine-tuned weights and are passed through when present.
KEEP_CLASSES = {"person", "helmet", "hardhat", "hard_hat", "safety_helmet", "vest", "safety_vest"}


@runtime_checkable
class Detector(Protocol):
    name: str

    def load(self, weights: str, device: str) -> None: ...

    def detect(self, frame: np.ndarray) -> list[Det]: ...

    def track(self, frame: np.ndarray) -> list[Track]: ...


def pick_device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def make_detector(
    name: DetectorName = "yolo",
    weights: str | Path | None = None,
    device: str | None = None,
    conf: float = 0.25,
) -> Detector:
    """Instantiate and load a detector by name. Lazy imports keep startup fast."""
    weights_path = Path(weights) if weights else WEIGHTS_DIR / DEFAULT_WEIGHTS[name]
    if not weights_path.exists():
        raise FileNotFoundError(
            f"weights not found at {weights_path}. Download from "
            "https://github.com/ultralytics/assets/releases (AGPL-3.0) — see docs/datasets.md"
        )
    dev = device or pick_device()
    if name == "yolo":
        from .yolo import YoloDetector

        det: Detector = YoloDetector(conf=conf)
    elif name == "rtdetr":
        from .rtdetr import RtDetrDetector

        det = RtDetrDetector(conf=conf)
    else:
        raise ValueError(f"unknown detector {name!r}")
    det.load(str(weights_path), dev)
    return det
