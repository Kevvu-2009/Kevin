"""Causal feature library.

Conventions
-----------
* Input is an OHLCV frame indexed by UTC timestamps (ascending).
* The feature value at bar ``t`` may use bar ``t``'s OHLCV (it is "as of the
  close of t") but never anything later.  Rolling windows therefore include
  the current bar; *shift(1)* is applied only where a reference must be
  strictly prior (e.g. breakout levels).
* Features are unit-stable (returns, z-scores, ratios) so models trained on
  one symbol/period transfer to another without rescaling.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.strategies import indicators as ind

# ----------------------------------------------------------------- primitives


def returns(close: pd.Series, periods: int = 1) -> pd.Series:
    return close.pct_change(periods)


def log_returns(close: pd.Series, periods: int = 1) -> pd.Series:
    return np.log(close).diff(periods)


def realized_vol(close: pd.Series, window: int = 20) -> pd.Series:
    """Rolling std of 1-bar log returns (per-bar units, not annualised)."""
    return log_returns(close).rolling(window).std(ddof=0)


def vol_of_vol(close: pd.Series, window: int = 20) -> pd.Series:
    rv = realized_vol(close, window)
    return rv.rolling(window).std(ddof=0) / rv.rolling(window).mean()


def atr_pct(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR as a fraction of price — comparable across symbols."""
    return ind.atr(df["high"], df["low"], df["close"], period) / df["close"]


def zscore(series: pd.Series, window: int = 50) -> pd.Series:
    mean = series.rolling(window).mean()
    std = series.rolling(window).std(ddof=0)
    return (series - mean) / std.replace(0.0, np.nan)


def ema_distance(close: pd.Series, span: int) -> pd.Series:
    """Distance of price from its EMA, in EMA units (trend strength + side)."""
    e = ind.ema(close, span)
    return close / e - 1.0


def momentum(close: pd.Series, lookback: int) -> pd.Series:
    return close / close.shift(lookback) - 1.0


def efficiency_ratio(close: pd.Series, window: int = 20) -> pd.Series:
    """Kaufman efficiency ratio: |net move| / sum |bar moves| in [0, 1].

    ~1 = clean trend, ~0 = chop.  A cheap, robust trendiness gauge.
    """
    net = (close - close.shift(window)).abs()
    path = close.diff().abs().rolling(window).sum()
    return net / path.replace(0.0, np.nan)


def variance_ratio(close: pd.Series, window: int = 100, q: int = 5) -> pd.Series:
    """Lo-MacKinlay style variance ratio: var(q-bar ret) / (q * var(1-bar ret)).

    > 1 suggests positive autocorrelation (momentum), < 1 mean reversion.
    """
    r1 = log_returns(close)
    rq = log_returns(close, q)
    v1 = r1.rolling(window).var(ddof=0)
    vq = rq.rolling(window).var(ddof=0)
    return vq / (q * v1.replace(0.0, np.nan))


def rolling_autocorr(close: pd.Series, window: int = 50, lag: int = 1) -> pd.Series:
    r = close.pct_change()
    return r.rolling(window).corr(r.shift(lag))


def drawdown_from_high(close: pd.Series, window: int = 50) -> pd.Series:
    return close / close.rolling(window).max() - 1.0


def runup_from_low(close: pd.Series, window: int = 50) -> pd.Series:
    return close / close.rolling(window).min() - 1.0


def donchian_position(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Where the close sits inside the prior N-bar high/low channel, in [0,1]."""
    hi = df["high"].rolling(window).max().shift(1)
    lo = df["low"].rolling(window).min().shift(1)
    rng = (hi - lo).replace(0.0, np.nan)
    return ((df["close"] - lo) / rng).clip(0.0, 1.0)


def bollinger_features(close: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    mid, upper, lower = ind.bollinger_bands(close, window, n_std)
    rng = (upper - lower).replace(0.0, np.nan)
    pct_b = (close - lower) / rng
    bandwidth = rng / mid
    return pd.DataFrame({"bb_pct_b": pct_b, "bb_bandwidth": bandwidth})


# --------------------------------------------------------------- volume/flow


def volume_zscore(volume: pd.Series, window: int = 50) -> pd.Series:
    return zscore(np.log1p(volume), window)


def volume_momentum(volume: pd.Series, fast: int = 10, slow: int = 50) -> pd.Series:
    return ind.ema(volume, fast) / ind.ema(volume, slow).replace(0.0, np.nan) - 1.0


def close_location_value(df: pd.DataFrame) -> pd.Series:
    """CLV in [-1, 1]: where the close sits within the bar's range.

    A crude order-flow proxy: closes near the high suggest buyer-dominated
    flow during the bar, closes near the low seller-dominated flow.
    """
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng
    return clv.fillna(0.0)


def signed_volume_flow(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Accumulation/distribution proxy: rolling z-score of CLV-signed volume."""
    sv = close_location_value(df) * df["volume"]
    flow = sv.rolling(window).sum()
    return zscore(flow, max(window * 3, 60))


def body_range_ratio(df: pd.DataFrame) -> pd.Series:
    """|close-open| / (high-low): conviction of the bar (1 = full-body candle)."""
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    return ((df["close"] - df["open"]).abs() / rng).fillna(0.0)


def gap_pct(df: pd.DataFrame) -> pd.Series:
    return df["open"] / df["close"].shift(1) - 1.0


# ------------------------------------------------------------ time / session


def time_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Cyclical encodings of hour-of-day and day-of-week (UTC)."""
    hour = index.hour + index.minute / 60.0
    dow = index.dayofweek.to_numpy(dtype=float)
    return pd.DataFrame(
        {
            "hod_sin": np.sin(2 * np.pi * hour / 24.0),
            "hod_cos": np.cos(2 * np.pi * hour / 24.0),
            "dow_sin": np.sin(2 * np.pi * dow / 7.0),
            "dow_cos": np.cos(2 * np.pi * dow / 7.0),
        },
        index=index,
    )


def session_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Coarse trading-session flags (UTC).  Crypto is 24/7 but flow is not:
    volatility and volume cluster around US/EU equity hours.
    """
    h = index.hour
    return pd.DataFrame(
        {
            "sess_asia": ((h >= 0) & (h < 8)).astype(float),
            "sess_europe": ((h >= 7) & (h < 16)).astype(float),
            "sess_us": ((h >= 13) & (h < 22)).astype(float),
            "weekend": (index.dayofweek >= 5).astype(float),
        },
        index=index,
    )


# --------------------------------------------------------- multi-timeframe


_RESAMPLE_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample to a higher timeframe, indexed by bar COMPLETION time.

    Standard resampling labels a bar by its *start*; joining that to a lower
    timeframe leaks the future (the 4h close stamped 00:00 is not known until
    04:00).  We therefore shift the index to the bar end before any join.
    """
    out = df.resample(rule, label="left", closed="left").agg(_RESAMPLE_AGG).dropna()
    out.index = out.index + pd.tseries.frequencies.to_offset(rule)
    return out


def multi_timeframe_feature(
    df: pd.DataFrame,
    rule: str,
    fn,
    name: str | None = None,
) -> pd.Series:
    """Compute ``fn(htf_frame) -> Series`` on a higher timeframe and align it
    back to ``df``'s index without lookahead (forward-fill from completion).
    """
    htf = resample_ohlcv(df, rule)
    feat = fn(htf)
    aligned = feat.reindex(df.index, method="ffill")
    if name:
        aligned.name = name
    return aligned


# ------------------------------------------------------------- regime tags


def trend_regime(df: pd.DataFrame, fast: int = 50, slow: int = 200, adx_th: float = 20.0) -> pd.Series:
    """+1 uptrend / -1 downtrend / 0 chop, from EMA stack + ADX strength."""
    close = df["close"]
    ema_f = ind.ema(close, fast)
    ema_s = ind.ema(close, slow)
    adx = ind.adx(df["high"], df["low"], close, 14)
    direction = np.sign(ema_f - ema_s)
    strong = adx > adx_th
    return pd.Series(np.where(strong, direction, 0.0), index=df.index)


def vol_regime(close: pd.Series, window: int = 20, ref_window: int = 200) -> pd.Series:
    """1 = high-vol (RV above its rolling median), 0 = low-vol."""
    rv = realized_vol(close, window)
    med = rv.rolling(ref_window).median()
    return (rv > med).astype(float)


# ------------------------------------------------------------ feature matrix

#: name -> short description; the default model feature set.
FEATURE_CATALOG: dict[str, str] = {
    "ret_1": "1-bar return",
    "ret_3": "3-bar return",
    "ret_12": "12-bar return",
    "ret_48": "48-bar return",
    "mom_24": "24-bar momentum",
    "mom_96": "96-bar momentum",
    "rv_20": "20-bar realized vol",
    "rv_ratio": "fast/slow realized-vol ratio (expansion)",
    "atr_pct": "ATR / price",
    "vol_of_vol": "vol of vol",
    "ema_dist_20": "close vs EMA20",
    "ema_dist_100": "close vs EMA100",
    "adx_14": "ADX(14) / 50",
    "eff_ratio": "Kaufman efficiency ratio",
    "var_ratio": "variance ratio (momentum vs reversion)",
    "autocorr_1": "rolling lag-1 autocorrelation",
    "rsi_14": "RSI(14) / 100 centred",
    "bb_pct_b": "Bollinger %B",
    "bb_bandwidth": "Bollinger bandwidth",
    "donch_pos_20": "position in 20-bar Donchian channel",
    "dd_50": "drawdown from 50-bar high",
    "vol_z": "volume z-score",
    "vol_mom": "volume momentum",
    "clv": "close-location value (flow proxy)",
    "flow_z": "signed-volume flow z-score",
    "body_range": "candle body/range ratio",
    "gap": "open gap vs prior close",
    "trend_reg": "trend regime (-1/0/+1)",
    "vol_reg": "vol regime (0/1)",
    "hod_sin": "hour-of-day (sin)",
    "hod_cos": "hour-of-day (cos)",
    "dow_sin": "day-of-week (sin)",
    "dow_cos": "day-of-week (cos)",
    "sess_asia": "Asia session flag",
    "sess_europe": "Europe session flag",
    "sess_us": "US session flag",
    "weekend": "weekend flag",
    "htf_trend": "higher-timeframe EMA trend (completed bars only)",
}


def build_feature_matrix(df: pd.DataFrame, htf_rule: str = "1D") -> pd.DataFrame:
    """The default, leakage-safe feature matrix used by the ML signals.

    Returns a frame aligned to ``df.index``; leading rows contain NaNs until
    the longest lookback is warm (callers drop them together with labels).
    """
    close = df["close"]
    feats = pd.DataFrame(index=df.index)
    feats["ret_1"] = returns(close, 1)
    feats["ret_3"] = returns(close, 3)
    feats["ret_12"] = returns(close, 12)
    feats["ret_48"] = returns(close, 48)
    feats["mom_24"] = momentum(close, 24)
    feats["mom_96"] = momentum(close, 96)
    rv20 = realized_vol(close, 20)
    feats["rv_20"] = rv20
    feats["rv_ratio"] = rv20 / realized_vol(close, 100).replace(0.0, np.nan)
    feats["atr_pct"] = atr_pct(df, 14)
    feats["vol_of_vol"] = vol_of_vol(close, 20)
    feats["ema_dist_20"] = ema_distance(close, 20)
    feats["ema_dist_100"] = ema_distance(close, 100)
    feats["adx_14"] = ind.adx(df["high"], df["low"], close, 14) / 50.0
    feats["eff_ratio"] = efficiency_ratio(close, 20)
    feats["var_ratio"] = variance_ratio(close, 100, 5)
    feats["autocorr_1"] = rolling_autocorr(close, 50, 1)
    feats["rsi_14"] = ind.rsi(close, 14) / 100.0 - 0.5
    feats = feats.join(bollinger_features(close, 20, 2.0))
    feats["donch_pos_20"] = donchian_position(df, 20)
    feats["dd_50"] = drawdown_from_high(close, 50)
    feats["vol_z"] = volume_zscore(df["volume"], 50)
    feats["vol_mom"] = volume_momentum(df["volume"], 10, 50)
    feats["clv"] = close_location_value(df)
    feats["flow_z"] = signed_volume_flow(df, 20)
    feats["body_range"] = body_range_ratio(df)
    feats["gap"] = gap_pct(df)
    feats["trend_reg"] = trend_regime(df)
    feats["vol_reg"] = vol_regime(close)
    feats = feats.join(time_features(df.index))
    feats = feats.join(session_features(df.index))
    feats["htf_trend"] = multi_timeframe_feature(
        df, htf_rule, lambda h: np.sign(ind.ema(h["close"], 10) - ind.ema(h["close"], 30))
    )
    # Replace infs produced by degenerate denominators; models handle NaN rows
    # by exclusion upstream.
    return feats.replace([np.inf, -np.inf], np.nan)
