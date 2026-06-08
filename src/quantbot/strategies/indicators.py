"""Vectorized technical indicators (pandas/numpy only).

All functions are pure and operate on pandas Series/DataFrame.  They are kept
free of any IO so they can be unit-tested in isolation and reused by both the
backtester and the live engine (identical code path = no train/serve skew).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    tr = true_range(high, low, close)
    # Wilder smoothing == EMA with alpha = 1/period.
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss == 0 -> RSI 100; when avg_gain == 0 -> RSI 0.
    out = out.where(avg_loss != 0.0, 100.0)
    out = out.where(avg_gain != 0.0, out.where(avg_loss == 0.0, 0.0))
    return out


def bollinger_bands(
    close: pd.Series, period: int = 20, n_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (lower, middle, upper) Bollinger Bands."""
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std(ddof=0)
    upper = mid + n_std * std
    lower = mid - n_std * std
    return lower, mid, upper


def donchian_channels(
    high: pd.Series, low: pd.Series, period: int = 20
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (lower, middle, upper) Donchian channels.

    The channels are computed on data *up to and including* the current bar.
    Breakout strategies must compare the current close against the channel from
    the *prior* bar to avoid look-ahead (handled in the strategy).
    """
    upper = high.rolling(period, min_periods=period).max()
    lower = low.rolling(period, min_periods=period).min()
    mid = (upper + lower) / 2.0
    return lower, mid, upper


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std(ddof=0)
    return (series - mean) / std.replace(0.0, np.nan)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index — trend-strength gauge (0-100)."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move

    atr_ = atr(high, low, close, period)
    plus_di = 100 * (plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_)
    minus_di = 100 * (minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def realized_volatility(close: pd.Series, window: int = 20, periods_per_year: int = 365) -> pd.Series:
    """Annualised rolling volatility of log returns."""
    logret = np.log(close / close.shift(1))
    return logret.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(periods_per_year)
