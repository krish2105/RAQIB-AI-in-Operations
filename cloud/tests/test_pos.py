"""POS: CSV import with validation and dedupe; μ from POS labelled and different from video; forecast never worse with POS."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from raqib_api.forecast import FEATURES, POS_FEATURES, fit_predict, hourly_counts
from raqib_api.integrations.pos import (
    CsvAdapter,
    NotConfigured,
    OdooAdapter,
    ShopifyAdapter,
    import_rows,
    parse_csv,
    sample_csv,
)
from raqib_api.models import Event, PosTransaction, Site
from raqib_api.ops_theory import slot_rates
from raqib_api.simulate import generate
from raqib_api.tz import ensure_utc

SITE = "raqib_demo_store"
NOW = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
CSV = "ts,till,txn_id,items,amount\n2026-09-06T10:00:00Z,1,T1,3,12.5\n2026-09-06T10:04:00Z,2,T2,1,4.0\n2026-09-06T10:05:00Z,1,T3,7,31.9\n"


@pytest.fixture()
def eng():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(e)
    with Session(e) as s:
        s.add(Site(name=SITE, profile="retail", tills=3))
        s.commit()
    return e


def test_parse_validates_and_reports_lines():
    rows, errors = parse_csv(CSV)
    assert len(rows) == 3 and not errors and rows[0].ts.tzinfo is not None and rows[2].amount == 31.9
    bad = ("ts,till,txn_id,items,amount\nnot-a-date,1,X,1,1\n2026-09-06T10:00:00Z,0,Y,1,1\n2026-09-06T10:00:00Z,1,Y,1,1\n"
           "2026-09-06T10:00:00Z,1,Z,1,1\n2026-09-06T10:01:00Z,1,Z,2,2\n")
    rows, errors = parse_csv(bad)
    assert [r.txn_id for r in rows] == ["Y", "Z"] and len(errors) == 3 and errors[0].startswith("line 2")
    assert "duplicate txn_id Z" in errors[2] and "till < 1" in errors[1]
    assert parse_csv("a,b\n1,2\n")[1][0].startswith("columns must be exactly")


def test_importing_the_same_csv_twice_inserts_once(eng):
    with Session(eng) as s:
        first = import_rows(SITE, CsvAdapter(CSV).fetch(), s)
        second = import_rows(SITE, CsvAdapter(CSV).fetch(), s)
        assert (first.inserted, first.duplicates) == (3, 0) and (second.inserted, second.duplicates) == (0, 3)
        assert len(s.exec(select(PosTransaction)).all()) == 3
        assert import_rows("other-site", CsvAdapter(CSV).fetch(), s).inserted == 3  # dedupe is per site


def test_adapters_share_the_interface_and_stubs_fail_loudly():
    assert CsvAdapter(CSV).name == "csv" and len(CsvAdapter(CSV).fetch(since=datetime(2026, 9, 6, 10, 3, tzinfo=UTC))) == 2
    with pytest.raises(NotConfigured):
        OdooAdapter().fetch()
    with pytest.raises(NotConfigured):
        ShopifyAdapter().fetch()


def _seed(days=21):
    rows = generate(SITE, "retail", days=days, seed=7, end=NOW, tills=3)
    evs = []
    for r in rows:
        r2 = dict(r)
        r2["ts"] = datetime.fromisoformat(r2["ts"])
        evs.append(Event(**r2))
    return ensure_utc(evs)


def test_mu_from_pos_differs_from_video_and_is_labelled():
    events = _seed(days=2)
    rows, _ = parse_csv(sample_csv(events))
    assert rows and all(r.txn_id.startswith("SIM-") for r in rows)  # simulated stays labelled
    video = slot_rates(events, tills_open=3)
    with_pos = slot_rates(events, tills_open=3, pos=rows)
    assert len(video) == len(with_pos) or len(with_pos) >= len(video)
    pos_slots = [x for x in with_pos if x.mu_source == "pos"]
    assert pos_slots and all(x.mu_source == "estimated_from_video" for x in video)
    diffs = [abs(a.mu_per_h - b.mu_per_h) for a, b in zip(video, with_pos, strict=False) if b.mu_source == "pos" and a.served > 0]
    assert diffs and max(diffs) > 1.0  # throughput per till is not the same number as 3600/dwell


def test_forecast_with_pos_feature_is_never_worse():
    events = _seed(days=21)
    series = hourly_counts(events, "footfall_tick", end=NOW)
    rows, _ = parse_csv(sample_csv(events))
    pos_series = pd.Series(1.0, index=pd.DatetimeIndex([r.ts for r in rows])).resample("1h").sum().reindex(series.index).fillna(0.0)
    base = fit_predict(series, horizon=24)
    with_pos = fit_predict(series, horizon=24, exog=pos_series)
    assert base.sufficient and with_pos.sufficient
    assert with_pos.mae <= base.mae
    assert with_pos.features in (FEATURES, FEATURES + POS_FEATURES)
    assert with_pos.features == FEATURES + POS_FEATURES or with_pos.mae == base.mae  # POS features only when they help


def test_pos_api_import_summary_sample_and_kpis(client):
    client.post("/admin/seed", params={"site": SITE, "days": 3, "run_agent_last_hours": 0})
    sample = client.get("/pos/sample", params={"site": SITE, "days": 3})
    assert sample.status_code == 200 and sample.text.startswith("ts,till,txn_id,items,amount")
    r = client.post("/pos/import", data={"site": SITE}, files={"file": ("pos.csv", sample.text.encode(), "text/csv")})
    assert r.status_code == 201 and r.json()["inserted"] > 0 and r.json()["invalid"] == 0
    again = client.post("/pos/import", data={"site": SITE}, files={"file": ("pos.csv", sample.text.encode(), "text/csv")}).json()
    assert again["inserted"] == 0 and again["duplicates"] == r.json()["inserted"]
    sm = client.get("/pos/summary", params={"site": SITE}).json()
    assert sm["transactions"] == r.json()["inserted"] and sm["mu_source"] == "pos" and sm["mu_pos_per_h"] and sm["adapters"]["odoo"].startswith("stub")
    kp = client.get("/kpis", params={"site": SITE, "window_h": 72}).json()
    assert kp["queue_model"] and any(x["mu_source"] == "pos" for x in kp["queue_model"])
    assert client.post("/pos/import", data={"site": SITE}, files={"file": ("x.txt", b"a", "text/plain")}).status_code == 415
    assert client.post("/pos/import", data={"site": SITE}, files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}).status_code == 422
    assert client.get("/pos/transactions", params={"site": SITE, "limit": 5}).json()[0]["txn_id"].startswith("SIM-")
