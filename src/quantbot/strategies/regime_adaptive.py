"""Strategy 4 — Market-Regime Adaptive.

Switches between a trend strategy and a mean-reversion strategy based on a
regime classifier built from trend strength (ADX) and volatility state.

Regime rule (evaluated per bar, no look-ahead):
    * TREND   when ADX >= adx_trend  → delegate to TrendFollowing signals
    * RANGE   when ADX <  adx_trend  → delegate to MeanReversion signals
A volatility ceiling (annualised realized vol) globally suppresses new entries
when the market is too chaotic to size safely.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.strategies import indicators as ind
from quantbot.strategies.base import Strategy, StrategyResult
from quantbot.strategies.mean_reversion import MeanReversion
from quantbot.strategies.registry import register
from quantbot.strategies.trend_following import TrendFollowing


@register("regime_adaptive")
class RegimeAdaptive(Strategy):
    default_params = {
        "adx_period": 14,
        "adx_trend": 25.0,
        "vol_window": 20,
        "vol_ceiling": 2.5,   # suppress entries above 250% annualised vol
        # sub-strategy params (prefixed)
        "trend_ema_fast": 50,
        "trend_ema_slow": 200,
        "trend_atr_mult": 3.0,
        "mr_rsi_buy": 30.0,
        "mr_bb_std": 2.0,
        "mr_atr_mult": 2.5,
    }
    param_space = {
        "adx_trend": ("float", 18.0, 32.0),
        "vol_ceiling": ("float", 1.5, 4.0),
        "trend_ema_fast": ("int", 20, 80),
        "trend_atr_mult": ("float", 2.0, 5.0),
        "mr_rsi_buy": ("float", 20.0, 35.0),
        "mr_atr_mult": ("float", 2.0, 4.0),
    }

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        self._validate(df)
        p = self.params

        trend = TrendFollowing(
            ema_fast=int(p["trend_ema_fast"]),
            ema_slow=int(p["trend_ema_slow"]),
            atr_mult=float(p["trend_atr_mult"]),
        ).generate(df)
        mr = MeanReversion(
            rsi_buy=float(p["mr_rsi_buy"]),
            bb_std=float(p["mr_bb_std"]),
            atr_mult=float(p["mr_atr_mult"]),
        ).generate(df)

        adx = ind.adx(df["high"], df["low"], df["close"], int(p["adx_period"]))
        rvol = ind.realized_volatility(df["close"], int(p["vol_window"]))

        is_trend = adx >= float(p["adx_trend"])
        vol_ok = (rvol <= float(p["vol_ceiling"])) | rvol.isna()

        # Pick entries from the active regime only; suppress in chaotic vol.
        entries = np.where(is_trend, trend.entries, mr.entries) & vol_ok.to_numpy()
        entries = pd.Series(entries, index=df.index).fillna(False)

        # Exit if either the active regime says exit OR the regime itself flips.
        regime_flip = is_trend != is_trend.shift(1).fillna(is_trend.iloc[0] if len(is_trend) else False)
        exits = np.where(is_trend, trend.exits, mr.exits)
        exits = pd.Series(exits, index=df.index).fillna(False) | regime_flip

        # Use the active regime's stop level.
        stop = trend.stop.where(is_trend, mr.stop)

        return StrategyResult(
            entries=entries,
            exits=exits,
            stop=stop,
            meta={"regime": "adaptive"},
        )
