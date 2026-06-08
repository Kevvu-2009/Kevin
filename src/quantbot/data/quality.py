"""OHLCV data-quality validation.

Bad data silently destroys backtests, so every dataset passes through these
checks before it is trusted.  Checks performed:

  * **monotonic, unique timestamps** (no duplicates / out-of-order bars)
  * **gap detection** vs the expected bar spacing for the timeframe
  * **OHLC sanity**: high >= max(open,close,low), low <= min(...), all > 0
  * **NaN / non-finite** values
  * **volume** non-negative
  * **extreme jumps**: bar-to-bar return beyond a z-score threshold flagged as
    a candidate anomaly (e.g. bad tick), not auto-dropped.

``validate_ohlcv`` returns a structured report; ``passed`` is False if any hard
check fails.  Gap counts are reported but do not by themselves fail a dataset
(exchanges legitimately have maintenance windows).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TIMEFRAME_SECONDS = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


@dataclass
class QualityReport:
    timeframe: str
    n_candles: int
    n_duplicates: int = 0
    n_gaps: int = 0
    n_ohlc_violations: int = 0
    n_nan: int = 0
    n_negative_volume: int = 0
    n_anomalies: int = 0
    gaps: list[tuple] = field(default_factory=list)
    passed: bool = True
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["gaps"] = [(str(a), str(b)) for a, b in self.gaps[:50]]
        return d


def validate_ohlcv(
    df: pd.DataFrame,
    timeframe: str,
    anomaly_z: float = 12.0,
) -> QualityReport:
    rep = QualityReport(timeframe=timeframe, n_candles=len(df))
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        rep.passed = False
        rep.messages.append(f"missing columns: {sorted(missing)}")
        return rep

    if df.empty:
        rep.passed = False
        rep.messages.append("empty dataframe")
        return rep

    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        rep.passed = False
        rep.messages.append("index is not a DatetimeIndex")
        return rep

    # Duplicates / ordering.
    rep.n_duplicates = int(idx.duplicated().sum())
    if rep.n_duplicates:
        rep.messages.append(f"{rep.n_duplicates} duplicate timestamps")
    if not idx.is_monotonic_increasing:
        rep.messages.append("timestamps not strictly increasing")
        rep.passed = False

    # Gap detection vs expected spacing.
    step = TIMEFRAME_SECONDS.get(timeframe)
    if step and len(idx) > 1:
        # Resolution-agnostic (works for ns/us/ms datetime64 and tz-aware).
        deltas = idx.to_series().diff().dropna().dt.total_seconds().to_numpy()
        gap_mask = deltas > step * 1.5
        rep.n_gaps = int(gap_mask.sum())
        for i in np.where(gap_mask)[0]:
            rep.gaps.append((idx[i], idx[i + 1]))

    # OHLC sanity.
    o, h, l, c, v = (df["open"], df["high"], df["low"], df["close"], df["volume"])
    ohlc_bad = (
        (h < l)
        | (h < o)
        | (h < c)
        | (l > o)
        | (l > c)
        | (o <= 0)
        | (c <= 0)
    )
    rep.n_ohlc_violations = int(ohlc_bad.sum())
    if rep.n_ohlc_violations:
        rep.passed = False
        rep.messages.append(f"{rep.n_ohlc_violations} OHLC sanity violations")

    # NaN / non-finite.
    rep.n_nan = int((~np.isfinite(df[["open", "high", "low", "close", "volume"]].to_numpy())).sum())
    if rep.n_nan:
        rep.passed = False
        rep.messages.append(f"{rep.n_nan} NaN/non-finite values")

    # Negative volume.
    rep.n_negative_volume = int((v < 0).sum())
    if rep.n_negative_volume:
        rep.passed = False
        rep.messages.append(f"{rep.n_negative_volume} negative volumes")

    # Anomalous returns (flag only).
    ret = np.log(c / c.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    if len(ret) > 20:
        z = (ret - ret.mean()) / (ret.std(ddof=0) or 1.0)
        rep.n_anomalies = int((z.abs() > anomaly_z).sum())
        if rep.n_anomalies:
            rep.messages.append(f"{rep.n_anomalies} anomalous return spikes (review)")

    return rep


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Best-effort cleaning: drop dup timestamps, sort, drop NaN rows."""
    out = df[~df.index.duplicated(keep="last")].sort_index()
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out
