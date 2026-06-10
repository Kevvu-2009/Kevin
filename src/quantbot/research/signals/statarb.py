"""Statistical-arbitrage signal family (panel signals).

These are *relative-value* trades: long one asset, short another, betting on
the relationship rather than the direction.  All hedge ratios and spread
statistics are estimated on trailing windows and refreshed periodically —
never fitted on the full sample (the canonical stat-arb backtest sin).

Crypto caveat (stated up front): most major pairs (e.g. ETH/BTC) share one
dominant factor, so cointegration in-sample is common but *regime-fragile* —
relationships break when narratives rotate.  Validation must therefore weight
the correlation-breakdown failure mode heavily for this family.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.research.signals.base import PanelSignal, register_signal


def rolling_hedge_ratio(
    log_a: pd.Series, log_b: pd.Series, window: int, refit_every: int
) -> pd.Series:
    """OLS beta of log_a on log_b over a trailing window, refit periodically.

    The ratio used at bar t was estimated from bars (t-window, t-1] at the
    most recent refit — strictly causal.
    """
    n = len(log_a)
    beta = np.full(n, np.nan)
    a = log_a.to_numpy(dtype=float)
    b = log_b.to_numpy(dtype=float)
    last = np.nan
    for t in range(window, n):
        if (t - window) % refit_every == 0 or np.isnan(last):
            ya = a[t - window : t]
            xb = b[t - window : t]
            varb = xb.var()
            if varb > 1e-18:
                last = float(np.cov(ya, xb, ddof=0)[0, 1] / varb)
        beta[t] = last
    return pd.Series(beta, index=log_a.index)


def engle_granger_pvalue(log_a: pd.Series, log_b: pd.Series) -> float:
    """ADF p-value of the OLS spread residual (Engle-Granger step 2).

    Used by discovery to PRE-SELECT candidate pairs on the TRAINING sample
    only.  Uses statsmodels when available; otherwise returns NaN and the
    pair-selection falls back to correlation ranking.
    """
    try:
        from statsmodels.tsa.stattools import adfuller
    except ImportError:  # pragma: no cover
        return float("nan")
    a, b = log_a.dropna(), log_b.dropna()
    idx = a.index.intersection(b.index)
    if len(idx) < 100:
        return float("nan")
    a, b = a.loc[idx], b.loc[idx]
    beta = float(np.cov(a, b, ddof=0)[0, 1] / b.var())
    resid = a - beta * b
    try:
        return float(adfuller(resid, regression="c", autolag="AIC")[1])
    except Exception:  # pragma: no cover - numerical failures
        return float("nan")


@register_signal
class CointegrationPairSignal(PanelSignal):
    name = "coint_pair"
    family = "stat_arb"
    default_params = {
        "window": 500,         # hedge-ratio estimation window
        "refit_every": 100,    # bars between refits
        "z_window": 100,       # spread z-score window
        "entry_z": 2.0,
        "exit_z": 0.5,
        "stop_z": 4.0,         # structural-break stop
    }
    grid = {"entry_z": [1.5, 2.0, 2.5], "z_window": [50, 100, 200]}
    thesis = (
        "If two assets share a common stochastic factor, their hedged spread "
        "is stationary; deviations are liquidity noise that mean-reverts.  "
        "Classic pairs trading (Gatev, Goetzmann & Rouwenhorst 2006)."
    )
    persistence = (
        "Idiosyncratic flow hits one leg at a time (single-name listings, "
        "unlocks, narratives), perpetually recreating spread dislocations."
    )
    risks = (
        "Cointegration breaks are silent and expensive: the stop_z exit is "
        "load-bearing.  Shorting the strong leg in a narrative rotation is "
        "the canonical stat-arb death."
    )

    def generate_panel(self, panel: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        p = self.params
        symbols = sorted(panel)
        if len(symbols) != 2:
            raise ValueError("coint_pair expects exactly 2 symbols")
        sa, sb = symbols
        idx = panel[sa].index.intersection(panel[sb].index)
        la = np.log(panel[sa]["close"].reindex(idx))
        lb = np.log(panel[sb]["close"].reindex(idx))

        beta = rolling_hedge_ratio(la, lb, int(p["window"]), int(p["refit_every"]))
        spread = la - beta * lb
        mean = spread.rolling(int(p["z_window"])).mean()
        std = spread.rolling(int(p["z_window"])).std(ddof=0)
        z = (spread - mean) / std.replace(0.0, np.nan)

        entry, exit_, stop = float(p["entry_z"]), float(p["exit_z"]), float(p["stop_z"])
        zv = z.to_numpy()
        n = len(idx)
        state = 0  # +1: long spread (long a, short b); -1: short spread
        pos_a = np.zeros(n)
        for i in range(n):
            zi = zv[i]
            if not np.isfinite(zi):
                state = 0
            elif state == 0:
                if zi < -entry:
                    state = 1
                elif zi > entry:
                    state = -1
            elif state == 1 and (zi > -exit_ or zi < -stop):
                state = 0       # converged, or structurally broken
            elif state == -1 and (zi < exit_ or zi > stop):
                state = 0
            pos_a[i] = state

        pa = pd.Series(pos_a, index=idx)
        # Dollar-neutral legs, each capped at 1x of its capital slice.
        pb = (-pa * beta).clip(-1.0, 1.0).fillna(0.0)
        return {
            sa: pa.reindex(panel[sa].index).fillna(0.0),
            sb: pb.reindex(panel[sb].index).fillna(0.0),
        }


@register_signal
class RelativeValueSignal(PanelSignal):
    name = "relative_value"
    family = "stat_arb"
    default_params = {"z_window": 200, "entry_z": 2.0, "exit_z": 0.5}
    grid = {"z_window": [100, 200, 400], "entry_z": [1.5, 2.0, 2.5]}
    thesis = (
        "The log price *ratio* of two majors oscillates inside narrative "
        "epochs; fading ratio extremes vs a trailing window monetises "
        "rotation overshoot without needing formal cointegration."
    )
    persistence = "Rotation flows between majors overshoot persistently (relative FOMO)."
    risks = "Epoch changes (one asset structurally re-rates) look exactly like an entry."

    def generate_panel(self, panel: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        p = self.params
        symbols = sorted(panel)
        if len(symbols) != 2:
            raise ValueError("relative_value expects exactly 2 symbols")
        sa, sb = symbols
        idx = panel[sa].index.intersection(panel[sb].index)
        ratio = np.log(panel[sa]["close"].reindex(idx)) - np.log(panel[sb]["close"].reindex(idx))
        mean = ratio.rolling(int(p["z_window"])).mean()
        std = ratio.rolling(int(p["z_window"])).std(ddof=0)
        z = ((ratio - mean) / std.replace(0.0, np.nan))

        from quantbot.research.signals.base import hysteresis_positions

        e, x = float(p["entry_z"]), float(p["exit_z"])
        pa = hysteresis_positions(
            enter_long=z < -e, exit_long=z > -x, enter_short=z > e, exit_short=z < x
        )
        return {
            sa: pa.reindex(panel[sa].index).fillna(0.0),
            sb: (-pa).reindex(panel[sb].index).fillna(0.0),
        }


@register_signal
class CorrelationBreakdownSignal(PanelSignal):
    name = "corr_breakdown"
    family = "stat_arb"
    default_params = {"corr_window": 100, "ref_window": 500, "corr_q": 0.10, "lookback": 48, "hold": 48}
    grid = {"corr_window": [50, 100], "corr_q": [0.05, 0.10, 0.20]}
    thesis = (
        "Major crypto pairs are structurally one-factor; when their rolling "
        "correlation collapses vs its own history, one leg has been moved by "
        "idiosyncratic flow.  Betting on re-correlation (long laggard, short "
        "leader) harvests the reversal of that flow."
    )
    persistence = "Factor structure reasserts because the holder base overlaps."
    risks = "Sometimes decorrelation IS the news (delisting, hack) — re-correlation never comes."

    def generate_panel(self, panel: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        p = self.params
        symbols = sorted(panel)
        if len(symbols) != 2:
            raise ValueError("corr_breakdown expects exactly 2 symbols")
        sa, sb = symbols
        idx = panel[sa].index.intersection(panel[sb].index)
        ra = panel[sa]["close"].reindex(idx).pct_change()
        rb = panel[sb]["close"].reindex(idx).pct_change()

        corr = ra.rolling(int(p["corr_window"])).corr(rb)
        broke = corr.rolling(int(p["ref_window"])).rank(pct=True) < float(p["corr_q"])

        look = int(p["lookback"])
        perf_gap = (
            panel[sa]["close"].reindex(idx).pct_change(look)
            - panel[sb]["close"].reindex(idx).pct_change(look)
        )
        # a outperformed → a is leader → short a, long b (and vice versa).
        pa = pd.Series(0.0, index=idx)
        pa[broke & (perf_gap > 0)] = -1.0
        pa[broke & (perf_gap < 0)] = 1.0
        pa = pa.replace(0.0, np.nan).ffill(limit=int(p["hold"])).fillna(0.0)
        return {
            sa: pa.reindex(panel[sa].index).fillna(0.0),
            sb: (-pa).reindex(panel[sb].index).fillna(0.0),
        }
