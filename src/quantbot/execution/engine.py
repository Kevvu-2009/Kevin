"""Live/paper trading engine.

Orchestrates: market data -> strategy signal -> risk checks -> sizing -> order.
Designed to be driven bar-by-bar (``on_bar``) by a market-data loop, so the same
engine works for backtest-replay, paper trading and live trading by swapping the
``TradingVenue``.

Per symbol it maintains at most one long position (matching the strategy
library).  Every entry must pass the ``PortfolioRiskManager`` gate; stops and
exit signals are honoured on each new bar.  All decisions are logged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from quantbot.config import Settings, get_settings
from quantbot.execution.order_manager import OrderManager
from quantbot.execution.state import EngineState, StateStore
from quantbot.integrations.base import Order, OrderSide, OrderType, TradingVenue
from quantbot.logging_setup import get_logger, log_risk, log_signal, log_strategy
from quantbot.risk.portfolio import PortfolioRiskManager
from quantbot.risk.position_sizing import fixed_fractional_size
from quantbot.strategies.base import Strategy

log = get_logger("execution.engine")


@dataclass
class TrackedPosition:
    symbol: str
    qty: float
    entry_price: float
    stop_price: float
    strategy_name: str
    take_profit: float = float("nan")
    trail: bool = True
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LiveEngine:
    def __init__(
        self,
        venue: TradingVenue,
        strategies: dict[str, Strategy],
        settings: Settings | None = None,
        starting_equity: float = 10_000.0,
        state_store: StateStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.venue = venue
        self.om = OrderManager(venue)
        self.strategies = strategies                 # symbol -> Strategy
        self.risk = PortfolioRiskManager(self.settings.risk, starting_equity)
        self.positions: dict[str, TrackedPosition] = {}
        self.state_store = state_store
        self._equity = starting_equity

    # ---------------------------------------------------------------- public
    def on_bar(self, symbol: str, df: pd.DataFrame) -> None:
        """Process a freshly-closed bar for ``symbol`` given its OHLCV history."""
        strat = self.strategies.get(symbol)
        if strat is None or len(df) < 5:
            return

        last_price = float(df["close"].iloc[-1])
        # Keep paper-broker price feed current.
        if hasattr(self.venue, "set_price"):
            self.venue.set_price(symbol, last_price)

        self._mark_to_market(symbol, last_price)

        sig = strat.generate(df)
        i = -1
        entry = bool(sig.entries.iloc[i])
        exit_ = bool(sig.exits.iloc[i])
        stop = float(sig.stop.iloc[i]) if not np.isnan(sig.stop.iloc[i]) else np.nan
        tp = (
            float(sig.take_profit.iloc[i])
            if sig.take_profit is not None and not np.isnan(sig.take_profit.iloc[i])
            else np.nan
        )

        log_signal(log, symbol=symbol, strategy=strat.name, price=last_price,
                   entry=entry, exit=exit_, stop=None if np.isnan(stop) else stop)

        pos = self.positions.get(symbol)

        # 1) Manage open position: stop / take-profit / exit signal.
        if pos is not None:
            # Ratchet a trailing stop up (skip for fixed-stop strategies).
            if pos.trail and not np.isnan(stop):
                pos.stop_price = max(pos.stop_price, stop) if pos.stop_price else stop
            if pos.stop_price and last_price <= pos.stop_price:
                self._close(symbol, last_price, reason="stop")
                return
            if not np.isnan(pos.take_profit) and last_price >= pos.take_profit:
                self._close(symbol, last_price, reason="take_profit")
                return
            if exit_:
                self._close(symbol, last_price, reason="signal")
                return

        # 2) Consider a new entry.
        if pos is None and entry:
            self._try_open(symbol, strat.name, last_price, stop, tp, sig.trail)

        self._persist()

    def flatten_all(self, reason: str = "manual") -> None:
        for symbol in list(self.positions):
            price = self.venue.get_ticker(symbol)
            self._close(symbol, price, reason=reason)

    # ---------------------------------------------------------------- private
    def _try_open(self, symbol: str, strat_name: str, price: float, stop: float,
                  take_profit: float = float("nan"), trail: bool = True) -> None:
        self.risk.set_open_positions(len(self.positions))
        self.risk.update_equity(self._equity)
        decision = self.risk.can_open()
        if not decision.allowed:
            log_risk(log, symbol=symbol, action="entry_blocked", reason=decision.reason)
            if decision.reason.startswith("kill_switch"):
                self.flatten_all(reason="kill_switch")
            return

        stop_price = stop if not np.isnan(stop) else price * 0.95  # 5% safety stop
        sizing = fixed_fractional_size(
            equity=self._equity,
            entry_price=price,
            stop_price=stop_price,
            risk_per_trade=self.settings.risk.risk_per_trade,
        )
        if sizing.qty <= 0:
            return

        order = Order(
            client_id=self.om.new_client_id(),
            symbol=symbol,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=sizing.qty,
            strategy_name=strat_name,
        )
        result = self.om.submit(order)
        if result.status.value == "filled":
            self.positions[symbol] = TrackedPosition(
                symbol=symbol, qty=result.filled_qty,
                entry_price=result.avg_fill_price, stop_price=stop_price,
                strategy_name=strat_name, take_profit=take_profit, trail=trail,
            )
            log_strategy(log, symbol=symbol, action="opened", qty=result.filled_qty,
                         price=result.avg_fill_price, stop=stop_price, risk_cash=sizing.risk_cash)

    def _close(self, symbol: str, price: float, reason: str) -> None:
        pos = self.positions.get(symbol)
        if pos is None:
            return
        order = Order(
            client_id=self.om.new_client_id(),
            symbol=symbol,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            qty=pos.qty,
            strategy_name=pos.strategy_name,
            reason=reason,
        )
        result = self.om.submit(order)
        if result.status.value == "filled":
            pnl = (result.avg_fill_price - pos.entry_price) * pos.qty
            log_strategy(log, symbol=symbol, action="closed", reason=reason,
                         price=result.avg_fill_price, pnl=pnl)
            del self.positions[symbol]
            self._mark_to_market(symbol, price)

    def _mark_to_market(self, symbol: str, price: float) -> None:
        if hasattr(self.venue, "equity"):
            self._equity = self.venue.equity()
        else:
            balances = self.venue.get_balances()
            quote = next((b.total for b in balances), self._equity)
            self._equity = quote
        self.risk.update_equity(self._equity)

    def _persist(self) -> None:
        if self.state_store is None:
            return
        st = EngineState(
            mode=self.settings.mode,
            equity=self._equity,
            peak_equity=self.risk.state.peak_equity,
            open_positions={
                s: {"qty": p.qty, "entry": p.entry_price, "stop": p.stop_price,
                    "strategy": p.strategy_name}
                for s, p in self.positions.items()
            },
            kill_switch_active=self.risk.state.kill_switch_active,
        )
        try:
            self.state_store.save(st)
        except Exception as e:  # pragma: no cover
            log.warning("state_persist_failed", error=str(e))

    @property
    def equity(self) -> float:
        return self._equity
