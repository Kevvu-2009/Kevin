"""Regime-conditioned signal family.

The single most reliable finding in systematic trading research: the same
signal has opposite expectancy in different regimes (momentum works trending,
reversion works ranging).  These candidates make the conditioning explicit so
validation can measure whether the *gate itself* adds value over the raw
signal — each gated signal's natural baseline is its ungated sibling.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.research.regimes import detect_regimes
from quantbot.research.signals.base import ResearchSignal, register_signal
from quantbot.research.signals.mean_reversion import ZScoreReversionSignal
from quantbot.research.signals.momentum import TimeSeriesMomentumSignal


@register_signal
class RegimeGatedTrendSignal(ResearchSignal):
    name = "regime_gated_trend"
    family = "regime"
    default_params = {"lookback": 168, "adx_th": 20.0}
    grid = {"lookback": [72, 168, 336], "adx_th": [15.0, 20.0, 25.0]}
    thesis = (
        "TSMOM only while the trend regime is on (EMA stack + ADX): removes "
        "the chop bars where momentum bleeds, keeping the trend bars where "
        "it earns."
    )
    persistence = "Inherits TSMOM's premium; the gate only subtracts known-bad states."
    risks = "Gate lag at regime turns; two layers of parameters."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        regimes = detect_regimes(df, adx_th=float(p["adx_th"]))
        base = TimeSeriesMomentumSignal(lookback=int(p["lookback"])).generate(df)
        gated = base.where(regimes["trend"] != 0, 0.0)
        return gated


@register_signal
class RegimeGatedReversionSignal(ResearchSignal):
    name = "regime_gated_reversion"
    family = "regime"
    default_params = {"window": 50, "entry_z": 2.0, "adx_th": 20.0}
    grid = {"window": [30, 50], "entry_z": [1.5, 2.0, 2.5]}
    thesis = (
        "Z-score reversion only while the market is RANGING (trend gate off): "
        "removes the trending bars where fading is catching knives."
    )
    persistence = "Liquidity-provision premium concentrated in its natural habitat."
    risks = "Ranges end without notice; the last fade of a range is the breakout."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        regimes = detect_regimes(df, adx_th=float(p["adx_th"]))
        base = ZScoreReversionSignal(
            window=int(p["window"]), entry_z=float(p["entry_z"])
        ).generate(df)
        return base.where(regimes["trend"] == 0, 0.0)


@register_signal
class RegimeSwitchSignal(ResearchSignal):
    name = "regime_switch"
    family = "regime"
    default_params = {"lookback": 168, "window": 50, "entry_z": 2.0, "adx_th": 20.0}
    grid = {"lookback": [72, 168], "entry_z": [1.5, 2.0]}
    thesis = (
        "The adaptive composite: momentum in trending regimes, reversion in "
        "ranging regimes.  If both component edges are real, switching "
        "captures both habitats with the same capital."
    )
    persistence = "Combination of two structurally distinct premia."
    risks = (
        "Whipsaw at regime boundaries can be worse than either component; "
        "complexity costs degrees of freedom."
    )

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        regimes = detect_regimes(df, adx_th=float(p["adx_th"]))
        mom = TimeSeriesMomentumSignal(lookback=int(p["lookback"])).generate(df)
        rev = ZScoreReversionSignal(window=int(p["window"]), entry_z=float(p["entry_z"])).generate(df)
        trending = regimes["trend"] != 0
        return mom.where(trending, rev).fillna(0.0)
