"""Strategy 5 — Breakout with fixed Reward:Risk (R:R).

Thesis: in a market that drifts upward and trends in bursts, *frequent* short-
lookback breakouts have a modest hit-rate but, paired with a tight stop and a
target several times that distance, carry positive expectancy.  With a 3:1
reward:risk you only need to be right ~25% of the time to break even; anything
above that compounds.

Mechanics (long-only, no look-ahead):
    * Entry  — close breaks above the prior bar's ``entry_lookback``-bar high
               (Donchian upper), *and* price is above a slow EMA trend filter
               (don't buy breakouts inside a downtrend).
    * Stop   — fixed at ``entry - atr_mult * ATR`` (does NOT trail; ``trail`` is
               False so the R:R ratio is preserved).
    * Target — fixed at ``entry + rr * atr_mult * ATR`` → exactly ``rr`` : 1.
There is no discretionary exit signal: a trade ends at the stop, the target, or
the end of data.  Frequency is governed by ``entry_lookback`` (shorter = more
trades, more noise, more cost drag).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.strategies import indicators as ind
from quantbot.strategies.base import Strategy, StrategyResult
from quantbot.strategies.registry import register


@register("breakout_rr")
class BreakoutRR(Strategy):
    default_params = {
        "entry_lookback": 20,    # Donchian breakout window (bars)
        "trend_ema": 100,        # long-only trend filter
        "atr_period": 14,
        "atr_mult": 1.5,         # stop distance in ATRs (tight)
        "rr": 3.0,               # target = rr * stop distance  → reward:risk
    }
    param_space = {
        "entry_lookback": ("int", 10, 55),
        "trend_ema": ("int", 50, 200),
        "atr_mult": ("float", 1.0, 3.0),
        "rr": ("float", 3.0, 5.0),   # honour the "above 3:1" intent
    }

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        self._validate(df)
        p = self.params
        close = df["close"]

        _, _, upper = ind.donchian_channels(
            df["high"], df["low"], int(p["entry_lookback"])
        )
        atr = ind.atr(df["high"], df["low"], close, int(p["atr_period"]))
        trend = ind.ema(close, int(p["trend_ema"]))

        # Breakout above the *prior* bar's channel (no look-ahead), filtered to
        # uptrends only.
        broke_out = close > upper.shift(1)
        entries = (broke_out & (close > trend)).fillna(False)

        risk = float(p["atr_mult"]) * atr
        stop = close - risk
        take_profit = close + float(p["rr"]) * risk

        # No signal exit; stop & target (and EOD) close the trade.
        exits = pd.Series(False, index=df.index)

        return StrategyResult(
            entries=entries,
            exits=exits,
            stop=stop,
            take_profit=take_profit,
            trail=False,          # fixed stop → clean R:R
            meta={"regime": "breakout", "rr": float(p["rr"])},
        )
