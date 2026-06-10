"""Vectorized, cost-aware research backtester.

Purpose: screen hundreds of (signal × symbol × parameter) candidates orders of
magnitude faster than the event-driven engine, while keeping the execution
assumptions honest.  Survivors are later re-verified on the event engine.

Execution model (no lookahead by construction)
----------------------------------------------
* A position ``pos[t] ∈ [-1, 1]`` is decided using data up to the CLOSE of
  bar ``t`` (the signal's responsibility).
* The trade executes at the OPEN of bar ``t+1`` (engine's responsibility):
  the return earned while holding from open[i] to open[i+1] is attributed to
  the position decided at close of bar ``i-1``.
* Costs are charged on *turnover*: every unit of position change pays
  ``fee + slippage + half-spread``.  Holding costs nothing (perp funding is a
  deliberate omission — see CostModel notes).

An optional ``extra_lag`` adds one more bar of delay; validation re-runs
candidates with it to kill anything that only works with perfect timing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quantbot.backtest.metrics import Metrics, compute_metrics


@dataclass(frozen=True)
class CostModel:
    """Per-side trading costs in basis points of notional.

    Defaults approximate a taker on a major perp venue (Hyperliquid/Binance
    tier-0: 2-5 bps fee) plus conservative impact for retail-size orders in
    BTC/ETH books.  Funding payments are NOT modelled: across long flat
    periods funding on majors has averaged near zero, but strategies holding
    persistent one-sided perp exposure should treat results as optimistic by
    roughly the average funding drag — flagged in the report.
    """

    fee_bps: float = 4.0          # taker fee per side
    slippage_bps: float = 3.0     # expected impact/adverse fill per side
    spread_bps: float = 2.0       # full quoted spread; half is paid per side

    @property
    def cost_per_unit_turnover(self) -> float:
        """Fractional cost charged per unit of |Δposition|."""
        return (self.fee_bps + self.slippage_bps + self.spread_bps / 2.0) / 1e4


@dataclass
class VectorBacktestResult:
    equity: pd.Series          # compounded, starts at 1.0
    returns: pd.Series         # per-bar net strategy returns
    positions: pd.Series       # executed position (post-lag)
    trades: pd.DataFrame       # segmented round-trips
    timeframe: str
    exposure: float            # fraction of bars with a position on
    annual_turnover: float     # sum |Δpos| scaled to a year
    metrics: Metrics = field(init=False)

    def __post_init__(self) -> None:
        pnl = self.trades["return"].to_numpy() if len(self.trades) else np.array([])
        self.metrics = compute_metrics(self.equity, self.timeframe, pnl)

    @property
    def stats(self) -> dict:
        d = self.metrics.to_dict()
        d["exposure"] = self.exposure
        d["annual_turnover"] = self.annual_turnover
        d["recovery_factor"] = (
            abs(d["total_return"] / d["max_drawdown"]) if d["max_drawdown"] < 0 else 0.0
        )
        return d


def _segment_trades(pos: np.ndarray, rets: np.ndarray, index: pd.Index) -> pd.DataFrame:
    """Split the executed position series into round-trip trades.

    A trade is a maximal run of bars with the same position sign.  Its return
    is the compounded strategy return over the run — an approximation (resizes
    within a run are merged) but unbiased for win-rate / profit-factor use.
    """
    sign = np.sign(pos)
    rows = []
    i, n = 0, len(sign)
    while i < n:
        if sign[i] == 0:
            i += 1
            continue
        j = i
        while j + 1 < n and sign[j + 1] == sign[i]:
            j += 1
        ret = float(np.prod(1.0 + rets[i : j + 1]) - 1.0)
        rows.append(
            {
                "entry_time": index[i],
                "exit_time": index[j],
                "direction": int(sign[i]),
                "bars": j - i + 1,
                "return": ret,
                "pnl": ret,  # in equity-fraction units
            }
        )
        i = j + 1
    if not rows:
        return pd.DataFrame(
            columns=["entry_time", "exit_time", "direction", "bars", "return", "pnl"]
        )
    return pd.DataFrame(rows)


def backtest_positions(
    df: pd.DataFrame,
    positions: pd.Series,
    timeframe: str,
    costs: CostModel | None = None,
    extra_lag: int = 0,
) -> VectorBacktestResult:
    """Run the vectorized backtest.

    Args:
        df: OHLCV frame (needs ``open``; ``close`` used for the final mark).
        positions: target exposure in [-1, 1] decided at each bar's close.
        timeframe: bar size, for annualisation.
        costs: cost model (defaults to CostModel()).
        extra_lag: additional execution delay in bars for robustness checks.
    """
    costs = costs or CostModel()
    if not positions.index.equals(df.index):
        positions = positions.reindex(df.index)
    pos = positions.astype(float).clip(-1.0, 1.0).fillna(0.0).to_numpy()

    open_ = df["open"].to_numpy(dtype=float)
    n = len(df)
    if n < 3:
        raise ValueError("need at least 3 bars")

    # Return earned holding from open[i] to open[i+1], attributed to bar i.
    # (The final interval marks to the last close instead of a next open.)
    nxt = np.empty(n)
    nxt[:-1] = open_[1:]
    nxt[-1] = float(df["close"].iloc[-1])
    r_oo = nxt / open_ - 1.0

    lag = 1 + max(0, int(extra_lag))
    active = np.zeros(n)
    active[lag:] = pos[:-lag]                  # pos decided at close t is live over bar t+lag
    prev_active = np.zeros(n)
    prev_active[1:] = active[:-1]
    turnover = np.abs(active - prev_active)    # executed at each bar's open

    strat = active * r_oo - turnover * costs.cost_per_unit_turnover
    equity = pd.Series(np.cumprod(1.0 + strat), index=df.index, name="equity")
    returns = pd.Series(strat, index=df.index, name="returns")

    trades = _segment_trades(active, strat, df.index)
    exposure = float(np.mean(np.abs(active) > 1e-12))
    years = max(n / _bars_per_year(timeframe), 1e-9)
    annual_turnover = float(turnover.sum() / years)

    return VectorBacktestResult(
        equity=equity,
        returns=returns,
        positions=pd.Series(active, index=df.index, name="position"),
        trades=trades,
        timeframe=timeframe,
        exposure=exposure,
        annual_turnover=annual_turnover,
    )


def backtest_panel(
    panel: dict[str, pd.DataFrame],
    positions: dict[str, pd.Series],
    timeframe: str,
    costs: CostModel | None = None,
    extra_lag: int = 0,
) -> VectorBacktestResult:
    """Aggregate a multi-symbol book (each leg ≤ 1x) into one result.

    Legs are combined on the union index with equal capital per *symbol
    provided* (not per active position), so adding symbols dilutes — the same
    convention a fixed-capital book faces.  Costs are charged per leg.
    """
    if not positions:
        raise ValueError("positions dict is empty")
    legs: list[VectorBacktestResult] = []
    for sym, pos in positions.items():
        legs.append(backtest_positions(panel[sym], pos, timeframe, costs, extra_lag))

    union = legs[0].returns.index
    for leg in legs[1:]:
        union = union.union(leg.returns.index)
    k = len(legs)
    rets = sum(leg.returns.reindex(union).fillna(0.0) for leg in legs) / k
    net_pos = sum(leg.positions.reindex(union).fillna(0.0).abs() for leg in legs) / k

    equity = (1.0 + rets).cumprod()
    trades = pd.concat([leg.trades for leg in legs], ignore_index=True)
    if len(trades):
        trades = trades.sort_values("entry_time").reset_index(drop=True)
        trades[["return", "pnl"]] = trades[["return", "pnl"]] / k
    exposure = float((net_pos > 1e-12).mean())
    years = max(len(union) / _bars_per_year(timeframe), 1e-9)
    annual_turnover = float(np.mean([leg.annual_turnover for leg in legs]))

    out = VectorBacktestResult(
        equity=equity,
        returns=rets,
        positions=net_pos,
        trades=trades,
        timeframe=timeframe,
        exposure=exposure,
        annual_turnover=annual_turnover,
    )
    return out


def _bars_per_year(timeframe: str) -> float:
    from quantbot.backtest.metrics import bars_per_year

    return bars_per_year(timeframe)
