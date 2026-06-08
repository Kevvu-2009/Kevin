"""Walk-forward analysis.

Rolling (or anchored) windows: fit parameters on a train slice, then evaluate on
the immediately following test slice, and step forward.  The concatenation of
test-slice results is the *walk-forward equity curve* — the most honest proxy
for live performance because every test bar was unseen when its parameters were
chosen.

This module is agnostic to *how* parameters are chosen: pass a ``fit_fn`` that
receives the train frame and returns a parameter dict.  For a fixed-parameter
robustness check, pass a ``fit_fn`` that ignores train and returns constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from quantbot.backtest.engine import BacktestEngine
from quantbot.backtest.metrics import Metrics, compute_metrics
from quantbot.config import CostConfig
from quantbot.strategies.registry import get_strategy


@dataclass
class WalkForwardResult:
    equity: pd.Series
    metrics: Metrics
    windows: list[dict]
    timeframe: str


def walk_forward(
    strategy_name: str,
    df: pd.DataFrame,
    timeframe: str,
    fit_fn: Callable[[pd.DataFrame], dict],
    n_splits: int = 5,
    train_frac: float = 0.6,
    costs: CostConfig | None = None,
    initial_cash: float = 10_000.0,
    risk_per_trade: float = 0.0075,
) -> WalkForwardResult:
    """Run anchored-train / rolling-test walk-forward.

    The data is divided into ``n_splits`` test blocks; each test block uses the
    parameters fitted on all data up to its start (anchored) blended with a
    minimum ``train_frac`` history requirement.
    """
    df = df.sort_index()
    n = len(df)
    if n < n_splits * 4:
        raise ValueError("Not enough data for the requested number of splits")

    engine = BacktestEngine(costs=costs, initial_cash=initial_cash, risk_per_trade=risk_per_trade)
    test_size = int(n * (1 - train_frac) / n_splits)
    if test_size < 1:
        test_size = max(1, n // (n_splits + 2))

    windows: list[dict] = []
    stitched: list[pd.Series] = []
    equity_base = initial_cash

    start_test = n - test_size * n_splits
    for k in range(n_splits):
        test_lo = start_test + k * test_size
        test_hi = test_lo + test_size
        train = df.iloc[:test_lo]
        test = df.iloc[max(0, test_lo - 250):test_hi]  # warm-up tail for indicators
        if len(train) < 50 or len(test) < 5:
            continue

        params = fit_fn(train)
        strat = get_strategy(strategy_name, **params)
        res = engine.run(strat, test, timeframe)

        # Rescale this window's equity so segments compound continuously.
        seg = res.equity.iloc[-test_size:] if len(res.equity) >= test_size else res.equity
        scale = equity_base / seg.iloc[0] if len(seg) and seg.iloc[0] else 1.0
        seg_scaled = seg * scale
        equity_base = seg_scaled.iloc[-1] if len(seg_scaled) else equity_base
        stitched.append(seg_scaled)

        windows.append(
            {
                "window": k,
                "train_end": str(train.index[-1]) if len(train) else None,
                "test_start": str(test.index[-test_size]) if len(test) >= test_size else None,
                "test_end": str(test.index[-1]) if len(test) else None,
                "params": params,
                "metrics": res.stats,
            }
        )

    if not stitched:
        empty = pd.Series([initial_cash], index=[df.index[-1]])
        return WalkForwardResult(empty, compute_metrics(empty, timeframe), windows, timeframe)

    wf_equity = pd.concat(stitched)
    wf_equity = wf_equity[~wf_equity.index.duplicated(keep="last")].sort_index()
    pnl = np.diff(wf_equity.to_numpy())
    metrics = compute_metrics(wf_equity, timeframe, pnl)
    return WalkForwardResult(wf_equity, metrics, windows, timeframe)
