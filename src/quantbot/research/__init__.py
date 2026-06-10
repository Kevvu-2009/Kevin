"""Edge-discovery research layer.

A fast, vectorized, cost-aware screening engine plus a library of candidate
signals across trend, momentum, mean-reversion, volatility, market-structure,
regime, statistical-arbitrage, ML and hybrid families — and the validation
harness (walk-forward, Monte Carlo, parameter sensitivity, regime breakdown,
deflated Sharpe) that decides which candidates deserve capital.

Research uses this layer to *find and rank* edges; the event-driven engine in
``quantbot.backtest`` re-verifies the survivors with full order mechanics
before anything is deployed.
"""

from quantbot.research.vector_engine import CostModel, VectorBacktestResult, backtest_positions
from quantbot.research.signals.base import SIGNAL_REGISTRY, get_signal, list_signals

__all__ = [
    "CostModel",
    "VectorBacktestResult",
    "backtest_positions",
    "SIGNAL_REGISTRY",
    "get_signal",
    "list_signals",
]
