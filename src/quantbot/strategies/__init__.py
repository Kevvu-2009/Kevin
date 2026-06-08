"""Plug-and-play strategy framework."""

from quantbot.strategies.base import Strategy, StrategyResult
from quantbot.strategies.registry import get_strategy, list_strategies, register

# Importing the concrete strategies registers them via the @register decorator.
from quantbot.strategies import (  # noqa: E402,F401
    mean_reversion,
    momentum_breakout,
    regime_adaptive,
    trend_following,
)

__all__ = [
    "Strategy",
    "StrategyResult",
    "get_strategy",
    "list_strategies",
    "register",
]
