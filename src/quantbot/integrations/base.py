"""Common trading-venue interface.

Every venue (Hyperliquid, Bullpen, the paper broker) implements ``TradingVenue``
so the execution engine is venue-agnostic.  Domain objects are plain dataclasses
to avoid coupling to any venue's wire format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class BrokerError(Exception):
    """Raised for venue-side failures (auth, rejected order, network)."""


@dataclass
class Order:
    client_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    qty: float
    limit_price: float | None = None
    status: OrderStatus = OrderStatus.NEW
    venue_order_id: str | None = None
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    fee: float = 0.0
    reason: str | None = None
    strategy_name: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Position:
    symbol: str
    qty: float                 # signed
    avg_price: float
    unrealized_pnl: float = 0.0
    venue: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Balance:
    currency: str
    free: float
    total: float


@dataclass
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class TradingVenue(ABC):
    """Abstract trading venue."""

    name: str = "base"

    # -- lifecycle ----------------------------------------------------------
    @abstractmethod
    def authenticate(self) -> None:
        """Establish/verify credentials.  Raise BrokerError on failure."""

    def close(self) -> None:  # pragma: no cover - optional override
        pass

    # -- market data --------------------------------------------------------
    @abstractmethod
    def get_ticker(self, symbol: str) -> float:
        """Return the latest price for ``symbol``."""

    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        ...

    # -- trading ------------------------------------------------------------
    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit and return the order updated with venue id / status."""

    @abstractmethod
    def cancel_order(self, venue_order_id: str, symbol: str | None = None) -> bool:
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    def get_balances(self) -> list[Balance]:
        ...

    @abstractmethod
    def get_trade_history(self, symbol: str | None = None, limit: int = 100) -> list[dict]:
        ...
