"""Strategy 2 — Momentum Breakout (Donchian + ATR trailing + volume filter).

Thesis: liquid crypto breaks out of consolidation ranges with follow-through,
especially when accompanied by a volume expansion (real participation rather
than a thin-book wick).  We buy a close above the prior N-bar high and ride it
with an ATR trailing stop.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.strategies import indicators as ind
from quantbot.strategies.base import Strategy, StrategyResult
from quantbot.strategies.registry import register


@register("momentum_breakout")
class MomentumBreakout(Strategy):
    default_params = {
        "channel": 20,
        "exit_channel": 10,
        "atr_period": 14,
        "atr_mult": 3.0,
        "vol_window": 20,
        "vol_mult": 1.2,
    }
    param_space = {
        "channel": ("int", 10, 55),
        "exit_channel": ("int", 5, 20),
        "atr_period": ("int", 10, 21),
        "atr_mult": ("float", 2.0, 5.0),
        "vol_mult": ("float", 1.0, 2.0),
    }

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        self._validate(df)
        p = self.params
        high, low, close, vol = df["high"], df["low"], df["close"], df["volume"]

        # Use the *prior* bar's channel to avoid the breakout bar contaminating
        # its own reference high (look-ahead guard).
        _, _, up = ind.donchian_channels(high, low, int(p["channel"]))
        breakout_level = up.shift(1)
        dn_exit, _, _ = ind.donchian_channels(high, low, int(p["exit_channel"]))
        exit_level = dn_exit.shift(1)

        atr = ind.atr(high, low, close, int(p["atr_period"]))
        vol_ma = vol.rolling(int(p["vol_window"]), min_periods=int(p["vol_window"])).mean()
        vol_ok = vol > (float(p["vol_mult"]) * vol_ma)

        entries = (close > breakout_level) & vol_ok
        # Exit when price closes back below the shorter Donchian floor.
        exits = close < exit_level

        stop = close - float(p["atr_mult"]) * atr

        return StrategyResult(
            entries=entries.fillna(False),
            exits=exits.fillna(False),
            stop=stop,
            meta={"regime": "trend"},
        )
