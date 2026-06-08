"""In-memory paper-trading broker.

A fully-functional ``TradingVenue`` that simulates fills with the same cost
model as the backtester (taker fee + slippage), so paper results are comparable
to backtests.  It needs an external price source: call ``set_price`` from the
live engine's market-data loop before submitting orders, or pass a price feed.

State is intentionally simple and serialisable so it can be snapshotted to Redis
between restarts.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from quantbot.config import CostConfig
from quantbot.integrations.base import (
    Balance,
    BrokerError,
    Candle,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TradingVenue,
)


class PaperBroker(TradingVenue):
    name = "paper"

    def __init__(
        self,
        starting_cash: float = 10_000.0,
        quote_ccy: str = "USDT",
        costs: CostConfig | None = None,
    ) -> None:
        self.costs = costs or CostConfig()
        self.quote_ccy = quote_ccy
        self.cash = float(starting_cash)
        self.prices: dict[str, float] = {}
        self._positions: dict[str, Position] = {}
        self._orders: list[Order] = []
        self._fills: list[dict] = []
        self._realized: dict[str, float] = defaultdict(float)

    # ---- price feed --------------------------------------------------------
    def set_price(self, symbol: str, price: float) -> None:
        self.prices[symbol] = float(price)

    def _price(self, symbol: str) -> float:
        if symbol not in self.prices:
            raise BrokerError(f"no paper price for {symbol}; call set_price first")
        return self.prices[symbol]

    # ---- TradingVenue ------------------------------------------------------
    def authenticate(self) -> None:
        return None

    def get_ticker(self, symbol: str) -> float:
        return self._price(symbol)

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        return []

    def submit_order(self, order: Order) -> Order:
        price = order.limit_price if order.type == OrderType.LIMIT and order.limit_price else self._price(order.symbol)
        slip = self.costs.slippage_bps / 1e4
        fill_price = price * (1 + slip) if order.side == OrderSide.BUY else price * (1 - slip)
        notional = order.qty * fill_price
        fee = notional * self.costs.taker_fee

        if order.side == OrderSide.BUY:
            if notional + fee > self.cash + 1e-9:
                order.status = OrderStatus.REJECTED
                order.reason = "insufficient_cash"
                self._orders.append(order)
                return order
            self.cash -= notional + fee
            self._apply_fill(order.symbol, order.qty, fill_price)
        else:  # SELL
            pos = self._positions.get(order.symbol)
            held = pos.qty if pos else 0.0
            qty = min(order.qty, held)
            if qty <= 0:
                order.status = OrderStatus.REJECTED
                order.reason = "no_position"
                self._orders.append(order)
                return order
            self.cash += qty * fill_price - qty * fill_price * self.costs.taker_fee
            self._apply_fill(order.symbol, -qty, fill_price)

        order.status = OrderStatus.FILLED
        order.filled_qty = order.qty
        order.avg_fill_price = fill_price
        order.fee = fee
        order.venue_order_id = uuid.uuid4().hex
        self._orders.append(order)
        self._fills.append(
            {
                "symbol": order.symbol,
                "side": order.side.value,
                "qty": order.filled_qty,
                "price": fill_price,
                "fee": fee,
                "ts": datetime.now(timezone.utc),
            }
        )
        return order

    def _apply_fill(self, symbol: str, signed_qty: float, price: float) -> None:
        pos = self._positions.get(symbol)
        if pos is None:
            self._positions[symbol] = Position(symbol=symbol, qty=signed_qty, avg_price=price, venue=self.name)
            return
        new_qty = pos.qty + signed_qty
        if pos.qty > 0 and signed_qty < 0:  # reducing/closing a long
            self._realized[symbol] += (price - pos.avg_price) * min(-signed_qty, pos.qty)
        if abs(new_qty) < 1e-12:
            del self._positions[symbol]
            return
        if (pos.qty >= 0 and signed_qty > 0) or (pos.qty <= 0 and signed_qty < 0):
            # adding in same direction → weighted avg
            pos.avg_price = (pos.avg_price * pos.qty + price * signed_qty) / new_qty
        pos.qty = new_qty

    def cancel_order(self, venue_order_id: str, symbol: str | None = None) -> bool:
        return True  # paper orders fill immediately; nothing to cancel

    def get_positions(self) -> list[Position]:
        out = []
        for p in self._positions.values():
            px = self.prices.get(p.symbol, p.avg_price)
            p.unrealized_pnl = (px - p.avg_price) * p.qty
            out.append(p)
        return out

    def get_balances(self) -> list[Balance]:
        return [Balance(currency=self.quote_ccy, free=self.cash, total=self.equity())]

    def get_trade_history(self, symbol: str | None = None, limit: int = 100) -> list[dict]:
        fills = [f for f in self._fills if symbol is None or f["symbol"] == symbol]
        return fills[-limit:]

    # ---- helpers -----------------------------------------------------------
    def equity(self) -> float:
        mtm = sum(
            p.qty * self.prices.get(p.symbol, p.avg_price) for p in self._positions.values()
        )
        return self.cash + mtm
