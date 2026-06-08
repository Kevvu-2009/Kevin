"""Strategy 1 — Trend Following (EMA crossover + ATR stop).

Thesis: crypto majors exhibit strong, persistent trends and fat-tailed upside.
A slow/fast EMA stack keeps us aligned with the dominant regime; the ATR stop
caps the loss when the trend breaks.  Long-only (no shorting the structurally
upward-drifting majors), which also keeps fees and borrow costs out of scope.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.strategies import indicators as ind
from quantbot.strategies.base import Strategy, StrategyResult
from quantbot.strategies.registry import register


@register("trend_following")
class TrendFollowing(Strategy):
    default_params = {
        "ema_fast": 50,
        "ema_slow": 200,
        "atr_period": 14,
        "atr_mult": 3.0,
    }
    param_space = {
        "ema_fast": ("int", 20, 80),
        "ema_slow": ("int", 120, 300),
        "atr_period": ("int", 10, 21),
        "atr_mult": ("float", 2.0, 5.0),
    }

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        self._validate(df)
        p = self.params
        close = df["close"]

        ema_f = ind.ema(close, int(p["ema_fast"]))
        ema_s = ind.ema(close, int(p["ema_slow"]))
        atr = ind.atr(df["high"], df["low"], close, int(p["atr_period"]))

        uptrend = ema_f > ema_s
        # Entry on the bar the fast EMA crosses above the slow EMA.
        entries = uptrend & (~uptrend.shift(1).fillna(False))
        # Reversal exit when trend flips back down.
        exits = (~uptrend) & uptrend.shift(1).fillna(False)

        # Chandelier-style ATR stop trailing the highest close since entry is
        # approximated bar-by-bar as close - mult*ATR; the backtester ratchets
        # it upward (never down) once in a position.
        stop = close - float(p["atr_mult"]) * atr
        stop = stop.where(uptrend, np.nan)

        return StrategyResult(
            entries=entries.fillna(False),
            exits=exits.fillna(False),
            stop=stop,
            meta={"regime": "trend"},
        )
