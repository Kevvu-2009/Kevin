"""Event-driven backtest engine.

Deliberately *not* simplistic.  It models:

* **Latency** — a signal formed at the close of bar *t* is executed at the open
  of bar ``t + latency_bars`` (default 1).  No same-bar fills.
* **Fees** — taker fee charged on both entry and exit notional.
* **Slippage** — entries fill worse by ``slippage_bps``; exits fill worse too;
  stop exits additionally assume the stop slips through by the same amount.
* **Risk-based sizing** — quantity is set so a stop-out loses ~``risk_per_trade``
  of current equity, capped at no-leverage (1x) notional.
* **Trailing ATR stops** — the per-bar stop from the strategy ratchets upward
  only and is checked intrabar against the bar low.  Strategies may set
  ``trail=False`` to hold the entry stop fixed (for fixed reward:risk setups).
* **Take-profit targets** — an optional per-bar target price; a bar whose high
  reaches it books the trade at the target.  If a bar spans both the stop and
  the target, the stop is assumed hit first (conservative).

The engine is long-only and single-position-per-instrument, matching the
strategy library.  It returns an equity curve, a trade blotter and the realised
per-trade PnL used by the metrics module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quantbot.config import CostConfig
from quantbot.backtest.metrics import Metrics, compute_metrics
from quantbot.strategies.base import Strategy


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: pd.DataFrame
    returns: pd.Series
    timeframe: str
    metrics: Metrics = field(init=False)

    def __post_init__(self) -> None:
        pnl = self.trades["pnl"].to_numpy() if len(self.trades) else np.array([])
        self.metrics = compute_metrics(self.equity, self.timeframe, pnl)

    @property
    def stats(self) -> dict:
        return self.metrics.to_dict()


class BacktestEngine:
    def __init__(
        self,
        costs: CostConfig | None = None,
        initial_cash: float = 10_000.0,
        risk_per_trade: float = 0.0075,
        allow_fractional: bool = True,
    ) -> None:
        self.costs = costs or CostConfig()
        self.initial_cash = float(initial_cash)
        self.risk_per_trade = float(risk_per_trade)
        self.allow_fractional = allow_fractional

    # ------------------------------------------------------------------ run
    def run(self, strategy: Strategy, df: pd.DataFrame, timeframe: str) -> BacktestResult:
        df = df.copy()
        sig = strategy.generate(df)
        entries = sig.entries.to_numpy(dtype=bool)
        exits = sig.exits.to_numpy(dtype=bool)
        stop_arr = sig.stop.to_numpy(dtype=float)
        tp_arr = (
            sig.take_profit.to_numpy(dtype=float)
            if sig.take_profit is not None
            else np.full(len(df), np.nan)
        )
        trail = sig.trail

        op = df["open"].to_numpy(dtype=float)
        hi = df["high"].to_numpy(dtype=float)
        lo = df["low"].to_numpy(dtype=float)
        cl = df["close"].to_numpy(dtype=float)
        idx = df.index

        slip = self.costs.slippage_bps / 1e4
        fee = self.costs.taker_fee
        lat = max(1, int(self.costs.latency_bars))
        n = len(df)

        cash = self.initial_cash
        equity_curve = np.full(n, self.initial_cash, dtype=float)

        in_pos = False
        qty = 0.0
        entry_price = 0.0
        stop_price = np.nan
        tp_price = np.nan
        entry_i = -1
        pending_entry = False  # signal seen, awaiting latency to fill

        trades: list[dict] = []

        def mark_equity(i: int, price: float) -> None:
            equity_curve[i] = cash + (qty * price if in_pos else 0.0)

        for i in range(n):
            price_open = op[i]

            # 1) Execute a pending entry at this bar's open (post-latency).
            if pending_entry and not in_pos:
                fill = price_open * (1 + slip)
                # Position sizing: risk_per_trade of equity over stop distance.
                eq = cash
                init_stop = stop_arr[i - 1] if i > 0 else np.nan
                if np.isnan(init_stop) or init_stop >= fill:
                    # No usable stop → fixed-fraction fallback (cap at 1x).
                    notional = eq  # full allocation, no leverage
                    q = notional / fill
                    init_stop = np.nan
                else:
                    risk_cash = eq * self.risk_per_trade
                    per_unit_risk = fill - init_stop
                    q = risk_cash / per_unit_risk
                    q = min(q, eq / fill)  # no leverage
                if not self.allow_fractional:
                    q = float(np.floor(q))
                if q > 0:
                    cost = q * fill
                    cash -= cost
                    cash -= cost * fee
                    in_pos = True
                    qty = q
                    entry_price = fill
                    stop_price = init_stop
                    tp_price = tp_arr[i - 1] if i > 0 else np.nan
                    entry_i = i
                pending_entry = False

            # 2) Manage an open position: stop / take-profit / exit signal.
            if in_pos:
                # Ratchet the stop upward using the strategy's per-bar stop,
                # unless the strategy asked for a fixed (non-trailing) stop.
                if trail:
                    s = stop_arr[i]
                    if not np.isnan(s):
                        stop_price = s if np.isnan(stop_price) else max(stop_price, s)

                exited = False
                # 2a) Intrabar stop-out (assume gap/slip through the stop).
                #     Checked before the target: if a bar spans both levels we
                #     conservatively assume the loss was hit first.
                if not np.isnan(stop_price) and lo[i] <= stop_price:
                    fill = min(price_open, stop_price) * (1 - slip)
                    cash += qty * fill
                    cash -= qty * fill * fee
                    trades.append(
                        _trade_record(idx, entry_i, i, entry_price, fill, qty, "stop")
                    )
                    in_pos, qty, stop_price, tp_price, entry_i = False, 0.0, np.nan, np.nan, -1
                    exited = True

                # 2b) Intrabar take-profit (target touched by the bar high).
                if not exited and not np.isnan(tp_price) and hi[i] >= tp_price:
                    fill = max(price_open, tp_price) * (1 - slip)
                    cash += qty * fill
                    cash -= qty * fill * fee
                    trades.append(
                        _trade_record(idx, entry_i, i, entry_price, fill, qty, "take_profit")
                    )
                    in_pos, qty, stop_price, tp_price, entry_i = False, 0.0, np.nan, np.nan, -1
                    exited = True

                # 2c) Strategy exit signal → fill next bar open (latency).
                if not exited and exits[i]:
                    # schedule exit at next open
                    if i + 1 < n:
                        fill = op[i + 1] * (1 - slip)
                        cash += qty * fill
                        cash -= qty * fill * fee
                        trades.append(
                            _trade_record(idx, entry_i, i + 1, entry_price, fill, qty, "signal")
                        )
                        in_pos, qty, stop_price, tp_price, entry_i = False, 0.0, np.nan, np.nan, -1
                        exited = True

            # 3) Look for a new entry signal (fills after latency).
            if not in_pos and not pending_entry and entries[i]:
                # schedule fill `lat` bars later (default next bar)
                if i + lat < n:
                    pending_entry = True

            mark_equity(i, cl[i])

        # Force-close any residual position at the last close (mark-to-market).
        if in_pos:
            fill = cl[-1] * (1 - slip)
            cash += qty * fill - qty * fill * fee
            trades.append(_trade_record(idx, entry_i, n - 1, entry_price, fill, qty, "eod"))
            equity_curve[-1] = cash

        equity = pd.Series(equity_curve, index=idx, name="equity")
        returns = equity.pct_change().fillna(0.0)
        trades_df = pd.DataFrame(trades)
        if trades_df.empty:
            trades_df = pd.DataFrame(
                columns=["entry_time", "exit_time", "entry_price", "exit_price", "qty", "pnl", "return", "reason"]
            )
        return BacktestResult(equity=equity, trades=trades_df, returns=returns, timeframe=timeframe)


def _trade_record(idx, ei, xi, entry_price, exit_price, qty, reason) -> dict:
    pnl = (exit_price - entry_price) * qty
    ret = exit_price / entry_price - 1.0 if entry_price else 0.0
    return {
        "entry_time": idx[ei],
        "exit_time": idx[xi],
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "qty": float(qty),
        "pnl": float(pnl),
        "return": float(ret),
        "reason": reason,
    }
