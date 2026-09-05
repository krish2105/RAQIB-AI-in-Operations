from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from raqib_api.forecast import fit_predict, hourly_counts, seasonal_naive
from raqib_api.simulate import generate


def _series(days=21, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-08-01", periods=24 * days, freq="1h", tz="UTC")
    h = idx.hour.to_numpy()
    wd = idx.weekday.to_numpy()
    base = 20 + 25 * np.exp(-((h - 13) ** 2) / 4) + 35 * np.exp(-((h - 19.5) ** 2) / 3)
    base = base * np.where(wd >= 3, 1.3, 1.0)
    base[(h < 8) | (h >= 23)] = 0
    y = np.clip(rng.poisson(base).astype(float), 0, None)
    return pd.Series(y, index=idx)


def test_gbr_beats_seasonal_naive_on_seasonal_series():
    s = _series()
    res = fit_predict(s, horizon=24)
    assert res.sufficient
    assert res.mae < res.mae_naive, (res.mae, res.mae_naive)
    assert res.improvement_pct > 0
    assert len(res.forecast) == 24 and all(f["value"] >= 0 for f in res.forecast)
    assert res.peaks and res.features


def test_insufficient_history_is_reported_not_faked():
    res = fit_predict(_series(days=5))
    assert not res.sufficient and "14 days" in res.reason
    assert fit_predict(pd.Series(dtype=float)).sufficient is False


def test_hourly_counts_and_naive_from_simulated_events():
    end = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    rows = generate("demo", "retail", days=3, seed=1, end=end, tills=3)
    from types import SimpleNamespace

    events = [SimpleNamespace(ts=datetime.fromisoformat(r["ts"]), kind=r["kind"], payload=r["payload"]) for r in rows]
    s = hourly_counts(events, "footfall_tick", end=end)
    assert len(s) >= 24 * 3 - 1
    assert s.sum() == sum(1 for e in events if e.kind == "footfall_tick")
    assert seasonal_naive(s).iloc[:168].isna().all()
    assert all(r["payload"]["simulated"] is True for r in rows)
    assert (end - datetime.fromisoformat(rows[0]["ts"])) <= timedelta(days=3, minutes=5)
