"""Model drift per camera: Population Stability Index of detection count and mean confidence vs the previous
7 days. The edge posts one sample per camera every two minutes; each hour is judged on the trailing two-hour
window (about 60 samples, five quantile bins, so a healthy camera sits near 0.07). PSI > 0.2 for 3 consecutive
hours raises one `model_drift` event (severity 2) with a suggested action derived from which signal moved:
confidence down with brightness/blur steady -> relabel; blur up -> clean lens; detections down with steady
light -> re-aim."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, select
from ulid import ULID

from ..config import settings
from ..models import DriftSample, Event

BINS = 5
WINDOW_H = 2
MIN_CURRENT = 30
MIN_BASELINE = 100


def psi(baseline: list[float], current: list[float], bins: int = BINS, floor: float = 0.01) -> float:
    """Population Stability Index with quantile bins from the baseline; 0 = identical, > 0.2 = shifted.
    Needs enough samples on both sides: histogram PSI on a handful of values is noise, so it returns 0."""
    if len(baseline) < MIN_BASELINE or len(current) < MIN_CURRENT:
        return 0.0
    b = sorted(baseline)
    edges = [b[int(i * (len(b) - 1) / bins)] for i in range(1, bins)]

    def hist(vals: list[float]) -> list[float]:
        counts = [0] * bins
        for v in vals:
            k = 0
            while k < len(edges) and v > edges[k]:
                k += 1
            counts[k] += 1
        n = len(vals)
        return [max(c / n, floor) for c in counts]

    hb, hc = hist(baseline), hist(current)
    return float(sum((c - b_) * math.log(c / b_) for b_, c in zip(hb, hc, strict=True)))


@dataclass
class CameraDrift:
    site: str
    camera: str
    psi_det: float
    psi_conf: float
    hours_over: int
    baseline_n: int
    current_n: int
    suggestion: str | None = None
    hourly: list[dict[str, Any]] = field(default_factory=list)

    @property
    def psi(self) -> float:
        return max(self.psi_det, self.psi_conf)

    def as_dict(self) -> dict[str, Any]:
        return {"site": self.site, "camera": self.camera, "psi": round(self.psi, 3), "psi_det": round(self.psi_det, 3), "psi_conf": round(self.psi_conf, 3),
                "hours_over": self.hours_over, "baseline_n": self.baseline_n, "current_n": self.current_n, "suggestion": self.suggestion,
                "threshold": settings.drift_psi_threshold, "hourly": self.hourly}


def suggest(baseline: list[DriftSample], current: list[DriftSample], psi_det: float, psi_conf: float) -> str | None:
    if max(psi_det, psi_conf) <= settings.drift_psi_threshold or not baseline or not current:
        return None
    mean = lambda xs: sum(xs) / len(xs)  # noqa: E731
    b_blur, c_blur = mean([s.blur for s in baseline]), mean([s.blur for s in current])
    b_bri, c_bri = mean([s.brightness for s in baseline]), mean([s.brightness for s in current])
    b_det, c_det = mean([s.det_count for s in baseline]), mean([s.det_count for s in current])
    if c_blur > b_blur * 1.5:
        return "clean_lens"
    if abs(c_bri - b_bri) > 0.25 * max(b_bri, 1e-6):
        return "check_lighting"
    if c_det < b_det * 0.6 and psi_det > psi_conf:
        return "re_aim"
    return "relabel"


def analyse(site: str, camera: str, session: Session, now: datetime | None = None) -> CameraDrift:
    now = now or datetime.now(UTC)
    base_start = now - timedelta(days=settings.drift_baseline_days)
    cur_start = now - timedelta(hours=WINDOW_H)
    rows = session.exec(select(DriftSample).where(DriftSample.site == site, DriftSample.camera == camera, DriftSample.ts >= base_start.replace(tzinfo=None)).order_by(DriftSample.ts)).all()
    baseline = [r for r in rows if r.ts < cur_start.replace(tzinfo=None)]
    current = [r for r in rows if r.ts >= cur_start.replace(tzinfo=None)]
    psi_det = psi([r.det_count for r in baseline], [r.det_count for r in current])
    psi_conf = psi([r.mean_conf for r in baseline], [r.mean_conf for r in current])
    # hours over: walk back hour by hour over the last 24 h and count the run of hours whose own sample set breaches
    hourly = []
    run = 0
    counting = True
    for h in range(24):
        t1 = now - timedelta(hours=h)
        t0 = t1 - timedelta(hours=WINDOW_H)
        cur = [r for r in rows if t0.replace(tzinfo=None) <= r.ts < t1.replace(tzinfo=None)]
        base_h = [r for r in rows if r.ts < t0.replace(tzinfo=None)]
        p = max(psi([r.det_count for r in base_h], [r.det_count for r in cur]), psi([r.mean_conf for r in base_h], [r.mean_conf for r in cur])) if cur else 0.0
        hourly.append({"hour": t0.isoformat(), "psi": round(p, 3), "samples": len(cur)})
        if counting:
            if cur and p > settings.drift_psi_threshold:
                run += 1
            else:
                counting = False
    hourly.reverse()
    return CameraDrift(site, camera, psi_det, psi_conf, run, len(baseline), len(current), suggest(baseline, current, psi_det, psi_conf), hourly)


def check_and_emit(site: str, session: Session, now: datetime | None = None, cooldown_h: float = 6.0) -> list[Event]:
    """One model_drift event per camera when PSI stayed over the threshold for `drift_hours`; not repeated within the cooldown."""
    now = now or datetime.now(UTC)
    cams = {str(r[0] if isinstance(r, tuple) else r) for r in session.exec(select(DriftSample.camera).where(DriftSample.site == site).distinct()).all()}
    out: list[Event] = []
    for cam in sorted(cams):
        d = analyse(site, cam, session, now)
        if d.hours_over < settings.drift_hours:
            continue
        recent = session.exec(select(Event).where(Event.site == site, Event.kind == "model_drift", Event.ts >= (now - timedelta(hours=cooldown_h)).replace(tzinfo=None))).all()
        if any(e.camera == cam for e in recent):
            continue
        e = Event(id=str(ULID()), site=site, camera=cam, ts=now, kind="model_drift", severity=2, rule_id="D01",
                  payload={"psi": round(d.psi, 3), "psi_det": round(d.psi_det, 3), "psi_conf": round(d.psi_conf, 3), "hours_over": d.hours_over,
                           "suggestion": d.suggestion, "baseline_n": d.baseline_n, "current_n": d.current_n, "confidence": 0.8}, handled=True)
        session.add(e)
        out.append(e)
    session.commit()
    return out
