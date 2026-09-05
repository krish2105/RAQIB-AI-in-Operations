"""Polygon zones and site configuration.

Zones are drawn in normalised frame coordinates (0..1) so one YAML works at any
camera resolution. `Zone.contains` takes pixel coordinates plus the frame size,
or normalised coordinates directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from shapely.geometry import Point, Polygon

ZONE_KINDS: tuple[str, ...] = (
    "entrance",
    "queue",
    "shelf",
    "checkout",
    "work_area",
    "exclusion",
    "machine",
)

PROFILES: tuple[str, ...] = ("retail", "factory")

DEFAULT_THRESHOLDS: dict[str, float] = {
    "queue_n": 4,
    "queue_s": 60,
    "shelf_empty_ratio": 0.4,
    "shelf_s": 300,
    "helmet_s": 2,
    "machine_stop_s": 120,
    "checkout_dwell_s": 20,
    "reemit_s": 300,
    "min_conf": 0.35,
}


@dataclass
class Zone:
    name: str
    kind: str
    camera: str
    polygon: list[tuple[float, float]]
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in ZONE_KINDS:
            raise ValueError(f"zone {self.name!r}: kind {self.kind!r} not in {ZONE_KINDS}")
        if len(self.polygon) < 3:
            raise ValueError(f"zone {self.name!r}: polygon needs at least 3 points")
        for x, y in self.polygon:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(f"zone {self.name!r}: coordinates must be normalised 0..1")
        self._shape = Polygon(self.polygon)

    def contains(self, pt: tuple[float, float], frame_wh: tuple[int, int] | None = None) -> bool:
        x, y = pt
        if frame_wh is not None:
            w, h = frame_wh
            x, y = x / w, y / h
        return bool(self._shape.covers(Point(x, y)))

    def pixel_polygon(self, frame_wh: tuple[int, int]) -> list[tuple[int, int]]:
        w, h = frame_wh
        return [(int(round(x * w)), int(round(y * h))) for x, y in self.polygon]


@dataclass
class CameraCfg:
    name: str
    source: str  # file | webcam | rtsp
    uri: str | int
    fps: float = 25.0


@dataclass
class Site:
    name: str
    profile: str
    cameras: dict[str, CameraCfg]
    zones: list[Zone]
    thresholds: dict[str, float]
    tills: int = 1
    floor: dict[str, Any] = field(default_factory=dict)
    machines: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.profile not in PROFILES:
            raise ValueError(f"site {self.name!r}: profile {self.profile!r} not in {PROFILES}")

    def zones_for(self, camera: str, kind: str | None = None) -> list[Zone]:
        return [z for z in self.zones if z.camera == camera and (kind is None or z.kind == kind)]

    def threshold(self, key: str) -> float:
        return float(self.thresholds.get(key, DEFAULT_THRESHOLDS[key]))


def load_site(path: str | Path) -> Site:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    cameras = {
        name: CameraCfg(name=name, source=c["source"], uri=c.get("uri", 0), fps=float(c.get("fps", 25)))
        for name, c in raw.get("cameras", {}).items()
    }
    zones = [
        Zone(
            name=z["name"],
            kind=z["kind"],
            camera=z["camera"],
            polygon=[(float(x), float(y)) for x, y in z["polygon"]],
            meta=dict(z.get("meta", {})),
        )
        for z in raw.get("zones", [])
    ]
    for z in zones:
        if z.camera not in cameras:
            raise ValueError(f"zone {z.name!r} references unknown camera {z.camera!r}")
    thresholds = {**DEFAULT_THRESHOLDS, **{k: float(v) for k, v in raw.get("thresholds", {}).items()}}
    return Site(
        name=raw["name"],
        profile=raw["profile"],
        cameras=cameras,
        zones=zones,
        thresholds=thresholds,
        tills=int(raw.get("tills", 1)),
        floor=dict(raw.get("floor", {})),
        machines=list(raw.get("machines", [])),
    )
