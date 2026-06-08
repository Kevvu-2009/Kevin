import numpy as np
import pandas as pd

from quantbot.backtest.metrics import (
    cagr,
    compute_metrics,
    max_drawdown,
    sharpe,
    trade_stats,
)


def test_max_drawdown_known():
    eq = pd.Series([100, 120, 60, 90, 150])
    # peak 120 -> trough 60 => -50%
    assert abs(max_drawdown(eq) - (-0.5)) < 1e-9


def test_cagr_doubling_one_year_daily():
    n = 365
    eq = pd.Series(np.linspace(100, 200, n + 1))
    c = cagr(eq, "1d")
    assert abs(c - 1.0) < 0.05  # ~100% over one year


def test_sharpe_zero_variance():
    r = pd.Series([0.0] * 50)
    assert sharpe(r, "1d") == 0.0


def test_sharpe_positive_for_uptrend():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.001, 0.005, 1000))
    assert sharpe(r, "1d") > 0


def test_trade_stats_profit_factor():
    pnl = [10, -5, 20, -5, -5]
    s = trade_stats(pnl)
    assert s["n_trades"] == 5
    assert abs(s["profit_factor"] - (30 / 15)) < 1e-9
    assert abs(s["win_rate"] - 0.4) < 1e-9


def test_compute_metrics_runs():
    eq = pd.Series(np.linspace(100, 130, 500))
    m = compute_metrics(eq, "1h", trade_pnl=[1, -1, 2, 3, -1])
    assert m.total_return > 0
    assert m.n_trades == 5
