import numpy as np
import pandas as pd

from quantbot.data.quality import clean_ohlcv, validate_ohlcv
from quantbot.data.synthetic import generate_ohlcv


def test_clean_data_passes():
    df = generate_ohlcv(n=500, timeframe="1h", seed=1)
    rep = validate_ohlcv(df, "1h")
    assert rep.passed
    assert rep.n_ohlc_violations == 0
    assert rep.n_duplicates == 0


def test_detects_ohlc_violation():
    df = generate_ohlcv(n=200, timeframe="1h", seed=1)
    df.iloc[10, df.columns.get_loc("high")] = df.iloc[10]["low"] - 1  # high < low
    rep = validate_ohlcv(df, "1h")
    assert not rep.passed
    assert rep.n_ohlc_violations >= 1


def test_detects_gap():
    df = generate_ohlcv(n=200, timeframe="1h", seed=1)
    df = pd.concat([df.iloc[:50], df.iloc[80:]])  # drop 30 bars -> gap
    rep = validate_ohlcv(df, "1h")
    assert rep.n_gaps >= 1


def test_detects_nan():
    df = generate_ohlcv(n=100, timeframe="1h", seed=1)
    df.iloc[5, df.columns.get_loc("close")] = np.nan
    rep = validate_ohlcv(df, "1h")
    assert not rep.passed
    assert rep.n_nan >= 1


def test_clean_removes_duplicates():
    df = generate_ohlcv(n=100, timeframe="1h", seed=1)
    dup = pd.concat([df, df.iloc[[10, 20]]]).sort_index()
    cleaned = clean_ohlcv(dup)
    assert not cleaned.index.duplicated().any()
