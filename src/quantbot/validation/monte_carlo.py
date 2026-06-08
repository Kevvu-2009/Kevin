"""Monte Carlo robustness simulation.

Two complementary resamplers:

* **Trade bootstrap** — resample the realised per-trade returns with
  replacement and recompound.  Answers: "how lucky was the *ordering* and
  *selection* of my trades?"  Produces a distribution of terminal equity, CAGR
  and max drawdown with confidence bounds.
* **Block bootstrap of bar returns** — preserves short-horizon autocorrelation
  by resampling contiguous blocks of returns.

A strategy whose 5th-percentile outcome is still acceptable is far more
trustworthy than one that relies on a single fortunate path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class MonteCarloResult:
    n_sims: int
    cagr_mean: float
    cagr_p05: float
    cagr_p95: float
    max_dd_mean: float
    max_dd_p95: float          # worst (most negative) tail of drawdown
    prob_profit: float
    terminal_p05: float
    terminal_p50: float
    terminal_p95: float

    def to_dict(self) -> dict:
        return self.__dict__


def _max_dd(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    return float((equity / peak - 1.0).min())


def monte_carlo_equity(
    trade_returns: pd.Series | np.ndarray | list,
    n_sims: int = 2_000,
    initial: float = 10_000.0,
    seed: int | None = 42,
) -> MonteCarloResult:
    """Trade-bootstrap Monte Carlo over per-trade returns (fractional)."""
    r = np.asarray(trade_returns, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 3:
        return MonteCarloResult(0, 0, 0, 0, 0, 0, 0, initial, initial, initial)

    rng = np.random.default_rng(seed)
    n = len(r)
    terminals = np.empty(n_sims)
    cagrs = np.empty(n_sims)
    dds = np.empty(n_sims)
    # Assume ~ the same number of trades per simulated path as observed.
    for i in range(n_sims):
        sample = rng.choice(r, size=n, replace=True)
        equity = initial * np.cumprod(1.0 + sample)
        equity = np.concatenate([[initial], equity])
        terminals[i] = equity[-1]
        dds[i] = _max_dd(equity)
        # CAGR proxy: treat the trade sequence as one "period" → geometric.
        growth = equity[-1] / initial
        cagrs[i] = growth - 1.0  # total return over the path

    return MonteCarloResult(
        n_sims=n_sims,
        cagr_mean=float(cagrs.mean()),
        cagr_p05=float(np.percentile(cagrs, 5)),
        cagr_p95=float(np.percentile(cagrs, 95)),
        max_dd_mean=float(dds.mean()),
        max_dd_p95=float(np.percentile(dds, 5)),  # 5th pct = worst drawdowns
        prob_profit=float((terminals > initial).mean()),
        terminal_p05=float(np.percentile(terminals, 5)),
        terminal_p50=float(np.percentile(terminals, 50)),
        terminal_p95=float(np.percentile(terminals, 95)),
    )


def block_bootstrap_returns(
    bar_returns: pd.Series | np.ndarray,
    block: int = 20,
    n_sims: int = 1_000,
    seed: int | None = 42,
) -> np.ndarray:
    """Return an array of terminal equities from block-bootstrapped bar returns."""
    r = np.asarray(bar_returns, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < block * 2:
        return np.array([])
    rng = np.random.default_rng(seed)
    n = len(r)
    n_blocks = int(np.ceil(n / block))
    out = np.empty(n_sims)
    starts_max = n - block
    for i in range(n_sims):
        starts = rng.integers(0, starts_max, size=n_blocks)
        path = np.concatenate([r[s:s + block] for s in starts])[:n]
        out[i] = float(np.prod(1.0 + path))
    return out
