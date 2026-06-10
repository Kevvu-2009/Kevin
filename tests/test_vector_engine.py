"""Vectorized research engine: cost accounting, lookahead immunity, trades."""

import numpy as np
import pandas as pd
import pytest

from quantbot.data.synthetic import generate_ohlcv
from quantbot.research.vector_engine import (
    CostModel,
    backtest_panel,
    backtest_positions,
)


@pytest.fixture(scope="module")
def df():
    return generate_ohlcv(n=1500, seed=21)


def test_flat_positions_no_pnl_no_cost(df):
    pos = pd.Series(0.0, index=df.index)
    res = backtest_positions(df, pos, "1h")
    assert res.equity.iloc[-1] == pytest.approx(1.0)
    assert res.metrics.n_trades == 0
    assert res.exposure == 0.0


def test_buy_and_hold_tracks_price(df):
    pos = pd.Series(1.0, index=df.index)
    res = backtest_positions(df, pos, "1h", CostModel(fee_bps=0, slippage_bps=0, spread_bps=0))
    # Long from the open after the first decision bar to the final close.
    expected = df["close"].iloc[-1] / df["open"].iloc[1] - 1.0
    assert res.equity.iloc[-1] - 1.0 == pytest.approx(expected, rel=1e-9)


def test_costs_charged_on_turnover(df):
    costs = CostModel(fee_bps=10.0, slippage_bps=0.0, spread_bps=0.0)
    # One round trip: in for 10 bars, then flat.
    pos = pd.Series(0.0, index=df.index)
    pos.iloc[100:110] = 1.0
    res_free = backtest_positions(df, pos, "1h", CostModel(0, 0, 0))
    res_paid = backtest_positions(df, pos, "1h", costs)
    # Two units of turnover (enter + exit) at 10 bps each ≈ 20 bps drag.
    drag = res_free.equity.iloc[-1] - res_paid.equity.iloc[-1]
    assert 0.0015 < drag < 0.0025


def test_lookahead_immunity(df):
    """A signal that knows the future must NOT be able to monetise the final
    bar: positions act with a 1-bar execution delay."""
    # "Perfect oracle" for the last bar: long iff the final open->close is up.
    pos = pd.Series(0.0, index=df.index)
    pos.iloc[-1] = 1.0  # decided at the very last close — no bar left to trade
    res = backtest_positions(df, pos, "1h", CostModel(0, 0, 0))
    assert res.equity.iloc[-1] == pytest.approx(1.0)


def test_execution_lag_changes_attribution(df):
    rng = np.random.default_rng(3)
    pos = pd.Series(rng.choice([-1.0, 0.0, 1.0], len(df)), index=df.index)
    base = backtest_positions(df, pos, "1h", CostModel(0, 0, 0))
    lagged = backtest_positions(df, pos, "1h", CostModel(0, 0, 0), extra_lag=1)
    # Same positions, shifted attribution → different equity path.
    assert not np.allclose(base.equity.to_numpy(), lagged.equity.to_numpy())


def test_trade_segmentation(df):
    pos = pd.Series(0.0, index=df.index)
    pos.iloc[10:20] = 1.0
    pos.iloc[30:40] = -1.0
    pos.iloc[50:55] = 1.0
    res = backtest_positions(df, pos, "1h")
    assert res.metrics.n_trades == 3
    assert list(res.trades["direction"]) == [1, -1, 1]


def test_positions_clipped_and_nan_safe(df):
    pos = pd.Series(5.0, index=df.index)  # over-levered request
    pos.iloc[100:200] = np.nan
    res = backtest_positions(df, pos, "1h")
    assert res.positions.abs().max() <= 1.0 + 1e-12


def test_panel_aggregates_equal_weight():
    a = generate_ohlcv(n=800, seed=1)
    b = generate_ohlcv(n=800, seed=2, start_price=100)
    panel = {"A": a, "B": b}
    positions = {
        "A": pd.Series(1.0, index=a.index),
        "B": pd.Series(0.0, index=b.index),
    }
    res = backtest_panel(panel, positions, "1h", CostModel(0, 0, 0))
    solo = backtest_positions(a, positions["A"], "1h", CostModel(0, 0, 0))
    # Half the capital in A, half idle → half the log-return, approx.
    assert res.equity.iloc[-1] - 1.0 == pytest.approx((solo.equity.iloc[-1] - 1.0) / 2, rel=0.2)


def test_short_position_profits_in_decline():
    n = 400
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    price = np.linspace(100, 50, n)  # monotone decline
    df = pd.DataFrame(
        {"open": price, "high": price * 1.001, "low": price * 0.999,
         "close": price, "volume": np.ones(n)},
        index=idx,
    )
    pos = pd.Series(-1.0, index=idx)
    res = backtest_positions(df, pos, "1h", CostModel(0, 0, 0))
    assert res.equity.iloc[-1] > 1.4
