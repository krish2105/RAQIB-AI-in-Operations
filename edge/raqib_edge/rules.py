"""Deterministic rule engine: tracks + zones + state -> Events.

Every rule is a pure function of its inputs and the injected `now`. There is no
wall-clock, no model, no LLM here. `RuleState` carries the small amount of
memory a rule needs across frames (dwell timers, debounce timestamps). It is
per camera and lives for the session only.

Rule ids match the spec table:
  R01 no helmet (factory, sev 3)     R10 queue over (retail, sev 2)
  R02 exclusion breach (factory, 3)  R11 shelf gap (retail, sev 1)
  R03 machine stopped (factory, 2)   R12 footfall tick (both, sev 1)
                                     R13 checkout served (retail, sev 1)
"""

from __future__ import annotations

from typing import Any

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from .events import Event, Track, box_iou, new_event
from .zones import Site, Zone

HELMET_CLASSES = {"helmet", "hardhat", "hard_hat", "safety_helmet"}
PERSON_CLASSES = {"person"}


@dataclass
class RuleState:
    """Mutable per-camera memory. Track ids inside are session-scoped."""

    dwell: dict[tuple[str, int], datetime] = field(default_factory=dict)
    queue_over_since: dict[str, datetime | None] = field(default_factory=dict)
    shelf_gap_since: dict[str, datetime | None] = field(default_factory=dict)
    machine_stopped_since: dict[str, datetime | None] = field(default_factory=dict)
    no_helmet_since: dict[int, datetime] = field(default_factory=dict)
    last_emit: dict[str, datetime] = field(default_factory=dict)
    crossed: set[tuple[str, int]] = field(default_factory=set)
    in_zone_prev: dict[tuple[str, int], bool] = field(default_factory=dict)

    def debounced(self, key: str, now: datetime, reemit_s: float) -> bool:
        """True if `key` fired within the last `reemit_s` seconds."""
        last = self.last_emit.get(key)
        return last is not None and (now - last).total_seconds() < reemit_s

    def mark(self, key: str, now: datetime) -> None:
        self.last_emit[key] = now


RuleFn = Callable[..., list[Event]]


def _persons(tracks: list[Track], min_conf: float) -> list[Track]:
    return [t for t in tracks if t.cls in PERSON_CLASSES and t.conf >= min_conf]


def _in(zone: Zone, t: Track, frame_wh: tuple[int, int]) -> bool:
    return zone.contains(t.foot, frame_wh)


# --------------------------------------------------------------------------- retail


def r10_queue_over(
    tracks: list[Track], site: Site, camera: str, state: RuleState, now: datetime, frame_wh
) -> list[Event]:
    out: list[Event] = []
    n_thr = int(site.threshold("queue_n"))
    s_thr = site.threshold("queue_s")
    persons = _persons(tracks, site.threshold("min_conf"))
    for zone in site.zones_for(camera, "queue"):
        count = sum(1 for t in persons if _in(zone, t, frame_wh))
        since = state.queue_over_since.get(zone.name)
        if count >= n_thr:
            if since is None:
                state.queue_over_since[zone.name] = now
            elif (now - since).total_seconds() >= s_thr:
                key = f"R10:{zone.name}"
                if not state.debounced(key, now, site.threshold("reemit_s")):
                    state.mark(key, now)
                    out.append(
                        new_event(
                            site.name,
                            camera,
                            now,
                            "queue_over",
                            2,
                            {
                                "zone": zone.name,
                                "till": zone.meta.get("till"),
                                "count": count,
                                "sustained_s": round((now - since).total_seconds(), 1),
                                "confidence": round(
                                    min((t.conf for t in persons if _in(zone, t, frame_wh)), default=0.0), 3
                                ),
                            },
                            "R10",
                        )
                    )
        else:
            state.queue_over_since[zone.name] = None
    return out


def r11_shelf_gap(
    site: Site, camera: str, state: RuleState, now: datetime, shelf_ratios: dict[str, float]
) -> list[Event]:
    out: list[Event] = []
    ratio_thr = site.threshold("shelf_empty_ratio")
    s_thr = site.threshold("shelf_s")
    for zone in site.zones_for(camera, "shelf"):
        ratio = shelf_ratios.get(zone.name)
        if ratio is None:
            continue
        since = state.shelf_gap_since.get(zone.name)
        if ratio > ratio_thr:
            if since is None:
                state.shelf_gap_since[zone.name] = now
            elif (now - since).total_seconds() >= s_thr:
                key = f"R11:{zone.name}"
                if not state.debounced(key, now, site.threshold("reemit_s")):
                    state.mark(key, now)
                    out.append(
                        new_event(
                            site.name,
                            camera,
                            now,
                            "shelf_gap",
                            1,
                            {
                                "zone": zone.name,
                                "shelf_id": zone.meta.get("shelf_id", zone.name),
                                "product": zone.meta.get("product"),
                                "empty_ratio": round(ratio, 3),
                                "sustained_s": round((now - since).total_seconds(), 1),
                                "confidence": round(min(1.0, (ratio - ratio_thr) / (1 - ratio_thr) + 0.5), 3),
                            },
                            "R11",
                        )
                    )
        else:
            state.shelf_gap_since[zone.name] = None
    return out


def r12_footfall_tick(
    tracks: list[Track], site: Site, camera: str, state: RuleState, now: datetime, frame_wh
) -> list[Event]:
    """One tick per track the first time its foot point enters an entrance zone."""
    out: list[Event] = []
    persons = _persons(tracks, site.threshold("min_conf"))
    for zone in site.zones_for(camera, "entrance"):
        for t in persons:
            key = (zone.name, t.track_id)
            if key in state.crossed:
                continue
            if _in(zone, t, frame_wh):
                state.crossed.add(key)
                out.append(
                    new_event(
                        site.name,
                        camera,
                        now,
                        "footfall_tick",
                        1,
                        {"zone": zone.name, "track_id": t.track_id, "confidence": round(t.conf, 3)},
                        "R12",
                    )
                )
    return out


def r13_checkout_served(
    tracks: list[Track], site: Site, camera: str, state: RuleState, now: datetime, frame_wh
) -> list[Event]:
    """A track that leaves a checkout zone after dwelling >= checkout_dwell_s = one service."""
    out: list[Event] = []
    dwell_thr = site.threshold("checkout_dwell_s")
    persons = {t.track_id: t for t in _persons(tracks, site.threshold("min_conf"))}
    for zone in site.zones_for(camera, "checkout"):
        present = {tid for tid, t in persons.items() if _in(zone, t, frame_wh)}
        for tid in present:
            state.dwell.setdefault((zone.name, tid), now)
        # tracks that were dwelling here but are no longer in the zone (moved or lost)
        for (zname, tid), entered in list(state.dwell.items()):
            if zname != zone.name or tid in present:
                continue
            dwell_s = (now - entered).total_seconds()
            del state.dwell[(zname, tid)]
            if dwell_s >= dwell_thr:
                out.append(
                    new_event(
                        site.name,
                        camera,
                        now,
                        "checkout_served",
                        1,
                        {
                            "zone": zone.name,
                            "till": zone.meta.get("till"),
                            "track_id": tid,
                            "dwell_s": round(dwell_s, 1),
                            "confidence": 0.7,
                            "mu_source": "estimated_from_video",
                        },
                        "R13",
                    )
                )
    return out


# --------------------------------------------------------------------------- factory


def r01_no_helmet(
    tracks: list[Track], site: Site, camera: str, state: RuleState, now: datetime, frame_wh
) -> list[Event]:
    out: list[Event] = []
    s_thr = site.threshold("helmet_s")
    persons = _persons(tracks, site.threshold("min_conf"))
    helmets = [t for t in tracks if t.cls in HELMET_CLASSES]
    work_zones = site.zones_for(camera, "work_area")
    for t in persons:
        if not any(_in(z, t, frame_wh) for z in work_zones):
            state.no_helmet_since.pop(t.track_id, None)
            continue
        has_helmet = any(box_iou(t.head_region, h.xyxy) > 0.05 for h in helmets)
        if has_helmet:
            state.no_helmet_since.pop(t.track_id, None)
            continue
        since = state.no_helmet_since.setdefault(t.track_id, now)
        if (now - since).total_seconds() >= s_thr:
            key = f"R01:{t.track_id}"
            if not state.debounced(key, now, site.threshold("reemit_s")):
                state.mark(key, now)
                out.append(
                    new_event(
                        site.name,
                        camera,
                        now,
                        "ppe_violation",
                        3,
                        {
                            "class": "no_helmet",
                            "track_id": t.track_id,
                            "zone": next(z.name for z in work_zones if _in(z, t, frame_wh)),
                            "sustained_s": round((now - since).total_seconds(), 1),
                            "confidence": round(t.conf, 3),
                        },
                        "R01",
                    )
                )
    return out


def r02_zone_breach(
    tracks: list[Track], site: Site, camera: str, state: RuleState, now: datetime, frame_wh
) -> list[Event]:
    out: list[Event] = []
    persons = _persons(tracks, site.threshold("min_conf"))
    for zone in site.zones_for(camera, "exclusion"):
        for t in persons:
            key = (zone.name, t.track_id)
            inside = _in(zone, t, frame_wh)
            was_inside = state.in_zone_prev.get(key, False)
            state.in_zone_prev[key] = inside
            if inside and not was_inside:
                out.append(
                    new_event(
                        site.name,
                        camera,
                        now,
                        "zone_breach",
                        3,
                        {
                            "zone": zone.name,
                            "machine_id": zone.meta.get("machine_id"),
                            "track_id": t.track_id,
                            "confidence": round(t.conf, 3),
                        },
                        "R02",
                    )
                )
    return out


def r03_machine_stopped(
    site: Site, camera: str, state: RuleState, now: datetime, machine_states: dict[str, str]
) -> list[Event]:
    out: list[Event] = []
    s_thr = site.threshold("machine_stop_s")
    for zone in site.zones_for(camera, "machine"):
        st = machine_states.get(zone.name)
        if st is None:
            continue
        since = state.machine_stopped_since.get(zone.name)
        if st == "stopped":
            if since is None:
                state.machine_stopped_since[zone.name] = now
            elif (now - since).total_seconds() >= s_thr:
                key = f"R03:{zone.name}"
                if not state.debounced(key, now, site.threshold("reemit_s")):
                    state.mark(key, now)
                    out.append(
                        new_event(
                            site.name,
                            camera,
                            now,
                            "machine_stopped",
                            2,
                            {
                                "zone": zone.name,
                                "machine_id": zone.meta.get("machine_id"),
                                "stopped_s": round((now - since).total_seconds(), 1),
                                "confidence": 0.8,
                            },
                            "R03",
                        )
                    )
        else:
            state.machine_stopped_since[zone.name] = None
    return out


# --------------------------------------------------------------------------- dispatcher


def r14_price_mismatch(
    site: Site, camera: str, state: RuleState, now: datetime, price_reads: dict[str, tuple[float | None, float | None]]
) -> list[Event]:
    """v2. price_reads: tag -> (read_price, expected_price). Severity 1 when they differ beyond the tolerance."""
    out: list[Event] = []
    tol = site.threshold("price_tolerance") if "price_tolerance" in site.thresholds else 0.05
    for tag, (read, expected) in sorted(price_reads.items()):
        if read is None or expected is None:
            continue
        if abs(read - expected) <= tol:
            state.last_emit.pop(f"R14:{tag}", None)
            continue
        key = f"R14:{tag}"
        if state.debounced(key, now, site.threshold("reemit_s")):
            continue
        state.mark(key, now)
        out.append(new_event(site.name, camera, now, "price_mismatch", 1,
                             {"tag": tag, "shelf_id": tag.split("-")[0], "read_price": read, "expected_price": expected,
                              "delta": round(read - expected, 2), "confidence": 0.7}, "R14"))
    return out


def r15_planogram_drift(
    site: Site, camera: str, state: RuleState, now: datetime, diffs: dict[str, Any]
) -> list[Event]:
    """v2. diffs: shelf zone name -> PlanogramDiff. Severity 1 when missing + misplaced reaches the threshold."""
    out: list[Event] = []
    min_drift = int(site.threshold("planogram_drift_min")) if "planogram_drift_min" in site.thresholds else 1
    for zone_name, d in sorted(diffs.items()):
        key = f"R15:{zone_name}"
        if d.drift < min_drift:
            state.last_emit.pop(key, None)
            continue
        if state.debounced(key, now, site.threshold("reemit_s")):
            continue
        state.mark(key, now)
        out.append(new_event(site.name, camera, now, "planogram_drift", 1,
                             {"zone": zone_name, "shelf_id": d.shelf_id, "expected": d.expected, "present": d.present,
                              "missing": [m["sku"] for m in d.missing], "misplaced": [m["sku"] for m in d.misplaced],
                              "compliance": round(d.compliance, 3), "confidence": 0.7}, "R15"))
    return out


def evaluate(
    tracks: list[Track],
    site: Site,
    camera: str,
    state: RuleState,
    now: datetime,
    frame_wh: tuple[int, int] = (1, 1),
    shelf_ratios: dict[str, float] | None = None,
    machine_states: dict[str, str] | None = None,
    price_reads: dict[str, tuple[float | None, float | None]] | None = None,
    planogram_diffs: dict[str, Any] | None = None,
) -> list[Event]:
    """Run the rules for the site's profile. Order is stable so output is reproducible."""
    events: list[Event] = []
    events += r12_footfall_tick(tracks, site, camera, state, now, frame_wh)
    if site.profile == "retail":
        events += r10_queue_over(tracks, site, camera, state, now, frame_wh)
        events += r13_checkout_served(tracks, site, camera, state, now, frame_wh)
        if shelf_ratios:
            events += r11_shelf_gap(site, camera, state, now, shelf_ratios)
        if price_reads:
            events += r14_price_mismatch(site, camera, state, now, price_reads)
        if planogram_diffs:
            events += r15_planogram_drift(site, camera, state, now, planogram_diffs)
    elif site.profile == "factory":
        events += r02_zone_breach(tracks, site, camera, state, now, frame_wh)
        events += r01_no_helmet(tracks, site, camera, state, now, frame_wh)
        if machine_states:
            events += r03_machine_stopped(site, camera, state, now, machine_states)
    return events
