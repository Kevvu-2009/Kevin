import numpy as np
import pandas as pd

from quantbot.backtest.metrics import compute_metrics
from quantbot.validation import (
    evaluate_gates,
    is_oos_split,
    monte_carlo_equity,
)
from quantbot.validation.gates import AcceptanceCriteria


def test_is_oos_split_chronological(ohlcv):
    is_df, oos_df = is_oos_split(ohlcv, 0.70)
    assert len(is_df) + len(oos_df) == len(ohlcv)
    assert is_df.index.max() <= oos_df.index.min()
    assert abs(len(is_df) / len(ohlcv) - 0.70) < 0.01


def test_gates_reject_weak_strategy():
    weak_eq = pd.Series(np.linspace(100, 95, 200))  # losing
    m = compute_metrics(weak_eq, "1d", trade_pnl=[-1] * 40)
    rep = evaluate_gates(m, m)
    assert not rep.passed
    assert "oos_positive" in rep.checks and rep.checks["oos_positive"] is False


def test_gates_pass_strong_strategy():
    # Construct metrics that clear every gate.
    from quantbot.backtest.metrics import Metrics

    strong = Metrics(
        cagr=0.4, sharpe=1.8, sortino=2.4, calmar=3.0, max_drawdown=-0.12,
        volatility=0.3, total_return=0.5, win_rate=0.55, profit_factor=1.6,
        avg_trade=50, expectancy=40, n_trades=120,
    )
    rep = evaluate_gates(strong, strong)
    assert rep.passed, rep.reasons


def test_gates_drawdown_breach():
    from quantbot.backtest.metrics import Metrics

    m = Metrics(0.4, 1.8, 2.0, 1.0, -0.35, 0.3, 0.5, 0.55, 1.6, 50, 40, 120)
    rep = evaluate_gates(m, m)
    assert rep.checks["max_drawdown"] is False


def test_monte_carlo_basic():
    rng = np.random.default_rng(0)
    trade_returns = rng.normal(0.01, 0.05, 200)  # positive edge
    mc = monte_carlo_equity(trade_returns, n_sims=500, seed=1)
    assert mc.n_sims == 500
    assert 0.0 <= mc.prob_profit <= 1.0
    assert mc.terminal_p05 <= mc.terminal_p50 <= mc.terminal_p95
