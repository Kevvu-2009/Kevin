"""End-to-end discovery: sweep, rank, report — plus the null-data property."""

from pathlib import Path

import pandas as pd
import pytest

from quantbot.data.synthetic import generate_ohlcv, generate_random_walk
from quantbot.reporting.research_report import render_markdown, write_research_report
from quantbot.research.discovery import DiscoveryConfig, count_planned_trials, run_discovery


@pytest.fixture(scope="module")
def trending_panel():
    return {
        "AAA": generate_ohlcv(n=3000, seed=1),
        "BBB": generate_ohlcv(n=3000, seed=2, start_price=900.0),
    }


@pytest.fixture(scope="module")
def fast_cfg():
    return DiscoveryConfig(
        timeframe="1h",
        families=("trend", "mean_reversion"),   # small, fast subset
        include_ml=False,
        mc_sims=60,
        wf_splits=3,
        min_bars=1500,
    )


def test_trial_count_covers_grid(trending_panel, fast_cfg):
    n = count_planned_trials(trending_panel, fast_cfg)
    # 6 trend signals + 4 MR signals across 2 symbols with small grids.
    assert n > 50


def test_discovery_end_to_end(tmp_path, trending_panel, fast_cfg):
    result = run_discovery(trending_panel, fast_cfg)
    assert len(result.candidates) > 10
    assert isinstance(result.leaderboard, pd.DataFrame)
    assert set(result.leaderboard["family"]) <= {"trend", "mean_reversion"}
    # Leaderboard sorted: passers first, then by robustness score.
    lb = result.leaderboard
    if lb["passed"].any():
        first_block = lb[lb["passed"]]
        assert first_block["robustness_score"].is_monotonic_decreasing

    md = render_markdown(result)
    assert "Full leaderboard" in md and "Rejected candidates" in md
    paths = write_research_report(result, tmp_path / "research")
    for p in paths.values():
        assert Path(p).exists() and Path(p).stat().st_size > 0


def test_discovery_mostly_rejects_random_walks(fast_cfg):
    """False-discovery control: on martingale data with realistic costs, the
    pipeline must reject (nearly) everything.  A small tolerance is allowed —
    with dozens of candidates a rare false positive is statistically
    expected — but wholesale acceptance means the harness is broken."""
    panel = {
        "NULL1": generate_random_walk(n=3000, seed=101),
        "NULL2": generate_random_walk(n=3000, seed=202),
    }
    result = run_discovery(panel, fast_cfg)
    n = len(result.candidates)
    assert n > 10
    accept_rate = len(result.selected) / n
    assert accept_rate <= 0.1, (
        f"{len(result.selected)}/{n} null candidates accepted — "
        "validation gates are too weak"
    )


def test_discovery_refuses_short_series(fast_cfg):
    with pytest.raises(ValueError):
        run_discovery({"X": generate_ohlcv(n=300, seed=3)}, fast_cfg)
