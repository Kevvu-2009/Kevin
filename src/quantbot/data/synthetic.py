"""Synthetic OHLCV generation for tests, demos and offline pipeline runs.

Produces a regime-switching geometric-Brownian-motion price path (trending and
mean-reverting segments) so that every strategy has conditions it should and
shouldn't trade — useful for sanity-checking the research/validation pipeline
without a live data feed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_TF_FREQ = {"5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}


def generate_ohlcv(
    n: int = 3000,
    timeframe: str = "1h",
    start: str = "2022-01-01",
    seed: int = 7,
    start_price: float = 20_000.0,
) -> pd.DataFrame:
    """Generate a realistic-ish regime-switching OHLCV frame."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=n, freq=_TF_FREQ.get(timeframe, "1h"), tz="UTC")

    # Alternate trend / range regimes with different drift & vol.
    regime_len = max(50, n // 12)
    drift = np.zeros(n)
    vol = np.full(n, 0.01)
    k = 0
    while k < n:
        seg = slice(k, min(k + regime_len, n))
        if (k // regime_len) % 2 == 0:  # trend regime
            drift[seg] = rng.choice([1, -1]) * rng.uniform(0.0003, 0.0009)
            vol[seg] = rng.uniform(0.008, 0.015)
        else:  # range regime
            drift[seg] = 0.0
            vol[seg] = rng.uniform(0.004, 0.009)
        k += regime_len

    shocks = rng.standard_normal(n) * vol + drift
    logp = np.log(start_price) + np.cumsum(shocks)
    close = np.exp(logp)

    # Build OHLC around the close path.
    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]
    intrabar = np.abs(rng.standard_normal(n)) * vol * close
    high = np.maximum(open_, close) + intrabar
    low = np.minimum(open_, close) - intrabar
    low = np.clip(low, 1e-6, None)
    volume = rng.uniform(50, 500, n) * (1 + np.abs(shocks) * 20)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def generate_random_walk(
    n: int = 3000,
    timeframe: str = "1h",
    start: str = "2022-01-01",
    seed: int = 7,
    start_price: float = 20_000.0,
    vol: float = 0.01,
) -> pd.DataFrame:
    """Zero-drift martingale OHLCV (with GARCH-like vol clustering but NO
    exploitable return autocorrelation).

    The null benchmark for the discovery pipeline: a research harness worth
    trusting must find (almost) nothing here.  Vol clustering is included so
    vol-conditioned signals face realistic — but unmonetisable — structure.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=n, freq=_TF_FREQ.get(timeframe, "1h"), tz="UTC")

    # GARCH(1,1)-ish conditional vol; returns themselves are iid-signed.
    sig2 = np.empty(n)
    sig2[0] = vol**2
    omega, alpha, beta = 0.05 * vol**2, 0.10, 0.85
    z = rng.standard_normal(n)
    shocks = np.empty(n)
    for t in range(n):
        if t > 0:
            sig2[t] = omega + alpha * shocks[t - 1] ** 2 + beta * sig2[t - 1]
        shocks[t] = np.sqrt(sig2[t]) * z[t]

    logp = np.log(start_price) + np.cumsum(shocks)
    close = np.exp(logp)
    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]
    intrabar = np.abs(rng.standard_normal(n)) * np.sqrt(sig2) * close
    high = np.maximum(open_, close) + intrabar
    low = np.clip(np.minimum(open_, close) - intrabar, 1e-6, None)
    volume = rng.uniform(50, 500, n) * (1 + np.abs(shocks) * 20)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
