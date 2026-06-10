"""Validation harness: deflated Sharpe, bootstrap, walk-forward, gates."""

import numpy as np
import pandas as pd
import pytest

from quantbot.data.synthetic import generate_ohlcv, generate_random_walk
from quantbot.research.signals.trend import EMACrossSignal
from quantbot.research.validation import (
    CostModel,
    ResearchGates,
    block_bootstrap_paths,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    validate_candidate,
    walk_forward_signal,
)


def test_psr_strong_signal_high_probability():
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0.001, 0.005, 2000))  # SR/bar = 0.2: very strong
    sr = float(r.mean() / r.std(ddof=0))
    p = probabilistic_sharpe_ratio(sr, 0.0, len(r), 0.0, 3.0)
    assert p > 0.99


def test_psr_zero_signal_near_half():
    p = probabilistic_sharpe_ratio(0.0, 0.0, 1000, 0.0, 3.0)
    assert abs(p - 0.5) < 1e-9


def test_expected_max_sharpe_grows_with_trials():
    v = 0.001
    assert expected_max_sharpe(10, v) < expected_max_sharpe(100, v) < expected_max_sharpe(1000, v)


def test_dsr_penalises_trial_count():
    rng = np.random.default_rng(2)
    r = pd.Series(rng.normal(0.0004, 0.01, 3000))  # modest edge
    few = deflated_sharpe_ratio(r, n_trials=2)
    many = deflated_sharpe_ratio(r, n_trials=5000)
    assert few > many


def test_dsr_zero_mean_low_probability():
    rng = np.random.default_rng(3)
    r = pd.Series(rng.normal(0.0, 0.01, 3000))
    assert deflated_sharpe_ratio(r, n_trials=100) < 0.7


def test_block_bootstrap_shapes_and_sanity():
    rng = np.random.default_rng(4)
    r = pd.Series(rng.normal(0.0005, 0.01, 2000))
    out = block_bootstrap_paths(r, block=20, n_sims=200)
    assert out.n_sims == 200
    assert out.terminal_p05 < out.terminal_p50
    assert -1.0 < out.max_dd_p05 <= out.max_dd_median <= 0.0
    assert 0.0 <= out.prob_loss <= 1.0


def test_walk_forward_windows_are_chronological():
    df = generate_ohlcv(n=4000, seed=8)
    wf = walk_forward_signal(EMACrossSignal, df, "1h", CostModel(), n_splits=4)
    assert len(wf["windows"]) == 4
    starts = [w["test_start"] for w in wf["windows"]]
    assert starts == sorted(starts)
    assert 0.0 <= wf["positive_window_frac"] <= 1.0
    # Stitched OOS returns cover the test region only.
    assert len(wf["returns"]) < len(df)


def test_validate_candidate_full_structure():
    df = generate_ohlcv(n=4000, seed=8)
    cv = validate_candidate(EMACrossSignal, df, "1h", ("SYN",), mc_sims=100, wf_splits=3)
    row = cv.to_row()
    for key in ("oos_sharpe", "deflated_prob", "robustness_score", "passed",
                "wf_positive_windows", "mc_dd_p05", "sens_retention", "lag_sharpe"):
        assert key in row
    assert 0.0 <= cv.robustness_score <= 100.0
    assert cv.n_trials >= len(EMACrossSignal.grid_combinations())
    assert set(cv.gates.checks) >= {
        "oos_positive", "oos_sharpe", "profit_factor", "max_drawdown",
        "min_trades", "wf_consistency", "mc_drawdown", "sensitivity",
        "deflated_sharpe", "lag_stress", "regime_floor",
    }


def test_random_walk_candidate_rejected():
    """The harness must not bless an edge on a martingale."""
    df = generate_random_walk(n=5000, seed=42)
    cv = validate_candidate(EMACrossSignal, df, "1h", ("NULL",), mc_sims=100, wf_splits=3)
    assert not cv.gates.passed


def test_gates_configurable():
    df = generate_ohlcv(n=3000, seed=8)
    lax = ResearchGates(
        min_oos_sharpe=-10, min_oos_profit_factor=0, max_oos_drawdown=1.0,
        min_oos_trades=0, require_positive_oos=False, min_oos_is_sharpe_ratio=-10,
        min_wf_positive_windows=0.0, max_mc_p05_drawdown=1.0,
        min_sensitivity_retention=-1.0, min_deflated_prob=0.0,
        min_lag_stress_sharpe=-10.0, worst_regime_max_drawdown=1.0,
    )
    cv = validate_candidate(EMACrossSignal, df, "1h", ("SYN",), gates=lax,
                            mc_sims=50, wf_splits=3)
    assert cv.gates.passed  # everything passes under no-op gates
