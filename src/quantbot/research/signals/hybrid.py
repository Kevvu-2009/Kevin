"""Hybrid signal family: combinations of weak edges.

Rationale: independent weak signals with positive expectancy combine into a
stronger one (diversification of alpha, not just of assets).  The validation
question for every hybrid is whether it beats its best component on
*robustness*, not just on return — otherwise the combination is complexity
without compensation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.research.signals.base import ResearchSignal, register_signal
from quantbot.research.signals.mean_reversion import BollingerReversionSignal
from quantbot.research.signals.momentum import TimeSeriesMomentumSignal
from quantbot.research.signals.trend import DonchianBreakoutSignal, EMACrossSignal
from quantbot.research.signals.volatility import VolContractionBreakoutSignal


@register_signal
class EnsembleVoteSignal(ResearchSignal):
    name = "ensemble_vote"
    family = "hybrid"
    default_params = {"min_agree": 0.5}
    grid = {"min_agree": [0.34, 0.5, 0.75]}
    thesis = (
        "Equal-weight vote of four structurally different directional "
        "signals (EMA trend, Donchian breakout, TSMOM, squeeze breakout).  "
        "Positions scale with agreement; disagreement nets to flat.  Errors "
        "of the components are imperfectly correlated, so the vote's Sharpe "
        "exceeds the average component's."
    )
    persistence = "As durable as the weakest surviving component; rebalanced by construction."
    risks = (
        "Components share trend exposure, so diversification is partial; "
        "all four can be wrong together at violent reversals."
    )

    def _components(self) -> list[ResearchSignal]:
        return [
            EMACrossSignal(),
            DonchianBreakoutSignal(),
            TimeSeriesMomentumSignal(),
            VolContractionBreakoutSignal(),
        ]

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        votes = [c.generate(df) for c in self._components()]
        avg = pd.concat(votes, axis=1).mean(axis=1)
        min_agree = float(self.params["min_agree"])
        pos = avg.where(avg.abs() >= min_agree, 0.0)
        return pos.clip(-1.0, 1.0).fillna(0.0)


@register_signal
class TrendPlusPullbackSignal(ResearchSignal):
    name = "trend_pullback"
    family = "hybrid"
    default_params = {"fast": 50, "slow": 200, "bb_window": 20, "n_std": 1.5, "hold": 48}
    grid = {"n_std": [1.0, 1.5, 2.0], "hold": [24, 48, 96]}
    thesis = (
        "Trend filter chooses the side; mean-reversion chooses the moment: "
        "buy pullbacks to the lower band INSIDE an uptrend (and mirror in "
        "downtrends).  Combines momentum's edge in direction with "
        "reversion's edge in entry price."
    )
    persistence = "Pullback entries are capacity-friendly and behaviourally hard (buying dips in fear)."
    risks = "Deep pullbacks that keep going are trend *changes*; the filter is always late."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        from quantbot.strategies import indicators as ind

        ema_f = ind.ema(df["close"], int(p["fast"]))
        ema_s = ind.ema(df["close"], int(p["slow"]))
        mid, upper, lower = ind.bollinger_bands(df["close"], int(p["bb_window"]), float(p["n_std"]))
        upper, lower = upper.shift(1), lower.shift(1)

        uptrend = ema_f > ema_s
        long_entry = uptrend & (df["close"] < lower)
        short_entry = (~uptrend) & (df["close"] > upper)
        raw = pd.Series(0.0, index=df.index)
        raw[long_entry] = 1.0
        raw[short_entry] = -1.0
        return raw.replace(0.0, np.nan).ffill(limit=int(p["hold"])).fillna(0.0)


@register_signal
class WeightedCompositeSignal(ResearchSignal):
    name = "weighted_composite"
    family = "hybrid"
    default_params = {"w_trend": 0.4, "w_mom": 0.4, "w_rev": 0.2}
    grid = {"w_rev": [0.0, 0.2, 0.4]}
    thesis = (
        "Continuous blend (not a vote): trend + momentum + a contrarian "
        "sleeve whose weight is the diversifier.  The reversion sleeve "
        "earns little alone but pays at exactly the moments trend bleeds."
    )
    persistence = "Risk-premia blending — the standard multi-strategy argument."
    risks = "Static weights are themselves a fitted choice; drift unmonitored."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        trend = EMACrossSignal().generate(df)
        mom = TimeSeriesMomentumSignal().generate(df)
        rev = BollingerReversionSignal().generate(df)
        w = np.array([float(p["w_trend"]), float(p["w_mom"]), float(p["w_rev"])])
        if w.sum() <= 0:
            return pd.Series(0.0, index=df.index)
        w = w / w.sum()
        blend = w[0] * trend + w[1] * mom + w[2] * rev
        return blend.clip(-1.0, 1.0).fillna(0.0)
