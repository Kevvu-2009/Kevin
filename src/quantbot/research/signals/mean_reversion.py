"""Mean-reversion signal family.

Shared thesis: at intraday-to-daily horizons, liquidity demand (liquidations,
stop cascades, large market orders) pushes price away from fair value faster
than informed capital replenishes the book; the snap-back compensates
liquidity providers.  This is the inverse regime of momentum — it lives at
shorter horizons and in range-bound tape.

Shared risks: "catching the knife" — what looks like an overshoot is
sometimes the first leg of a regime change; MR strategies have short, fat
left tails and need hard stops or regime gates.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.features.core import realized_vol, zscore
from quantbot.research.signals.base import ResearchSignal, hysteresis_positions, register_signal
from quantbot.strategies import indicators as ind


@register_signal
class RSIReversionSignal(ResearchSignal):
    name = "rsi_reversion"
    family = "mean_reversion"
    default_params = {"period": 14, "lower": 30.0, "upper": 70.0, "exit_band": 50.0}
    grid = {"period": [7, 14, 21], "lower": [20.0, 30.0], "upper": [70.0, 80.0]}
    thesis = (
        "Deep RSI oversold/overbought marks one-sided flow exhaustion; "
        "fading it monetises the bounce as the marginal forced seller/buyer "
        "disappears."
    )
    persistence = "Forced flow (liquidations, stops) recurs structurally in leveraged crypto."
    risks = "Oversold keeps getting more oversold in crashes — stops or regime gates required."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        rsi = ind.rsi(df["close"], int(p["period"]))
        mid = float(p["exit_band"])
        return hysteresis_positions(
            enter_long=rsi < float(p["lower"]),
            exit_long=rsi > mid,
            enter_short=rsi > float(p["upper"]),
            exit_short=rsi < mid,
        )


@register_signal
class BollingerReversionSignal(ResearchSignal):
    name = "bollinger_reversion"
    family = "mean_reversion"
    default_params = {"window": 20, "n_std": 2.0}
    grid = {"window": [20, 40], "n_std": [2.0, 2.5, 3.0]}
    thesis = (
        "Closes outside ±kσ bands are statistically stretched relative to "
        "local volatility; reversion to the mean band monetises the stretch."
    )
    persistence = "Vol-scaled bands adapt to regime, so the trigger stays meaningfully rare."
    risks = "Band walks during strong trends produce serial losses."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        mid, upper, lower = ind.bollinger_bands(df["close"], int(p["window"]), float(p["n_std"]))
        # Prior-bar bands: the band must exist before the close pierces it.
        upper, lower, mid = upper.shift(1), lower.shift(1), mid.shift(1)
        return hysteresis_positions(
            enter_long=df["close"] < lower,
            exit_long=df["close"] > mid,
            enter_short=df["close"] > upper,
            exit_short=df["close"] < mid,
        )


@register_signal
class ZScoreReversionSignal(ResearchSignal):
    name = "zscore_reversion"
    family = "mean_reversion"
    default_params = {"window": 50, "entry_z": 2.0, "exit_z": 0.5}
    grid = {"window": [30, 50, 100], "entry_z": [1.5, 2.0, 2.5]}
    thesis = (
        "Plain statistical reversion: fade |z| > entry of price vs its rolling "
        "mean, cover near zero.  The cleanest expression of the liquidity-"
        "provision premium."
    )
    persistence = "Liquidity shocks recur; the premium is payment for inventory risk."
    risks = "Non-stationary drift makes the rolling mean itself trend away."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        z = zscore(df["close"], int(p["window"]))
        e, x = float(p["entry_z"]), float(p["exit_z"])
        return hysteresis_positions(
            enter_long=z < -e,
            exit_long=z > -x,
            enter_short=z > e,
            exit_short=z < x,
        )


@register_signal
class VolExhaustionSignal(ResearchSignal):
    name = "vol_exhaustion"
    family = "mean_reversion"
    default_params = {"move_window": 12, "move_z": 2.0, "rv_ratio": 1.5, "hold": 24}
    grid = {"move_z": [1.5, 2.0, 2.5], "rv_ratio": [1.25, 1.5, 2.0]}
    thesis = (
        "A violent multi-bar move on a volatility spike is dominated by "
        "forced flow (liquidation cascades).  Once realised vol peaks, the "
        "forced flow is spent and price partially retraces."
    )
    persistence = (
        "Liquidation mechanics are hard-wired into perp markets; cascades "
        "will keep overshooting as long as leverage exists."
    )
    risks = "News-driven moves do not retrace; sizing into spiking vol is dangerous."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        w = int(p["move_window"])
        ret_w = df["close"].pct_change(w)
        ret_z = zscore(ret_w, 200)
        rv_fast = realized_vol(df["close"], w)
        rv_slow = realized_vol(df["close"], 100)
        spike = rv_fast / rv_slow.replace(0.0, np.nan) > float(p["rv_ratio"])

        fade_long = (ret_z < -float(p["move_z"])) & spike    # crash → buy
        fade_short = (ret_z > float(p["move_z"])) & spike    # melt-up → sell
        raw = pd.Series(0.0, index=df.index)
        raw[fade_long] = 1.0
        raw[fade_short] = -1.0
        return raw.replace(0.0, np.nan).ffill(limit=int(p["hold"])).fillna(0.0)
