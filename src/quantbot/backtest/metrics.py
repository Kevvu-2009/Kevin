"""Performance & risk metrics.

All metrics are computed from a strategy equity curve (and optional trade-level
PnL).  Annualisation uses the bar frequency, so the same code is correct for 5m
through 1d.  Crypto trades 24/7, hence 365 days/year.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

# Bars per year for each supported timeframe (24/7 markets).
_BARS_PER_YEAR = {
    "5m": 365 * 24 * 12,
    "15m": 365 * 24 * 4,
    "1h": 365 * 24,
    "4h": 365 * 6,
    "1d": 365,
}


def bars_per_year(timeframe: str) -> float:
    return float(_BARS_PER_YEAR.get(timeframe, 365))


@dataclass
class Metrics:
    cagr: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    volatility: float
    total_return: float
    win_rate: float
    profit_factor: float
    avg_trade: float
    expectancy: float
    n_trades: int

    def to_dict(self) -> dict:
        return asdict(self)


def _annualisation(timeframe: str) -> float:
    return bars_per_year(timeframe)


def drawdown_series(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return equity / peak - 1.0


def max_drawdown(equity: pd.Series) -> float:
    if len(equity) == 0:
        return 0.0
    return float(drawdown_series(equity).min())


def cagr(equity: pd.Series, timeframe: str) -> float:
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    n_bars = len(equity) - 1
    years = n_bars / _annualisation(timeframe)
    if years <= 0:
        return 0.0
    growth = equity.iloc[-1] / equity.iloc[0]
    if growth <= 0:
        return -1.0
    return float(growth ** (1.0 / years) - 1.0)


def sharpe(returns: pd.Series, timeframe: str, rf: float = 0.0) -> float:
    r = returns.dropna()
    if r.std(ddof=0) == 0 or len(r) < 2:
        return 0.0
    ann = _annualisation(timeframe)
    excess = r - rf / ann
    return float(excess.mean() / r.std(ddof=0) * np.sqrt(ann))


def sortino(returns: pd.Series, timeframe: str, rf: float = 0.0) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    ann = _annualisation(timeframe)
    excess = r - rf / ann
    downside = r[r < 0]
    dd = downside.std(ddof=0)
    if dd == 0 or np.isnan(dd):
        return 0.0
    return float(excess.mean() / dd * np.sqrt(ann))


def calmar(equity: pd.Series, timeframe: str) -> float:
    mdd = abs(max_drawdown(equity))
    if mdd == 0:
        return 0.0
    return float(cagr(equity, timeframe) / mdd)


def trade_stats(trade_pnl: pd.Series | np.ndarray | list) -> dict:
    pnl = np.asarray(trade_pnl, dtype=float)
    n = len(pnl)
    if n == 0:
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_trade": 0.0,
            "expectancy": 0.0,
            "n_trades": 0,
        }
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    win_rate = len(wins) / n
    profit_factor = float(gross_win / gross_loss) if gross_loss > 0 else (
        np.inf if gross_win > 0 else 0.0
    )
    avg_trade = float(pnl.mean())
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    expectancy = float(win_rate * avg_win + (1 - win_rate) * avg_loss)
    return {
        "win_rate": float(win_rate),
        "profit_factor": profit_factor,
        "avg_trade": avg_trade,
        "expectancy": expectancy,
        "n_trades": int(n),
    }


def compute_metrics(
    equity: pd.Series,
    timeframe: str,
    trade_pnl: pd.Series | np.ndarray | list | None = None,
) -> Metrics:
    """Compute the full metric set from an equity curve (+ optional trades)."""
    equity = equity.dropna()
    returns = equity.pct_change().dropna()
    ts = trade_stats(trade_pnl if trade_pnl is not None else [])
    total_return = (
        float(equity.iloc[-1] / equity.iloc[0] - 1.0) if len(equity) >= 2 else 0.0
    )
    ann = _annualisation(timeframe)
    vol = float(returns.std(ddof=0) * np.sqrt(ann)) if len(returns) > 1 else 0.0
    return Metrics(
        cagr=cagr(equity, timeframe),
        sharpe=sharpe(returns, timeframe),
        sortino=sortino(returns, timeframe),
        calmar=calmar(equity, timeframe),
        max_drawdown=max_drawdown(equity),
        volatility=vol,
        total_return=total_return,
        win_rate=ts["win_rate"],
        profit_factor=ts["profit_factor"],
        avg_trade=ts["avg_trade"],
        expectancy=ts["expectancy"],
        n_trades=ts["n_trades"],
    )
