"""Volatility signal family.

Volatility is the most forecastable moment of returns (clustering,
mean-reversion of vol itself).  These signals trade *price* conditioned on
the volatility state rather than trading vol directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.features.core import realized_vol
from quantbot.research.signals.base import ResearchSignal, register_signal
from quantbot.strategies import indicators as ind


@register_signal
class ATRBreakoutSignal(ResearchSignal):
    name = "atr_breakout"
    family = "volatility"
    default_params = {"atr_period": 14, "mult": 1.5, "hold": 24}
    grid = {"mult": [1.0, 1.5, 2.0], "hold": [12, 24, 48]}
    thesis = (
        "A single bar travelling > k×ATR is an information/flow shock; "
        "shocks propagate (drift continuation) for hours afterwards as the "
        "market digests the new information."
    )
    persistence = "Post-shock drift is documented across markets (slow information diffusion)."
    risks = "Entering after a large bar means structurally bad fills; shocks can reverse on flush."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        atr = ind.atr(df["high"], df["low"], df["close"], int(p["atr_period"])).shift(1)
        move = df["close"].diff()
        up = move > float(p["mult"]) * atr
        dn = move < -float(p["mult"]) * atr
        raw = pd.Series(0.0, index=df.index)
        raw[up] = 1.0
        raw[dn] = -1.0
        return raw.replace(0.0, np.nan).ffill(limit=int(p["hold"])).fillna(0.0)


@register_signal
class VolExpansionSignal(ResearchSignal):
    name = "vol_expansion"
    family = "volatility"
    default_params = {"fast": 10, "slow": 100, "ratio": 1.5, "dir_lookback": 24}
    grid = {"ratio": [1.25, 1.5, 2.0], "dir_lookback": [12, 24, 48]}
    thesis = (
        "When short-horizon vol expands well above its baseline, a new "
        "directional phase is usually starting; ride it in the direction of "
        "the move that triggered the expansion."
    )
    persistence = "Vol clustering (ARCH effects) is among the strongest stylised facts in finance."
    risks = "Expansion at trend exhaustion points the wrong way; costs spike exactly then."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        rv_fast = realized_vol(df["close"], int(p["fast"]))
        rv_slow = realized_vol(df["close"], int(p["slow"]))
        expanding = rv_fast / rv_slow.replace(0.0, np.nan) > float(p["ratio"])
        direction = np.sign(df["close"].pct_change(int(p["dir_lookback"])))
        return (direction * expanding.astype(float)).fillna(0.0)


@register_signal
class VolContractionBreakoutSignal(ResearchSignal):
    name = "squeeze_breakout"
    family = "volatility"
    default_params = {"bb_window": 20, "squeeze_q": 0.15, "rank_window": 200, "channel": 20, "hold": 48}
    grid = {"squeeze_q": [0.10, 0.15, 0.25], "channel": [10, 20, 40]}
    thesis = (
        "Volatility compression (tight Bollinger bandwidth vs its own "
        "history) precedes expansion: positioning is balanced, so the first "
        "range break travels far (the 'squeeze' setup)."
    )
    persistence = "Vol mean-reversion is structural; compressed ranges must resolve."
    risks = "Direction of the resolution is the hard part — first break can be the false one."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        mid, upper, lower = ind.bollinger_bands(df["close"], int(p["bb_window"]), 2.0)
        bandwidth = (upper - lower) / mid
        squeezed = bandwidth.rolling(int(p["rank_window"])).rank(pct=True) < float(p["squeeze_q"])
        # Break of the recent channel while (or just after) squeezed.
        ch = int(p["channel"])
        hi = df["high"].rolling(ch).max().shift(1)
        lo = df["low"].rolling(ch).min().shift(1)
        armed = squeezed.shift(1).rolling(5).max().fillna(0.0).astype(bool)  # squeeze in last 5 bars
        up = (df["close"] > hi) & armed
        dn = (df["close"] < lo) & armed
        raw = pd.Series(0.0, index=df.index)
        raw[up] = 1.0
        raw[dn] = -1.0
        return raw.replace(0.0, np.nan).ffill(limit=int(p["hold"])).fillna(0.0)


@register_signal
class VolRegimeMomentumSignal(ResearchSignal):
    name = "vol_regime_momentum"
    family = "volatility"
    default_params = {"lookback": 168, "vol_window": 20, "ref_window": 200, "trade_in": "low"}
    grid = {"lookback": [72, 168, 336], "trade_in": ["low", "high"]}
    thesis = (
        "Momentum quality is regime-dependent: in low-vol regimes trends "
        "grind persistently; in high-vol regimes whipsaw dominates.  Trade "
        "TSMOM only in the favourable vol state."
    )
    persistence = "Conditioning on vol state is a capacity-unconstrained filter."
    risks = "Regime boundaries are lagged estimates; flips cluster at the worst times."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        rv = realized_vol(df["close"], int(p["vol_window"]))
        med = rv.rolling(int(p["ref_window"])).median()
        high_vol = rv > med
        wanted = high_vol if p["trade_in"] == "high" else ~high_vol
        sign = np.sign(df["close"].pct_change(int(p["lookback"])))
        return (sign * wanted.astype(float)).fillna(0.0)
