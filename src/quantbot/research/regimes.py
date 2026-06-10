"""Market-regime detection.

Two orthogonal, deliberately simple axes (simple = hard to overfit, cheap to
compute identically in research and live):

* **Trend axis** — EMA(fast) vs EMA(slow) direction, qualified by ADX
  strength: +1 trending up, -1 trending down, 0 ranging.
* **Volatility axis** — realized vol vs its long rolling median:
  1 high-vol, 0 low-vol.

The cross product gives six regime labels used for (a) regime-gated signals
and (b) regime-conditioned performance breakdowns in validation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.features.core import realized_vol, trend_regime, vol_regime

REGIME_LABELS = (
    "trend_up_lowvol",
    "trend_up_highvol",
    "trend_down_lowvol",
    "trend_down_highvol",
    "range_lowvol",
    "range_highvol",
)


def detect_regimes(
    df: pd.DataFrame,
    fast: int = 50,
    slow: int = 200,
    adx_th: float = 20.0,
    vol_window: int = 20,
    vol_ref_window: int = 200,
) -> pd.DataFrame:
    """Per-bar regime axes + a combined string label.

    Returns columns: ``trend`` (-1/0/+1), ``high_vol`` (0/1), ``label`` (str).
    """
    trend = trend_regime(df, fast, slow, adx_th)
    hv = vol_regime(df["close"], vol_window, vol_ref_window)

    t = trend.to_numpy()
    v = hv.to_numpy()
    labels = np.empty(len(df), dtype=object)
    labels[(t > 0) & (v == 0)] = "trend_up_lowvol"
    labels[(t > 0) & (v == 1)] = "trend_up_highvol"
    labels[(t < 0) & (v == 0)] = "trend_down_lowvol"
    labels[(t < 0) & (v == 1)] = "trend_down_highvol"
    labels[(t == 0) & (v == 0)] = "range_lowvol"
    labels[(t == 0) & (v == 1)] = "range_highvol"

    return pd.DataFrame(
        {"trend": trend, "high_vol": hv, "label": pd.Series(labels, index=df.index)},
        index=df.index,
    )


def regime_performance(
    returns: pd.Series,
    regimes: pd.DataFrame,
    timeframe: str,
    min_bars: int = 50,
) -> dict[str, dict]:
    """Sharpe / total return / max-DD of a return stream within each regime.

    Bars are grouped by concurrent regime label; segments shorter than
    ``min_bars`` in total are skipped (no meaningful statistics).
    """
    from quantbot.backtest.metrics import max_drawdown, sharpe

    out: dict[str, dict] = {}
    labels = regimes["label"].reindex(returns.index)
    for label in REGIME_LABELS:
        r = returns[labels == label]
        if len(r) < min_bars:
            continue
        eq = (1.0 + r).cumprod()
        out[label] = {
            "n_bars": int(len(r)),
            "sharpe": sharpe(r, timeframe),
            "total_return": float(eq.iloc[-1] - 1.0),
            "max_drawdown": max_drawdown(eq),
        }
    return out
