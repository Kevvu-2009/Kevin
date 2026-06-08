"""Strategy 3 — Mean Reversion (RSI + Bollinger Bands).

Thesis: inside a range / low-trend regime, crypto overshoots and snaps back.
We buy capitulation (RSI oversold AND price below the lower Bollinger band) and
take profit on a reversion to the band middle (or exit on RSI overbought).  A
hard ATR stop protects against a range that turns into a downtrend.
"""

from __future__ import annotations

import pandas as pd

from quantbot.strategies import indicators as ind
from quantbot.strategies.base import Strategy, StrategyResult
from quantbot.strategies.registry import register


@register("mean_reversion")
class MeanReversion(Strategy):
    default_params = {
        "rsi_period": 14,
        "rsi_buy": 30.0,
        "rsi_sell": 55.0,
        "bb_period": 20,
        "bb_std": 2.0,
        "atr_period": 14,
        "atr_mult": 2.5,
    }
    param_space = {
        "rsi_period": ("int", 7, 21),
        "rsi_buy": ("float", 20.0, 35.0),
        "rsi_sell": ("float", 50.0, 70.0),
        "bb_period": ("int", 14, 30),
        "bb_std": ("float", 1.5, 3.0),
        "atr_mult": ("float", 2.0, 4.0),
    }

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        self._validate(df)
        p = self.params
        close = df["close"]

        rsi = ind.rsi(close, int(p["rsi_period"]))
        lower, mid, _ = ind.bollinger_bands(close, int(p["bb_period"]), float(p["bb_std"]))
        atr = ind.atr(df["high"], df["low"], close, int(p["atr_period"]))

        entries = (rsi < float(p["rsi_buy"])) & (close < lower)
        # Exit on reversion to the mean OR momentum reasserting (RSI back up).
        exits = (close >= mid) | (rsi > float(p["rsi_sell"]))

        stop = close - float(p["atr_mult"]) * atr

        return StrategyResult(
            entries=entries.fillna(False),
            exits=exits.fillna(False),
            stop=stop,
            meta={"regime": "range"},
        )
