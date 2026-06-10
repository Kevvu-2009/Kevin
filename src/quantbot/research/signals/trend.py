"""Trend-following signal family.

Shared thesis: crypto exhibits persistent multi-week trends driven by
reflexive flows (FOMO/leverage cascades), slow-moving narrative capital, and
the absence of an index-arbitrage anchor.  Trend following is the most
durable documented anomaly across asset classes (Moskowitz, Ooi & Pedersen
2012; Hurst, Ooi & Pedersen 2017) and crypto's retail-heavy, momentum-chasing
flow makes it a natural habitat.

Shared risks: chop/range markets bleed via whipsaw; crowding compresses the
edge; violent V-reversals (exchange failures, regulatory shocks) hit before
slow filters react.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.features.core import efficiency_ratio, multi_timeframe_feature, volume_zscore
from quantbot.research.signals.base import ResearchSignal, hysteresis_positions, register_signal
from quantbot.strategies import indicators as ind


@register_signal
class EMACrossSignal(ResearchSignal):
    name = "ema_cross"
    family = "trend"
    default_params = {"fast": 50, "slow": 200, "allow_short": True}
    grid = {"fast": [20, 50, 80], "slow": [120, 200, 300]}
    thesis = (
        "An EMA stack is a low-pass filter on price: holding the side of the "
        "slow trend harvests the autocorrelation of crypto returns at "
        "multi-week horizons."
    )
    persistence = (
        "Requires sitting through deep give-backs, which most participants "
        "cannot do behaviourally or contractually; capacity is huge, so "
        "arbitrage does not eliminate it."
    )
    risks = "Extended ranges; regime shift to efficient/mean-reverting microstructure."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        if int(p["fast"]) >= int(p["slow"]):
            return pd.Series(0.0, index=df.index)
        fast = ind.ema(df["close"], int(p["fast"]))
        slow = ind.ema(df["close"], int(p["slow"]))
        up = (fast > slow).astype(float)
        pos = up if not p.get("allow_short", True) else 2.0 * up - 1.0
        # No signal until the slow EMA is warm.
        pos.iloc[: int(p["slow"])] = 0.0
        return pos


@register_signal
class SMACrossSignal(ResearchSignal):
    name = "sma_cross"
    family = "trend"
    default_params = {"fast": 20, "slow": 100, "allow_short": True}
    grid = {"fast": [10, 20, 40], "slow": [60, 100, 150]}
    thesis = "Simple-MA variant of the trend filter; slower turnover, fewer whipsaws."
    persistence = "Same behavioural/capacity argument as all slow trend systems."
    risks = "Identical to ema_cross; slightly later entries cost in fast trends."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        if int(p["fast"]) >= int(p["slow"]):
            return pd.Series(0.0, index=df.index)
        fast = ind.sma(df["close"], int(p["fast"]))
        slow = ind.sma(df["close"], int(p["slow"]))
        up = (fast > slow).astype(float)
        pos = up if not p.get("allow_short", True) else 2.0 * up - 1.0
        pos[slow.isna()] = 0.0
        return pos


@register_signal
class DonchianBreakoutSignal(ResearchSignal):
    name = "donchian_breakout"
    family = "trend"
    default_params = {"entry": 55, "exit": 20, "allow_short": True}
    grid = {"entry": [20, 55, 100], "exit": [10, 20, 50]}
    thesis = (
        "N-bar highs/lows are focal points: breakouts force stop-outs and "
        "chase entries, creating self-reinforcing follow-through (the classic "
        "turtle/Donchian edge)."
    )
    persistence = (
        "Breakout buying is psychologically hard (buying 'expensive'); "
        "institutional execution constraints leave the follow-through "
        "unexploited at daily/4h horizons."
    )
    risks = "False breakouts in ranges; slippage at the breakout moment is structurally worse."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        entry_n, exit_n = int(p["entry"]), int(p["exit"])
        hi_entry = df["high"].rolling(entry_n).max().shift(1)
        lo_entry = df["low"].rolling(entry_n).min().shift(1)
        hi_exit = df["high"].rolling(exit_n).max().shift(1)
        lo_exit = df["low"].rolling(exit_n).min().shift(1)

        enter_long = df["close"] > hi_entry
        exit_long = df["close"] < lo_exit
        if p.get("allow_short", True):
            enter_short = df["close"] < lo_entry
            exit_short = df["close"] > hi_exit
        else:
            enter_short = exit_short = None
        return hysteresis_positions(enter_long, exit_long, enter_short, exit_short)


@register_signal
class ChannelBreakoutVolumeSignal(ResearchSignal):
    name = "breakout_volume"
    family = "trend"
    default_params = {"window": 40, "vol_z": 1.0, "hold": 30}
    grid = {"window": [20, 40, 80], "vol_z": [0.5, 1.0, 1.5]}
    thesis = (
        "A breakout accompanied by abnormal volume distinguishes real "
        "initiative flow from a quiet drift through the level — volume is the "
        "commitment behind the move."
    )
    persistence = "Volume confirmation filters the crowd-visible false-break trade."
    risks = "Volume data quality varies by venue; wash trading can fake confirmation."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        w, hold = int(p["window"]), int(p["hold"])
        hi = df["high"].rolling(w).max().shift(1)
        lo = df["low"].rolling(w).min().shift(1)
        vz = volume_zscore(df["volume"], 50)
        confirmed = vz > float(p["vol_z"])
        up = (df["close"] > hi) & confirmed
        dn = (df["close"] < lo) & confirmed
        raw = pd.Series(0.0, index=df.index)
        raw[up] = 1.0
        raw[dn] = -1.0
        # Hold the position for `hold` bars after the trigger (or until the
        # opposite trigger), then flat.
        pos = raw.replace(0.0, np.nan).ffill(limit=hold).fillna(0.0)
        return pos


@register_signal
class TrendAccelerationSignal(ResearchSignal):
    name = "trend_acceleration"
    family = "trend"
    default_params = {"span": 50, "accel_window": 10, "er_window": 20, "er_min": 0.30}
    grid = {"span": [30, 50, 100], "er_min": [0.2, 0.3, 0.4]}
    thesis = (
        "Position only when the trend is both pointing and *steepening* and "
        "price is moving efficiently (high Kaufman ER): acceleration phases "
        "carry the bulk of trend P&L."
    )
    persistence = "Second-derivative conditioning is rarely used by slow trend money."
    risks = "Acceleration is late by construction; blow-off tops punish it."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        e = ind.ema(df["close"], int(p["span"]))
        slope = e.diff(int(p["accel_window"]))
        accel = slope.diff(int(p["accel_window"]))
        er = efficiency_ratio(df["close"], int(p["er_window"]))
        long_ = (slope > 0) & (accel > 0) & (er > float(p["er_min"]))
        short = (slope < 0) & (accel < 0) & (er > float(p["er_min"]))
        pos = pd.Series(0.0, index=df.index)
        pos[long_] = 1.0
        pos[short] = -1.0
        return pos


@register_signal
class MultiTimeframeTrendSignal(ResearchSignal):
    name = "mtf_trend"
    family = "trend"
    default_params = {"htf_rule": "1D", "htf_fast": 10, "htf_slow": 30, "ltf_fast": 20, "ltf_slow": 50}
    grid = {"htf_slow": [20, 30, 50], "ltf_fast": [10, 20, 30]}
    thesis = (
        "Trade lower-timeframe trend resumption only in the direction of the "
        "higher-timeframe trend: the HTF filter removes the counter-trend "
        "half of whipsaws."
    )
    persistence = "Multi-horizon agreement proxies for alignment of slow and fast capital."
    risks = "HTF turns are caught late; doubles the parameter surface."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        htf_dir = multi_timeframe_feature(
            df,
            str(p["htf_rule"]),
            lambda h: np.sign(
                ind.ema(h["close"], int(p["htf_fast"])) - ind.ema(h["close"], int(p["htf_slow"]))
            ),
        ).fillna(0.0)
        ltf_up = ind.ema(df["close"], int(p["ltf_fast"])) > ind.ema(df["close"], int(p["ltf_slow"]))
        pos = pd.Series(0.0, index=df.index)
        pos[(htf_dir > 0) & ltf_up] = 1.0
        pos[(htf_dir < 0) & (~ltf_up)] = -1.0
        return pos
