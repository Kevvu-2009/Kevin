import numpy as np
import pandas as pd
import pytest

from quantbot.strategies import indicators as ind


def test_ema_matches_pandas_ewm():
    s = pd.Series(np.arange(1, 101, dtype=float))
    out = ind.ema(s, 10)
    expected = s.ewm(span=10, adjust=False, min_periods=10).mean()
    pd.testing.assert_series_equal(out, expected)


def test_atr_positive_and_warmup():
    n = 200
    rng = np.random.default_rng(0)
    close = pd.Series(100 + np.cumsum(rng.standard_normal(n)))
    high = close + 1.0
    low = close - 1.0
    a = ind.atr(high, low, close, 14)
    assert a.iloc[20:].notna().all()
    assert (a.dropna() >= 0).all()


def test_rsi_bounds():
    rng = np.random.default_rng(1)
    close = pd.Series(100 + np.cumsum(rng.standard_normal(500)))
    r = ind.rsi(close, 14).dropna()
    assert r.between(0, 100).all()


def test_rsi_all_up_is_high():
    close = pd.Series(np.arange(1, 60, dtype=float))
    r = ind.rsi(close, 14).dropna()
    assert (r > 95).all()


def test_bollinger_ordering():
    rng = np.random.default_rng(2)
    close = pd.Series(100 + np.cumsum(rng.standard_normal(300)))
    lower, mid, upper = ind.bollinger_bands(close, 20, 2.0)
    valid = mid.dropna().index
    assert (upper.loc[valid] >= mid.loc[valid]).all()
    assert (mid.loc[valid] >= lower.loc[valid]).all()


def test_donchian_contains_price():
    rng = np.random.default_rng(3)
    n = 300
    close = pd.Series(100 + np.cumsum(rng.standard_normal(n)))
    high = close + 0.5
    low = close - 0.5
    lower, mid, upper = ind.donchian_channels(high, low, 20)
    valid = upper.dropna().index
    assert (upper.loc[valid] >= high.loc[valid] - 1e-9).all()
    assert (lower.loc[valid] <= low.loc[valid] + 1e-9).all()


def test_adx_range():
    rng = np.random.default_rng(4)
    close = pd.Series(100 + np.cumsum(rng.standard_normal(400)))
    high = close + 1
    low = close - 1
    a = ind.adx(high, low, close, 14).dropna()
    assert a.between(0, 100).all()
