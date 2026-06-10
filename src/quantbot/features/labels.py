"""Label construction for supervised models.

Labels look *forward*; features look *backward*.  Any cross-validation over
(feature, label) pairs must purge training samples whose label window overlaps
the test window and embargo a buffer after it — see ``quantbot.models.cv``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.strategies import indicators as ind


def forward_return(close: pd.Series, horizon: int) -> pd.Series:
    """Simple forward return over ``horizon`` bars (NaN for the final bars)."""
    return close.shift(-horizon) / close - 1.0


def classification_labels(
    close: pd.Series,
    horizon: int,
    deadzone: float = 0.0,
) -> pd.Series:
    """Binary up/down labels with an optional cost-aware deadzone.

    deadzone: moves smaller than this (e.g. round-trip cost) are labelled NaN
    and excluded from training — the model should not learn to predict noise
    it could never monetise.
    """
    fwd = forward_return(close, horizon)
    y = pd.Series(np.nan, index=close.index)
    y[fwd > deadzone] = 1.0
    y[fwd < -deadzone] = 0.0
    return y


def triple_barrier_labels(
    df: pd.DataFrame,
    horizon: int,
    tp_atr: float = 2.0,
    sl_atr: float = 1.0,
    atr_period: int = 14,
) -> pd.Series:
    """First-touch labels: +1 if the take-profit barrier (entry + tp_atr*ATR)
    is hit before the stop barrier (entry - sl_atr*ATR) within ``horizon``
    bars, 0 if the stop is hit first, NaN on timeout (no decisive move).

    Mirrors how the live system actually exits (ATR stops/targets), so the
    model learns the payoff that will be traded, not an abstract return.
    """
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    atr = ind.atr(df["high"], df["low"], df["close"], atr_period).to_numpy(dtype=float)
    n = len(df)
    out = np.full(n, np.nan)
    for i in range(n - 1):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        up = close[i] + tp_atr * a
        dn = close[i] - sl_atr * a
        end = min(n, i + 1 + horizon)
        for j in range(i + 1, end):
            hit_dn = low[j] <= dn
            hit_up = high[j] >= up
            if hit_dn:          # conservative: stop assumed first if both hit
                out[i] = 0.0
                break
            if hit_up:
                out[i] = 1.0
                break
    return pd.Series(out, index=df.index)
