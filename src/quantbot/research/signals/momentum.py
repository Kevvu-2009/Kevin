"""Momentum signal family.

Distinct from trend following: momentum measures *realised past return* over a
fixed lookback (anchored), trend following tracks a *state* (filter).  The
time-series momentum premium is documented across every major asset class
(Moskowitz, Ooi & Pedersen 2012); cross-sectional momentum dates to Jegadeesh
& Titman (1993).  Crypto's retail flow chases performance, feeding both.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.features.core import momentum, realized_vol, volume_momentum
from quantbot.research.signals.base import PanelSignal, ResearchSignal, register_signal


@register_signal
class TimeSeriesMomentumSignal(ResearchSignal):
    name = "tsmom"
    family = "momentum"
    default_params = {"lookback": 168, "vol_scale": True, "vol_window": 50, "target_vol": 0.01}
    grid = {"lookback": [72, 168, 336, 720]}
    thesis = (
        "Sign of the trailing L-bar return predicts the next period's return "
        "(positive return autocorrelation at weekly-monthly horizons) — the "
        "classic TSMOM premium, driven by under-reaction then herding."
    )
    persistence = (
        "Documented for a century across assets and still priced: the "
        "counterparty is systematic rebalancing and anchored disposition-"
        "effect sellers, who are not going away."
    )
    risks = "Momentum crashes: sharp reversals after extended runs; dead zones in ranges."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        look = int(p["lookback"])
        sign = np.sign(momentum(df["close"], look))
        if p.get("vol_scale", True):
            rv = realized_vol(df["close"], int(p["vol_window"]))
            scale = (float(p["target_vol"]) / rv).clip(upper=1.0)
            pos = (sign * scale).fillna(0.0)
        else:
            pos = sign.fillna(0.0)
        pos.iloc[:look] = 0.0
        return pos


@register_signal
class RelativeStrengthSignal(ResearchSignal):
    name = "relative_strength"
    family = "momentum"
    default_params = {"lookback": 168, "rank_window": 500, "upper_q": 0.85, "lower_q": 0.15}
    grid = {"lookback": [72, 168, 336], "upper_q": [0.8, 0.9]}
    thesis = (
        "Trade only momentum that is extreme *relative to the asset's own "
        "history* (rolling-rank): conditioning on abnormality removes the "
        "weak-momentum noise band."
    )
    persistence = "Extremeness filters retain the under-reaction core of momentum."
    risks = "Extreme momentum overlaps with bubble tops; rank windows lag regime change."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        mom = momentum(df["close"], int(p["lookback"]))
        rank = mom.rolling(int(p["rank_window"])).rank(pct=True)
        pos = pd.Series(0.0, index=df.index)
        pos[rank > float(p["upper_q"])] = 1.0
        pos[rank < float(p["lower_q"])] = -1.0
        return pos


@register_signal
class VolumeMomentumSignal(ResearchSignal):
    name = "volume_momentum"
    family = "momentum"
    default_params = {"lookback": 96, "vol_fast": 10, "vol_slow": 50}
    grid = {"lookback": [48, 96, 168]}
    thesis = (
        "Price momentum on expanding volume is initiative flow; on fading "
        "volume it is exhaustion.  Gate TSMOM by volume expansion."
    )
    persistence = "Joint price-volume conditioning is harder to crowd than price alone."
    risks = "Exchange-reported volume is manipulable; signal inherits momentum crashes."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        sign = np.sign(momentum(df["close"], int(p["lookback"])))
        vol_up = volume_momentum(df["volume"], int(p["vol_fast"]), int(p["vol_slow"])) > 0
        return (sign * vol_up.astype(float)).fillna(0.0)


@register_signal
class MomentumPersistenceSignal(ResearchSignal):
    name = "momentum_persistence"
    family = "momentum"
    default_params = {"window": 20, "threshold": 0.65}
    grid = {"window": [10, 20, 40], "threshold": [0.6, 0.65, 0.7]}
    thesis = (
        "The *fraction of up bars* (not the size of moves) measures the "
        "one-sidedness of flow; persistent one-sided tape continues — a "
        "streak/herding effect distinct from return-size momentum."
    )
    persistence = "Count-based statistics are robust to vol regime and rarely traded directly."
    risks = "Grinding tops show maximal persistence right before reversal."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        w, th = int(p["window"]), float(p["threshold"])
        up_frac = (df["close"].diff() > 0).rolling(w).mean()
        pos = pd.Series(0.0, index=df.index)
        pos[up_frac > th] = 1.0
        pos[up_frac < 1.0 - th] = -1.0
        return pos


@register_signal
class CrossSectionalMomentumSignal(PanelSignal):
    name = "xsec_momentum"
    family = "momentum"
    default_params = {"lookback": 168, "rebalance": 24, "top_k": 2}
    grid = {"lookback": [72, 168, 336], "top_k": [1, 2]}
    thesis = (
        "Long the recent winners, short the recent losers within the universe: "
        "relative momentum cancels the common market factor and isolates "
        "asset-specific flow persistence (Jegadeesh-Titman applied to crypto)."
    )
    persistence = (
        "Market-neutral construction means the edge lives in relative under-"
        "reaction, which retail crypto flow (chasing single names serially) "
        "regenerates continuously."
    )
    risks = (
        "Universe too small → idiosyncratic blowups dominate; shorts on alts "
        "carry squeeze risk; borrow/funding costs not modelled."
    )

    def generate_panel(self, panel: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        p = self.params
        look, reb, k = int(p["lookback"]), int(p["rebalance"]), int(p["top_k"])
        symbols = sorted(panel)
        if len(symbols) < max(3, 2 * k):
            return {s: pd.Series(0.0, index=panel[s].index) for s in symbols}

        closes = pd.DataFrame({s: panel[s]["close"] for s in symbols}).sort_index()
        mom = closes / closes.shift(look) - 1.0
        # Decide weights only every `rebalance` bars; hold in between.
        decide = pd.Series(False, index=closes.index)
        decide.iloc[look::reb] = True

        ranks = mom.rank(axis=1, ascending=False)
        n_valid = mom.notna().sum(axis=1)
        # Mask non-rebalance rows to NaN (broadcast row-wise), then carry the
        # last decision forward.
        decide_arr = np.broadcast_to(decide.to_numpy()[:, None], ranks.shape)
        long_w = (
            ranks.le(k).astype(float).where(decide_arr, np.nan).ffill().fillna(0.0)
        )
        short_w = (
            ranks.gt(n_valid - k, axis=0).astype(float).where(decide_arr, np.nan).ffill().fillna(0.0)
        )
        weights = (long_w - short_w).clip(-1.0, 1.0)
        weights[mom.isna()] = 0.0

        return {s: weights[s].reindex(panel[s].index).fillna(0.0) for s in symbols}
