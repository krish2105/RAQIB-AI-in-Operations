from datetime import UTC, datetime, timedelta

import pytest

from raqib_edge.events import Event, Track, box_iou, new_event


def test_event_roundtrip_preserves_utc_timestamp():
    ts = datetime(2026, 9, 6, 10, 15, 30, tzinfo=UTC)
    e = new_event("s", "cam1", ts, "queue_over", 2, {"count": 5}, "R10")
    d = e.to_dict()
    assert d["ts"].endswith("+00:00")
    back = Event.from_dict(d)
    assert back == e


def test_naive_timestamp_is_treated_as_utc():
    e = new_event("s", "cam1", datetime(2026, 1, 1, 0, 0, 0), "footfall_tick", 1, {}, "R12")
    assert e.ts.tzinfo is UTC


def test_ids_are_ulids_and_time_ordered():
    t0 = datetime(2026, 9, 6, tzinfo=UTC)
    a = new_event("s", "c", t0, "footfall_tick", 1, {}, "R12")
    b = new_event("s", "c", t0 + timedelta(seconds=1), "footfall_tick", 1, {}, "R12")
    assert len(a.id) == 26 and len(b.id) == 26
    assert a.id < b.id


def test_unknown_kind_and_bad_severity_rejected():
    ts = datetime.now(UTC)
    with pytest.raises(ValueError):
        new_event("s", "c", ts, "not_a_kind", 1, {}, "R00")
    with pytest.raises(ValueError):
        new_event("s", "c", ts, "queue_over", 4, {}, "R10")


def test_track_geometry_helpers():
    t = Track(track_id=7, cls="person", conf=0.9, xyxy=(10, 20, 30, 100))
    assert t.centroid == (20, 60)
    assert t.foot == (20, 100)
    assert t.head_region == (10, 20, 30, 40)


def test_box_iou():
    assert box_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert box_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert abs(box_iou((0, 0, 10, 10), (5, 0, 15, 10)) - 1 / 3) < 1e-9
