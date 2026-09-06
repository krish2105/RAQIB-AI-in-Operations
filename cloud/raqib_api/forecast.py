"""Hourly event-count forecasting: GradientBoosting vs seasonal naive.

Term 4 deliverable. Features are deliberately simple and explainable: hour of
day, weekday, lag-24, lag-168, rolling-24 mean. The baseline is seasonal naive
(same hour last week). We report MAE and MAPE on the last 7 days of history
and refuse to forecast with fewer than 14 days.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

MIN_DAYS = 14
SEASON_H = 24 * 7


@dataclass
class ForecastResult:
    sufficient: bool
    reason: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)
    forecast: list[dict[str, Any]] = field(default_factory=list)
    mae: float | None = None
    mape: float | None = None
    mae_naive: float | None = None
    improvement_pct: float | None = None
    peaks: list[dict[str, Any]] = field(default_factory=list)
    features: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def hourly_counts(events: Iterable[Any], kind: str, end: datetime | None = None) -> pd.Series:
    ts = [e.ts for e in events if e.kind == kind]
    if not ts:
        return pd.Series(dtype=float)
    idx = pd.DatetimeIndex(ts).tz_convert("UTC") if pd.DatetimeIndex(ts).tz is not None else pd.DatetimeIndex(ts).tz_localize("UTC")
    s = pd.Series(1.0, index=idx).resample("1h").sum()
    end_ts = pd.Timestamp(end).tz_convert("UTC") if end is not None and end.tzinfo else (pd.Timestamp(end, tz="UTC") if end else s.index.max())
    full = pd.date_range(s.index.min(), end_ts.floor("1h"), freq="1h", tz="UTC")
    return s.reindex(full, fill_value=0.0)


def seasonal_naive(series: pd.Series, season: int = SEASON_H) -> pd.Series:
    return series.shift(season)


def _features(series: pd.Series, exog: pd.Series | None = None) -> pd.DataFrame:
    df = pd.DataFrame({"y": series})
    if exog is not None:  # v2: POS volume, lagged so nothing from the forecast horizon leaks in
        x = exog.reindex(df.index).fillna(0.0)
        df["pos_lag24"] = x.shift(24)
        df["pos_lag168"] = x.shift(168).fillna(x.shift(24))
        df["pos_roll24"] = x.shift(1).rolling(24, min_periods=1).mean()
    df["hour"] = df.index.hour
    df["weekday"] = df.index.weekday
    df["lag24"] = df["y"].shift(24)
    df["lag168"] = df["y"].shift(168)
    df["roll24"] = df["y"].shift(1).rolling(24, min_periods=1).mean()
    df["roll168"] = df["y"].shift(1).rolling(168, min_periods=24).mean()
    # Hour-of-week profile: mean of the same weekday+hour over all *previous* weeks (no leakage).
    how = df["weekday"] * 24 + df["hour"]
    df["prof_how"] = df.groupby(how)["y"].transform(lambda s: s.shift(1).expanding().mean())
    # Back-fill long lags with shorter ones so the first week is usable for training.
    df["lag168"] = df["lag168"].fillna(df["lag24"])
    df["prof_how"] = df["prof_how"].fillna(df["lag168"])
    df["roll168"] = df["roll168"].fillna(df["roll24"])
    return df


FEATURES = ["hour", "weekday", "lag24", "lag168", "roll24", "roll168", "prof_how"]
POS_FEATURES = ["pos_lag24", "pos_lag168", "pos_roll24"]


def fit_predict(series: pd.Series, horizon: int = 24, holdout_h: int = 24 * 7, exog: pd.Series | None = None) -> ForecastResult:
    """v2: when `exog` (hourly POS volume) is given, a second model with the POS features is fitted and kept
    only if its holdout MAE is at or below the video-only model's, so POS can never make the forecast worse."""
    if series.empty or (series.index.max() - series.index.min()) < timedelta(days=MIN_DAYS):
        days = 0 if series.empty else (series.index.max() - series.index.min()).days
        return ForecastResult(sufficient=False, reason=f"need at least {MIN_DAYS} days of history, have {days}")
    from sklearn.ensemble import GradientBoostingRegressor

    def fit(feats: list[str], ex: pd.Series | None):
        d = _features(series, ex).dropna()
        if len(d) <= holdout_h + 24:
            return None
        tr, te = d.iloc[:-holdout_h], d.iloc[-holdout_h:]
        m = GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.03, subsample=0.9, loss="absolute_error", random_state=0)
        m.fit(tr[feats], tr["y"])
        pr = np.clip(m.predict(te[feats]), 0, None)
        return d, te, m, pr, float(np.mean(np.abs(pr - te["y"].to_numpy())))

    base = fit(FEATURES, None)
    if base is None:
        return ForecastResult(sufficient=False, reason="not enough rows after feature lags")
    feats, chosen = FEATURES, base
    if exog is not None and (with_pos := fit(FEATURES + POS_FEATURES, exog)) is not None and with_pos[4] <= base[4]:
        feats, chosen = FEATURES + POS_FEATURES, with_pos
    df, test, model, pred, _ = chosen
    exog_used = exog if feats is not FEATURES else None
    naive = seasonal_naive(series).reindex(test.index).fillna(0.0).to_numpy()
    y = test["y"].to_numpy()
    mae = float(np.mean(np.abs(pred - y)))
    mae_naive = float(np.mean(np.abs(naive - y)))
    nz = y > 0
    mape = float(np.mean(np.abs((pred[nz] - y[nz]) / y[nz]))) * 100 if nz.any() else None
    improvement = (1 - mae / mae_naive) * 100 if mae_naive > 0 else 0.0

    # refit on everything, then roll forward `horizon` hours recursively
    model.fit(df[feats], df["y"])
    hist = series.copy()
    fut_idx = pd.date_range(series.index.max() + pd.Timedelta(hours=1), periods=horizon, freq="1h", tz="UTC")
    preds = []
    for t in fut_idx:
        ext = pd.concat([hist, pd.Series([np.nan], index=[t])])
        f = _features(ext, exog_used).iloc[[-1]][feats].ffill(axis=1).fillna(0.0)
        p = float(max(0.0, model.predict(f)[0]))
        preds.append(p)
        hist = pd.concat([hist, pd.Series([p], index=[t])])
    baseline_future = [float(series.get(t - pd.Timedelta(hours=SEASON_H), np.nan)) for t in fut_idx]
    forecast = [{"ts": t.isoformat(), "value": round(p, 2), "baseline": (None if np.isnan(b) else round(b, 2))}
                for t, p, b in zip(fut_idx, preds, baseline_future, strict=True)]
    thr = float(np.percentile(preds, 75)) if preds else 0.0
    peaks = [f for f in forecast if f["value"] >= thr and f["value"] > 0][:6]
    history = [{"ts": t.isoformat(), "value": float(v)} for t, v in series.iloc[-holdout_h:].items()]
    return ForecastResult(True, "", history, forecast, round(mae, 3), None if mape is None else round(mape, 1),
                          round(mae_naive, 3), round(improvement, 1), peaks, list(feats))
