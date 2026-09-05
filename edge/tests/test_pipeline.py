"""End-to-end edge test on the real demo clip: ~60 frames through detector, blur, rules, store."""

from pathlib import Path

from raqib_edge.pipeline import run_pipeline
from raqib_edge.store import EventStore

SITE = Path(__file__).resolve().parents[1] / "sites" / "retail_demo.yaml"


def test_pipeline_produces_events_and_stats(tmp_path):
    db = tmp_path / "events.db"
    stats = run_pipeline(SITE, max_frames=60, detector="yolo", api=None, db_path=db,
                         clips_dir=tmp_path / "clips", cameras=["cam1"])
    assert stats.frames == 60
    assert stats.fps > 3
    assert stats.detector == "yolo"
    assert stats.latency_ms_p95 > 0
    store = EventStore(db)
    events = store.recent(100)
    assert events, "expected footfall ticks from the checkout clip"
    kinds = {e.kind for e in events}
    assert kinds & {"footfall_tick", "checkout_served", "queue_over"}
    for e in events:
        assert e.site == "raqib_demo_store" and e.camera == "cam1"
        assert "track_id" not in e.payload or isinstance(e.payload["track_id"], int)
