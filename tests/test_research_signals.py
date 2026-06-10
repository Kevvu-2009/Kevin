"""Signal-library contracts: causality, range, alignment — for EVERY signal.

The truncation-invariance test is the load-bearing one: a signal computed on
the full history must agree with itself computed on any prefix, on that
prefix (minus a small settling tail for stateful/refit signals).  Any
violation means information from the future reached an earlier bar.
"""

import numpy as np
import pandas as pd
import pytest

from quantbot.data.synthetic import generate_ohlcv
from quantbot.research.signals import SIGNAL_REGISTRY, PanelSignal, get_signal
from quantbot.research.signals.base import hysteresis_positions
from quantbot.research.signals.structure import confirmed_swings

SINGLE = sorted(
    name
    for name, cls in SIGNAL_REGISTRY.items()
    if not issubclass(cls, PanelSignal) and cls.family != "machine_learning"
)
PANEL = sorted(
    name for name, cls in SIGNAL_REGISTRY.items() if issubclass(cls, PanelSignal)
)


@pytest.fixture(scope="module")
def df():
    return generate_ohlcv(n=2200, seed=9)


@pytest.fixture(scope="module")
def panel():
    return {
        "AAA": generate_ohlcv(n=2200, seed=1),
        "BBB": generate_ohlcv(n=2200, seed=2, start_price=900.0),
        "CCC": generate_ohlcv(n=2200, seed=4, start_price=55.0),
        "DDD": generate_ohlcv(n=2200, seed=6, start_price=7.0),
    }


@pytest.mark.parametrize("name", SINGLE)
def test_signal_contract(name, df):
    sig = get_signal(name)
    pos = sig.generate(df)
    assert isinstance(pos, pd.Series)
    assert pos.index.equals(df.index)
    assert not pos.isna().any(), "positions must be NaN-free"
    assert pos.abs().max() <= 1.0 + 1e-9


@pytest.mark.parametrize("name", SINGLE)
def test_signal_causality_truncation(name, df):
    """Signal on a prefix must equal the full-sample signal on that prefix."""
    sig = get_signal(name)
    cut = len(df) - 300
    full = sig.generate(df).iloc[:cut]
    pre = sig.generate(df.iloc[:cut])
    pd.testing.assert_series_equal(full, pre, check_names=False)


@pytest.mark.parametrize("name", PANEL)
def test_panel_signal_contract(name, panel):
    cls = SIGNAL_REGISTRY[name]
    data = panel if name == "xsec_momentum" else {k: panel[k] for k in ("AAA", "BBB")}
    out = cls().generate_panel(data)
    assert set(out) == set(data)
    for sym, pos in out.items():
        assert pos.index.equals(data[sym].index)
        assert pos.abs().max() <= 1.0 + 1e-9
        assert not pos.isna().any()


@pytest.mark.parametrize("name", PANEL)
def test_panel_signal_causality(name, panel):
    cls = SIGNAL_REGISTRY[name]
    data = panel if name == "xsec_momentum" else {k: panel[k] for k in ("AAA", "BBB")}
    cut = 1800
    truncated = {k: v.iloc[:cut] for k, v in data.items()}
    full = cls().generate_panel(data)
    pre = cls().generate_panel(truncated)
    for sym in data:
        # Hedge-ratio refit schedules align to the series start, so prefixes
        # match exactly; compare the overlap.
        pd.testing.assert_series_equal(
            full[sym].iloc[:cut], pre[sym], check_names=False
        )


def test_ml_classifier_runs_and_is_causal():
    df = generate_ohlcv(n=2400, seed=13)
    sig = get_signal("ml_classifier", min_train=800, refit_every=400, horizon=6)
    pos = sig.generate(df)
    assert pos.index.equals(df.index)
    assert pos.abs().max() <= 1.0
    # Warm-up must be flat: no predictions before the first refit.
    assert (pos.iloc[:806] == 0).all()
    # Causality: truncating the tail must not change earlier positions.
    cut = 2000
    pre = get_signal("ml_classifier", min_train=800, refit_every=400, horizon=6).generate(
        df.iloc[:cut]
    )
    pd.testing.assert_series_equal(pos.iloc[:cut], pre, check_names=False)


def test_hysteresis_state_machine():
    idx = pd.date_range("2024-01-01", periods=8, freq="1h", tz="UTC")
    enter_long = pd.Series([1, 0, 0, 0, 0, 0, 0, 0], index=idx, dtype=bool)
    exit_long = pd.Series([0, 0, 1, 0, 0, 0, 0, 0], index=idx, dtype=bool)
    enter_short = pd.Series([0, 0, 0, 0, 1, 0, 0, 0], index=idx, dtype=bool)
    exit_short = pd.Series([0, 0, 0, 0, 0, 0, 1, 0], index=idx, dtype=bool)
    pos = hysteresis_positions(enter_long, exit_long, enter_short, exit_short)
    assert list(pos) == [1, 1, 0, 0, -1, -1, 0, 0]


def test_confirmed_swings_are_lagged():
    """A swing level must not be visible before its confirmation bar."""
    n = 60
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    high = pd.Series(10.0, index=idx)
    low = pd.Series(9.0, index=idx)
    high.iloc[20] = 15.0  # isolated swing high at bar 20
    hi_level, _ = confirmed_swings(high, low, confirm=5)
    assert hi_level.iloc[:25].isna().all()      # invisible until bar 25
    assert hi_level.iloc[25] == 15.0            # confirmed exactly at +confirm


def test_every_family_represented():
    families = {cls.family for cls in SIGNAL_REGISTRY.values()}
    assert {
        "trend", "momentum", "mean_reversion", "volatility",
        "structure", "regime", "stat_arb", "machine_learning", "hybrid",
    } <= families


def test_signals_document_their_economics():
    for name, cls in SIGNAL_REGISTRY.items():
        assert cls.thesis, f"{name} missing thesis"
        assert cls.persistence, f"{name} missing persistence rationale"
        assert cls.risks, f"{name} missing risk statement"
        assert cls.grid_combinations(), f"{name} has an empty grid"
