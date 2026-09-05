"""Regression test: reading events must never mark them dirty.

The bug: `event.ts = event.ts.replace(tzinfo=UTC)` on a row fetched from the
session mutates a tracked ORM object, so the next autoflush issues an UPDATE
for every row a read endpoint touched. On SQLite with a large table this
starves the single writer ("database is locked"); on any backend it is a
spurious write hidden inside a GET. `ensure_utc` must fix the naive timestamp
without ever dirtying the session.
"""
from datetime import UTC, datetime

from sqlmodel import Session, select

from raqib_api.models import Event
from raqib_api.tz import ensure_utc


def test_ensure_utc_preserves_an_already_aware_timestamp():
    aware = Event(id="01AAAAAAAAAAAAAAAAAAAAAAAA", site="s", camera="c", kind="footfall_tick",
                  severity=1, ts=datetime(2026, 1, 1, tzinfo=UTC), rule_id="R12")
    out = ensure_utc([aware])
    assert out[0].ts == aware.ts and out[0].ts.tzinfo is UTC
    assert out[0].id == aware.id and out[0].kind == aware.kind


def test_ensure_utc_never_marks_session_rows_dirty(client):  # client fixture wires a real sqlite session
    from conftest import make_event

    ev = make_event(0)
    client.post("/events/batch", json={"events": [ev]})

    from raqib_api import db as dbmod

    with Session(dbmod.engine) as session:
        rows = session.exec(select(Event)).all()
        assert rows[0].ts.tzinfo is None  # sqlite hands back naive datetimes
        fixed = ensure_utc(rows)
        assert fixed[0].ts.tzinfo is UTC
        assert rows[0].ts.tzinfo is None  # the original tracked row is untouched
        assert not session.dirty  # ensure_utc never marks anything for flush
        session.commit()  # would raise/attempt an UPDATE if anything were dirty


def test_ensure_utc_result_is_not_session_tracked_at_all(client):
    from conftest import make_event

    ev = make_event(0)
    client.post("/events/batch", json={"events": [ev]})

    from raqib_api import db as dbmod
    from raqib_api.models import Event as EventModel

    with Session(dbmod.engine) as session:
        rows = session.exec(select(Event)).all()
        fixed = ensure_utc(rows)
        assert not isinstance(fixed[0], EventModel)  # a plain value object, never mapped
        fixed[0].ts  # attribute access alone must not touch the session
        assert not session.dirty
