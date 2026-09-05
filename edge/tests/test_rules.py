"""Rules are tested with synthetic tracks and an injected clock. No video, no model."""

from datetime import UTC, datetime, timedelta

import pytest

from raqib_edge.events import Track
from raqib_edge.rules import RuleState, evaluate
from raqib_edge.zones import CameraCfg, Site, Zone

T0 = datetime(2026, 9, 6, 9, 0, 0, tzinfo=UTC)
WH = (1000, 1000)


def person(tid: int, x: float, y: float, conf: float = 0.9, cls: str = "person") -> Track:
    """A 40x120 px box whose foot point is at (x, y) in a 1000x1000 frame."""
    return Track(track_id=tid, cls=cls, conf=conf, xyxy=(x - 20, y - 120, x + 20, y))


def helmet_for(p: Track) -> Track:
    x1, y1, x2, _ = p.xyxy
    return Track(track_id=1000 + p.track_id, cls="helmet", conf=0.8, xyxy=(x1, y1, x2, y1 + 25))


@pytest.fixture
def retail() -> Site:
    return Site(
        name="demo",
        profile="retail",
        cameras={"cam1": CameraCfg("cam1", "file", "x.mp4")},
        zones=[
            Zone("entrance", "entrance", "cam1", [(0, 0.8), (1, 0.8), (1, 1), (0, 1)]),
            Zone("queue1", "queue", "cam1", [(0, 0.3), (0.5, 0.3), (0.5, 0.7), (0, 0.7)], {"till": 1}),
            Zone("till1", "checkout", "cam1", [(0.5, 0.3), (1, 0.3), (1, 0.7), (0.5, 0.7)], {"till": 1}),
            Zone("shelfA", "shelf", "cam1", [(0, 0), (0.5, 0), (0.5, 0.2), (0, 0.2)], {"shelf_id": "A1"}),
        ],
        thresholds={"queue_n": 4, "queue_s": 60, "shelf_empty_ratio": 0.4, "shelf_s": 300,
                    "checkout_dwell_s": 20, "reemit_s": 300, "min_conf": 0.35},
        tills=1,
    )


@pytest.fixture
def factory() -> Site:
    return Site(
        name="plant",
        profile="factory",
        cameras={"cam1": CameraCfg("cam1", "file", "x.mp4")},
        zones=[
            Zone("work", "work_area", "cam1", [(0, 0.2), (1, 0.2), (1, 1), (0, 1)]),
            Zone("excl", "exclusion", "cam1", [(0.6, 0.3), (1, 0.3), (1, 0.7), (0.6, 0.7)], {"machine_id": 1}),
            Zone("press", "machine", "cam1", [(0.6, 0), (1, 0), (1, 0.2), (0.6, 0.2)], {"machine_id": 1}),
        ],
        thresholds={"helmet_s": 2, "machine_stop_s": 120, "reemit_s": 300, "min_conf": 0.35},
    )


# ---------------------------------------------------------------- R10 queue over


def test_queue_of_five_needs_sixty_seconds_then_fires_once(retail):
    st = RuleState()
    crowd = [person(i, 100 + 30 * i, 500) for i in range(5)]
    assert [e for e in evaluate(crowd, retail, "cam1", st, T0, WH) if e.kind == "queue_over"] == []
    at_59 = evaluate(crowd, retail, "cam1", st, T0 + timedelta(seconds=59), WH)
    assert not [e for e in at_59 if e.kind == "queue_over"]
    at_61 = [e for e in evaluate(crowd, retail, "cam1", st, T0 + timedelta(seconds=61), WH) if e.kind == "queue_over"]
    assert len(at_61) == 1
    e = at_61[0]
    assert e.severity == 2 and e.rule_id == "R10"
    assert e.payload["count"] == 5 and e.payload["till"] == 1
    # debounced: no second emission a few seconds later
    at_70 = evaluate(crowd, retail, "cam1", st, T0 + timedelta(seconds=70), WH)
    assert not [e for e in at_70 if e.kind == "queue_over"]


def test_queue_timer_resets_when_crowd_disperses(retail):
    st = RuleState()
    crowd = [person(i, 100 + 30 * i, 500) for i in range(4)]
    evaluate(crowd, retail, "cam1", st, T0, WH)
    evaluate(crowd[:2], retail, "cam1", st, T0 + timedelta(seconds=30), WH)  # drops below threshold
    out = evaluate(crowd, retail, "cam1", st, T0 + timedelta(seconds=70), WH)
    assert not [e for e in out if e.kind == "queue_over"]


def test_low_confidence_persons_are_ignored(retail):
    st = RuleState()
    crowd = [person(i, 100 + 30 * i, 500, conf=0.2) for i in range(6)]
    evaluate(crowd, retail, "cam1", st, T0, WH)
    out = evaluate(crowd, retail, "cam1", st, T0 + timedelta(seconds=90), WH)
    assert not [e for e in out if e.kind == "queue_over"]


# ---------------------------------------------------------------- R12 footfall


def test_footfall_tick_once_per_track(retail):
    st = RuleState()
    walker = person(42, 500, 950)
    first = [e for e in evaluate([walker], retail, "cam1", st, T0, WH) if e.kind == "footfall_tick"]
    assert len(first) == 1 and first[0].payload["track_id"] == 42 and first[0].rule_id == "R12"
    again = evaluate([walker], retail, "cam1", st, T0 + timedelta(seconds=1), WH)
    assert not [e for e in again if e.kind == "footfall_tick"]


# ---------------------------------------------------------------- R13 checkout served


def test_checkout_served_after_dwell_then_leave(retail):
    st = RuleState()
    shopper = person(7, 750, 500)
    evaluate([shopper], retail, "cam1", st, T0, WH)
    evaluate([shopper], retail, "cam1", st, T0 + timedelta(seconds=25), WH)
    gone = evaluate([], retail, "cam1", st, T0 + timedelta(seconds=26), WH)
    served = [e for e in gone if e.kind == "checkout_served"]
    assert len(served) == 1
    assert served[0].payload["dwell_s"] == 26.0
    assert served[0].payload["mu_source"] == "estimated_from_video"


def test_short_checkout_visit_is_not_a_service(retail):
    st = RuleState()
    shopper = person(7, 750, 500)
    evaluate([shopper], retail, "cam1", st, T0, WH)
    gone = evaluate([], retail, "cam1", st, T0 + timedelta(seconds=5), WH)
    assert not [e for e in gone if e.kind == "checkout_served"]


# ---------------------------------------------------------------- R11 shelf gap


def test_shelf_gap_after_five_minutes_once(retail):
    st = RuleState()
    ratios = {"shelfA": 0.5}
    assert not evaluate([], retail, "cam1", st, T0, WH, shelf_ratios=ratios)
    out = evaluate([], retail, "cam1", st, T0 + timedelta(seconds=300), WH, shelf_ratios=ratios)
    gaps = [e for e in out if e.kind == "shelf_gap"]
    assert len(gaps) == 1 and gaps[0].severity == 1 and gaps[0].payload["shelf_id"] == "A1"
    out2 = evaluate([], retail, "cam1", st, T0 + timedelta(seconds=310), WH, shelf_ratios=ratios)
    assert not [e for e in out2 if e.kind == "shelf_gap"]


def test_shelf_restocked_resets_timer(retail):
    st = RuleState()
    evaluate([], retail, "cam1", st, T0, WH, shelf_ratios={"shelfA": 0.6})
    evaluate([], retail, "cam1", st, T0 + timedelta(seconds=100), WH, shelf_ratios={"shelfA": 0.1})
    out = evaluate([], retail, "cam1", st, T0 + timedelta(seconds=400), WH, shelf_ratios={"shelfA": 0.6})
    assert not [e for e in out if e.kind == "shelf_gap"]


# ---------------------------------------------------------------- factory rules


def test_exclusion_breach_is_immediate_severity_three_per_person(factory):
    st = RuleState()
    intruders = [person(1, 800, 500), person(2, 900, 600)]
    out = [e for e in evaluate(intruders, factory, "cam1", st, T0, WH) if e.kind == "zone_breach"]
    assert len(out) == 2
    assert all(e.severity == 3 and e.rule_id == "R02" and e.payload["machine_id"] == 1 for e in out)
    # staying inside does not re-emit every frame
    again = evaluate(intruders, factory, "cam1", st, T0 + timedelta(seconds=1), WH)
    assert not [e for e in again if e.kind == "zone_breach"]


def test_no_helmet_after_two_seconds_but_helmet_suppresses(factory):
    st = RuleState()
    worker = person(5, 300, 600)
    evaluate([worker], factory, "cam1", st, T0, WH)
    out = [e for e in evaluate([worker], factory, "cam1", st, T0 + timedelta(seconds=2.5), WH) if e.kind == "ppe_violation"]
    assert len(out) == 1 and out[0].severity == 3 and out[0].payload["class"] == "no_helmet"

    st2 = RuleState()
    with_helmet = [worker, helmet_for(worker)]
    evaluate(with_helmet, factory, "cam1", st2, T0, WH)
    out2 = evaluate(with_helmet, factory, "cam1", st2, T0 + timedelta(seconds=5), WH)
    assert not [e for e in out2 if e.kind == "ppe_violation"]


def test_machine_stopped_after_120s(factory):
    st = RuleState()
    ms = {"press": "stopped"}
    assert not evaluate([], factory, "cam1", st, T0, WH, machine_states=ms)
    out = [e for e in evaluate([], factory, "cam1", st, T0 + timedelta(seconds=121), WH, machine_states=ms) if e.kind == "machine_stopped"]
    assert len(out) == 1 and out[0].severity == 2 and out[0].payload["machine_id"] == 1
    running = evaluate([], factory, "cam1", st, T0 + timedelta(seconds=130), WH, machine_states={"press": "running"})
    assert not running


def test_retail_profile_never_runs_factory_rules(retail):
    st = RuleState()
    intruder = person(1, 800, 500)  # would be a breach if an exclusion zone existed
    out = evaluate([intruder], retail, "cam1", st, T0 + timedelta(seconds=10), WH)
    assert {e.kind for e in out} <= {"footfall_tick", "queue_over", "checkout_served", "shelf_gap"}
