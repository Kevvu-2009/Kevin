"""Take-profit + fixed-stop behaviour in the backtest engine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.backtest.engine import BacktestEngine
from quantbot.config import CostConfig
from quantbot.strategies.base import Strategy, StrategyResult


def _frame(closes, highs, lows):
    idx = pd.date_range("2022-01-01", periods=len(closes), freq="4h", tz="UTC")
    opens = [closes[0]] + list(closes[:-1])
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes,
         "volume": [1.0] * len(closes)},
        index=idx,
    )


class _FixedLevels(Strategy):
    """Enter at bar 1; fixed stop/target supplied by the test."""

    default_params = {"stop": 0.0, "tp": 0.0}

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        entries = pd.Series(False, index=df.index)
        entries.iloc[1] = True
        stop = pd.Series(float(self.params["stop"]), index=df.index)
        tp = pd.Series(float(self.params["tp"]), index=df.index)
        exits = pd.Series(False, index=df.index)
        return StrategyResult(entries=entries, exits=exits, stop=stop,
                              take_profit=tp, trail=False)


_NO_COST = CostConfig(taker_fee=0.0, slippage_bps=0.0)


def test_take_profit_books_at_target():
    # Entry fills at bar 2 open (=100). Price ramps up; high reaches the 115
    # target at bar 5 while the low never touches the 95 stop.
    closes = [100, 100, 101, 105, 110, 116, 120]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    df = _frame(closes, highs, lows)

    eng = BacktestEngine(costs=_NO_COST, risk_per_trade=0.0075)
    res = eng.run(_FixedLevels(stop=95.0, tp=115.0), df, "4h")

    assert len(res.trades) == 1
    trade = res.trades.iloc[0]
    assert trade["reason"] == "take_profit"
    assert trade["exit_price"] == 115.0           # filled at the target
    assert abs(trade["return"] - 0.15) < 1e-9      # exactly 3:1 (15 up / 5 risk)


def test_stop_takes_priority_when_a_bar_spans_both():
    # Bar 3 spans both levels (low 97 <= stop 98, high 104 >= tp 103). The engine
    # must conservatively assume the stop was hit first.
    closes = [100, 100, 100, 101, 102]
    highs = [100.5, 100.5, 100.5, 104.0, 102.5]
    lows = [99.5, 99.5, 99.5, 97.0, 101.5]
    df = _frame(closes, highs, lows)

    eng = BacktestEngine(costs=_NO_COST, risk_per_trade=0.0075)
    res = eng.run(_FixedLevels(stop=98.0, tp=103.0), df, "4h")

    assert len(res.trades) == 1
    assert res.trades.iloc[0]["reason"] == "stop"


def test_fixed_stop_does_not_trail():
    # The supplied stop sits at 95 the whole time; with trail=False the engine
    # must never raise it, so a later dip to 96 does NOT stop us out and we run
    # to the target.
    closes = [100, 100, 108, 96, 112, 116]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    df = _frame(closes, highs, lows)

    eng = BacktestEngine(costs=_NO_COST, risk_per_trade=0.0075)
    res = eng.run(_FixedLevels(stop=95.0, tp=115.0), df, "4h")

    assert res.trades.iloc[0]["reason"] == "take_profit"
