"""Event model: the single source of truth shared by edge and cloud.

An Event is what leaves the edge box. It carries counts, classes, positions,
confidences and the rule that fired. It never carries identity. `track_id` in
the payload is a per-session integer and is meaningless outside the run that
produced it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from ulid import ULID

EventKind = Literal[
    "ppe_violation",
    "zone_breach",
    "machine_stopped",
    "queue_over",
    "shelf_gap",
    "footfall_tick",
    "checkout_served",
]

EVENT_KINDS: tuple[str, ...] = (
    "ppe_violation",
    "zone_breach",
    "machine_stopped",
    "queue_over",
    "shelf_gap",
    "footfall_tick",
    "checkout_served",
    "price_mismatch",
    "planogram_drift",
)

SEVERITY_INFO = 1
SEVERITY_WARN = 2
SEVERITY_CRITICAL = 3

XYXY = tuple[float, float, float, float]


@dataclass(frozen=True)
class Det:
    """One detection in pixel coordinates."""

    cls: str
    conf: float
    xyxy: XYXY


@dataclass
class Track:
    """A tracked object for the current frame. `track_id` is session-scoped."""

    track_id: int
    cls: str
    conf: float
    xyxy: XYXY

    @property
    def centroid(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.xyxy
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def foot(self) -> tuple[float, float]:
        """Bottom-centre of the box: where the person stands on the floor."""
        x1, _, x2, y2 = self.xyxy
        return ((x1 + x2) / 2.0, y2)

    @property
    def head_region(self) -> XYXY:
        """Top quarter of the box, used for helmet overlap checks."""
        x1, y1, x2, y2 = self.xyxy
        return (x1, y1, x2, y1 + (y2 - y1) * 0.25)


@dataclass
class Event:
    id: str
    site: str
    camera: str
    ts: datetime
    kind: str
    severity: int
    payload: dict[str, Any] = field(default_factory=dict)
    clip_path: str | None = None
    rule_id: str = ""

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind {self.kind!r}")
        if self.severity not in (1, 2, 3):
            raise ValueError(f"severity must be 1, 2 or 3, got {self.severity!r}")
        if self.ts.tzinfo is None:
            self.ts = self.ts.replace(tzinfo=UTC)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts.astimezone(UTC).isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        d = dict(d)
        ts = d["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        d["ts"] = ts
        return cls(**d)


def new_event(
    site: str,
    camera: str,
    ts: datetime,
    kind: str,
    severity: int,
    payload: dict[str, Any],
    rule_id: str,
    clip_path: str | None = None,
) -> Event:
    """Build an Event with a fresh ULID. ULIDs sort by time, which the store relies on."""
    return Event(
        id=str(ULID.from_timestamp(ts.timestamp())),
        site=site,
        camera=camera,
        ts=ts,
        kind=kind,
        severity=severity,
        payload=payload,
        clip_path=clip_path,
        rule_id=rule_id,
    )


def box_iou(a: XYXY, b: XYXY) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)
