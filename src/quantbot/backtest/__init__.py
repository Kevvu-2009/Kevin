"""Backtesting framework: realistic engine + performance metrics + reports."""

from quantbot.backtest.engine import BacktestEngine, BacktestResult
from quantbot.backtest.metrics import compute_metrics

__all__ = ["BacktestEngine", "BacktestResult", "compute_metrics"]
