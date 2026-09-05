from datetime import UTC, datetime, timedelta

import cv2
import numpy as np

from raqib_edge.events import new_event
from raqib_edge.store import ClipWriter, EventStore

T0 = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def ev(i: int):
    return new_event("s", "cam1", T0 + timedelta(seconds=i), "footfall_tick", 1, {"i": i}, "R12")


def test_append_unsynced_mark_synced_roundtrip(tmp_path):
    st = EventStore(tmp_path / "e.db")
    events = [ev(i) for i in range(3)]
    for e in events:
        st.append(e)
    st.append(events[0])  # duplicate id is ignored
    assert st.count() == 3
    pending = st.unsynced()
    assert [e.id for e in pending] == [e.id for e in events]
    assert pending[0] == events[0]
    st.mark_synced([events[0].id, events[1].id])
    assert [e.id for e in st.unsynced()] == [events[2].id]
    assert st.recent(2)[0].id == events[2].id


def test_set_clip_path(tmp_path):
    st = EventStore(tmp_path / "e.db")
    e = ev(0)
    st.append(e)
    st.set_clip(e.id, "/clips/x.mp4")
    assert st.recent(1)[0].clip_path == "/clips/x.mp4"


def test_clip_writer_produces_ten_second_clip(tmp_path):
    fps = 10
    cw = ClipWriter(tmp_path, fps=fps, pre_s=5, post_s=5)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    for _ in range(80):  # 8 s of history, buffer keeps last 5 s
        assert cw.push(frame) == []
    cw.trigger("EV1")
    done = []
    for _ in range(fps * 5):
        done += cw.push(frame)
    assert len(done) == 1 and done[0][0] == "EV1"
    cap = cv2.VideoCapture(done[0][1])
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    assert 8 * fps <= n <= 12 * fps
