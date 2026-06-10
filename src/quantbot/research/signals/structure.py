"""Market-structure signal family.

These trade the levels every discretionary participant watches — swing
highs/lows, support/resistance, stop-clusters — on the theory that shared
reference points concentrate orders, and concentrated orders move price
predictably (break → continuation; sweep → reversal).

Causality note: a swing high at bar ``t`` is only *confirmed* after
``confirm`` lower highs print, i.e. at bar ``t + confirm``.  All level series
here are built so the level becomes visible exactly at its confirmation bar,
never earlier — the classic lookahead trap with pivot/fractal indicators.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.features.core import signed_volume_flow
from quantbot.research.signals.base import ResearchSignal, hysteresis_positions, register_signal


def confirmed_swings(
    high: pd.Series, low: pd.Series, confirm: int = 5
) -> tuple[pd.Series, pd.Series]:
    """Last confirmed swing-high and swing-low levels, visible from their
    confirmation bar onward (ffilled until superseded).

    A swing high at bar t requires high[t] to exceed the `confirm` highs on
    BOTH sides; it becomes known at t + confirm.
    """
    n = len(high)
    h = high.to_numpy(dtype=float)
    l = low.to_numpy(dtype=float)
    swing_hi = np.full(n, np.nan)
    swing_lo = np.full(n, np.nan)
    for t in range(confirm, n - confirm):
        seg_h = h[t - confirm : t + confirm + 1]
        if h[t] == seg_h.max() and (seg_h.argmax() == confirm):
            swing_hi[t + confirm] = h[t]          # known only at confirmation
        seg_l = l[t - confirm : t + confirm + 1]
        if l[t] == seg_l.min() and (seg_l.argmin() == confirm):
            swing_lo[t + confirm] = l[t]
    hi_level = pd.Series(swing_hi, index=high.index).ffill()
    lo_level = pd.Series(swing_lo, index=low.index).ffill()
    return hi_level, lo_level


@register_signal
class BreakOfStructureSignal(ResearchSignal):
    name = "break_of_structure"
    family = "structure"
    default_params = {"confirm": 5, "hold": 48}
    grid = {"confirm": [3, 5, 8], "hold": [24, 48, 96]}
    thesis = (
        "A close beyond the last confirmed swing high/low ('break of "
        "structure') flips the technical bias of every level-watcher at "
        "once: stops trigger through the level and sidelined breakout flow "
        "enters, producing continuation."
    )
    persistence = "Swing levels are the most universally watched objects in crypto charting."
    risks = "Engineered sweeps: large players push through levels to harvest the stops, then reverse."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        hi_level, lo_level = confirmed_swings(df["high"], df["low"], int(p["confirm"]))
        up = df["close"] > hi_level
        dn = df["close"] < lo_level
        bos_up = up & ~up.shift(1, fill_value=False)
        bos_dn = dn & ~dn.shift(1, fill_value=False)
        raw = pd.Series(0.0, index=df.index)
        raw[bos_up] = 1.0
        raw[bos_dn] = -1.0
        return raw.replace(0.0, np.nan).ffill(limit=int(p["hold"])).fillna(0.0)


@register_signal
class SupportResistanceSignal(ResearchSignal):
    name = "support_resistance"
    family = "structure"
    default_params = {"confirm": 5, "tolerance": 0.003, "hold": 24}
    grid = {"confirm": [3, 5, 8], "tolerance": [0.002, 0.003, 0.005]}
    thesis = (
        "Confirmed swing levels act as support/resistance because resting "
        "orders cluster there; a controlled touch-and-hold is a fade entry "
        "with a tight, well-defined invalidation."
    )
    persistence = "Anchoring is a robust behavioural bias; levels regenerate every cycle."
    risks = "Third+ tests of a level tend to break it; distinguishing touch from break costs latency."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        tol = float(p["tolerance"])
        hi_level, lo_level = confirmed_swings(df["high"], df["low"], int(p["confirm"]))
        near_support = (df["low"] <= lo_level * (1 + tol)) & (df["close"] > lo_level)
        near_resist = (df["high"] >= hi_level * (1 - tol)) & (df["close"] < hi_level)
        # Require a reversal-shaped bar: close back in the level's favour.
        bull_bar = df["close"] > df["open"]
        bear_bar = df["close"] < df["open"]
        raw = pd.Series(0.0, index=df.index)
        raw[near_support & bull_bar] = 1.0
        raw[near_resist & bear_bar] = -1.0
        return raw.replace(0.0, np.nan).ffill(limit=int(p["hold"])).fillna(0.0)


@register_signal
class LiquiditySweepSignal(ResearchSignal):
    name = "liquidity_sweep"
    family = "structure"
    default_params = {"confirm": 5, "hold": 24}
    grid = {"confirm": [3, 5, 8], "hold": [12, 24, 48]}
    thesis = (
        "Stops cluster just beyond swing points.  A wick that pierces the "
        "level but CLOSES back inside means the stop liquidity was consumed "
        "by an absorber, not a breakout — the move then reverses (the "
        "'stop hunt' / sweep-and-reclaim pattern)."
    )
    persistence = (
        "Stop placement behaviour is stable; sweeping it is a repeated game "
        "between forced retail flow and inventory-seeking market makers."
    )
    risks = "Real breakouts also start as wicks; mislabel rate is irreducible."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        hi_level, lo_level = confirmed_swings(df["high"], df["low"], int(p["confirm"]))
        # Use the PRIOR bar's level so a new swing printed this bar can't be swept same-bar.
        hi_ref, lo_ref = hi_level.shift(1), lo_level.shift(1)
        sweep_low = (df["low"] < lo_ref) & (df["close"] > lo_ref)     # swept & reclaimed → long
        sweep_high = (df["high"] > hi_ref) & (df["close"] < hi_ref)   # swept & rejected → short
        raw = pd.Series(0.0, index=df.index)
        raw[sweep_low] = 1.0
        raw[sweep_high] = -1.0
        return raw.replace(0.0, np.nan).ffill(limit=int(p["hold"])).fillna(0.0)


@register_signal
class OrderFlowProxySignal(ResearchSignal):
    name = "orderflow_proxy"
    family = "structure"
    default_params = {"window": 20, "entry_z": 1.5, "exit_z": 0.25}
    grid = {"window": [10, 20, 40], "entry_z": [1.0, 1.5, 2.0]}
    thesis = (
        "Without tick data, CLV-signed volume (volume credited to buyers "
        "when the close is near the high, sellers near the low) approximates "
        "net aggressor flow; persistent one-sided flow precedes price "
        "because large orders are worked over hours."
    )
    persistence = "Execution-driven flow autocorrelation is microstructural, not behavioural."
    risks = "Bar-level proxy is noisy vs real footprint data; venue volume quality varies."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        flow = signed_volume_flow(df, int(p["window"]))
        e, x = float(p["entry_z"]), float(p["exit_z"])
        return hysteresis_positions(
            enter_long=flow > e,
            exit_long=flow < x,
            enter_short=flow < -e,
            exit_short=flow > -x,
        )
