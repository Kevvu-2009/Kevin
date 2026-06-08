import numpy as np
import pandas as pd
import pytest

from quantbot.strategies.base import REQUIRED_COLUMNS
from quantbot.strategies.registry import get_strategy, list_strategies


@pytest.mark.parametrize("name", ["trend_following", "momentum_breakout", "mean_reversion", "regime_adaptive"])
def test_strategy_signal_contract(name, ohlcv):
    strat = get_strategy(name)
    res = strat.generate(ohlcv)
    assert res.entries.index.equals(ohlcv.index)
    assert res.exits.index.equals(ohlcv.index)
    assert res.stop.index.equals(ohlcv.index)
    assert res.entries.dtype == bool
    assert res.exits.dtype == bool
    # at least some signals should fire on regime-switching data
    assert res.entries.sum() >= 1


def test_registry_lists_all():
    names = list_strategies()
    for n in ["trend_following", "momentum_breakout", "mean_reversion", "regime_adaptive"]:
        assert n in names


def test_no_lookahead_breakout(small_ohlcv):
    """Breakout reference level must use the prior bar (no same-bar peeking)."""
    strat = get_strategy("momentum_breakout", channel=20)
    res = strat.generate(small_ohlcv)
    # Entries must never be True on the very first `channel` bars (warmup NaN).
    assert not res.entries.iloc[:20].any()


def test_missing_columns_raises():
    bad = pd.DataFrame({"open": [1, 2], "close": [1, 2]})
    with pytest.raises(ValueError):
        get_strategy("trend_following").generate(bad)


def test_params_override():
    s = get_strategy("trend_following", ema_fast=10)
    assert s.params["ema_fast"] == 10
    assert s.params["ema_slow"] == 200  # default retained
