import numpy as np
import pandas as pd

from quantbot.backtest.engine import BacktestEngine
from quantbot.config import CostConfig
from quantbot.strategies.base import Strategy, StrategyResult


class _AlwaysFlat(Strategy):
    name = "always_flat"

    def generate(self, df):
        false = pd.Series(False, index=df.index)
        nan = pd.Series(np.nan, index=df.index)
        return StrategyResult(entries=false, exits=false.copy(), stop=nan)


class _BuyAndHold(Strategy):
    name = "buy_hold_test"

    def generate(self, df):
        entries = pd.Series(False, index=df.index)
        entries.iloc[1] = True
        exits = pd.Series(False, index=df.index)
        nan = pd.Series(np.nan, index=df.index)
        return StrategyResult(entries=entries, exits=exits, stop=nan)


def _frame(prices):
    idx = pd.date_range("2023-01-01", periods=len(prices), freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": prices, "high": [p * 1.001 for p in prices],
         "low": [p * 0.999 for p in prices], "close": prices,
         "volume": [1.0] * len(prices)},
        index=idx,
    )


def test_flat_strategy_keeps_cash():
    df = _frame([100, 101, 102, 103, 104])
    res = BacktestEngine(initial_cash=10_000).run(_AlwaysFlat(), df, "1h")
    assert abs(res.equity.iloc[-1] - 10_000) < 1e-6
    assert len(res.trades) == 0


def test_buy_and_hold_profits_on_uptrend():
    prices = list(np.linspace(100, 200, 50))
    df = _frame(prices)
    res = BacktestEngine(initial_cash=10_000).run(_BuyAndHold(), df, "1h")
    assert res.equity.iloc[-1] > 10_000
    assert len(res.trades) == 1


def test_costs_reduce_returns():
    prices = list(np.linspace(100, 110, 30))
    df = _frame(prices)
    nofee = BacktestEngine(initial_cash=10_000, costs=CostConfig(taker_fee=0, slippage_bps=0)).run(
        _BuyAndHold(), df, "1h"
    )
    withfee = BacktestEngine(
        initial_cash=10_000, costs=CostConfig(taker_fee=0.001, slippage_bps=10)
    ).run(_BuyAndHold(), df, "1h")
    assert withfee.equity.iloc[-1] < nofee.equity.iloc[-1]


def test_no_lookahead_entry_fills_next_bar():
    # Entry signal on bar 1 must fill at bar 2 open, not bar 1.
    prices = [100, 100, 200, 200]
    df = _frame(prices)
    res = BacktestEngine(initial_cash=10_000, costs=CostConfig(taker_fee=0, slippage_bps=0)).run(
        _BuyAndHold(), df, "1h"
    )
    # filled at bar index 2 open == 200
    assert abs(res.trades.iloc[0]["entry_price"] - 200) < 1e-6
