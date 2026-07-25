"""Exchange access layer.

Provides two interchangeable implementations of ``ExchangeAPI``:

* ``ExchangeClient`` - Bybit USDT perpetuals over ccxt, with retry/backoff and
  explicit error classification.
* ``PaperExchange``  - a deterministic in-memory simulator. Used for ``DRY_RUN``
  mode in production and as the mocked exchange in the test suite, so the same
  code path is exercised in both.

Every network call goes through ``_call``, which classifies exceptions into
*retryable* (network blips, rate limits, venue maintenance) and *fatal*
(insufficient funds, invalid order, bad auth). Retrying a fatal error just burns
rate limit; retrying a network error is usually the difference between a
protected position and an unprotected one.

Order idempotency at the exchange
---------------------------------
Every order carries a ``clientOrderId`` derived deterministically from the
signal id. If a create_order call times out on the network but actually landed,
the retry is rejected by the venue as a duplicate id instead of opening a second
position. This is the mechanism that makes the retry loop safe to use on writes.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import Mode, Settings
from .sizing import MarketSpec, round_to_step

log = logging.getLogger(__name__)

try:
    import ccxt.async_support as ccxt

    CCXT_AVAILABLE = True
except ImportError:  # pragma: no cover - PaperExchange and tests do not need it
    ccxt = None  # type: ignore[assignment]
    CCXT_AVAILABLE = False


class ExchangeCallFailed(RuntimeError):
    """Raised when a call exhausted its retries."""


class FatalExchangeError(RuntimeError):
    """Raised for errors where retrying cannot help (bad order, no funds)."""


# Bybit orderLinkId is limited to 36 characters.
MAX_CLIENT_ORDER_ID = 36


def make_client_order_id(prefix: str, signal_id: str, nonce: int = 0) -> str:
    """Deterministic, collision-resistant, and short enough for Bybit.

    Deterministic matters: a network-timed-out create followed by a retry must
    present the *same* id so the venue can reject the duplicate.
    """
    digest = hashlib.sha1(signal_id.encode("utf-8")).hexdigest()[:20]
    suffix = f"-{nonce}" if nonce else ""
    return f"{prefix}-{digest}{suffix}"[:MAX_CLIENT_ORDER_ID]


@dataclass
class OrderState:
    """Normalised order, insulating the app from ccxt/venue dict shapes."""

    id: str
    symbol: str
    side: str
    type: str
    status: str  # open | closed | canceled | rejected | expired
    amount: float
    filled: float = 0.0
    average: float | None = None
    price: float | None = None
    trigger_price: float | None = None
    reduce_only: bool = False
    client_order_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def remaining(self) -> float:
        return max(0.0, self.amount - self.filled)

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    @property
    def is_fully_filled(self) -> bool:
        return self.status == "closed" and self.filled >= self.amount - 1e-12

    @property
    def is_dead(self) -> bool:
        """Terminal and not going to fill any further."""
        return self.status in ("canceled", "rejected", "expired")


@dataclass
class PositionState:
    symbol: str
    side: str  # long | short
    qty: float
    entry_price: float
    unrealized_pnl: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


class ExchangeAPI(Protocol):
    """The surface the engine and reconciler depend on."""

    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def market_spec(self, symbol: str) -> MarketSpec: ...
    async def fetch_equity(self) -> float: ...
    async def fetch_mark_price(self, symbol: str) -> float: ...
    async def prepare_symbol(self, symbol: str, leverage: float) -> None: ...
    async def create_entry_limit(
        self, symbol: str, side: str, qty: float, price: float, client_order_id: str
    ) -> OrderState: ...
    async def create_stop_market(
        self,
        symbol: str,
        position_side: str,
        qty: float,
        trigger_price: float,
        client_order_id: str,
    ) -> OrderState: ...
    async def create_tp_limit(
        self,
        symbol: str,
        position_side: str,
        qty: float,
        price: float,
        client_order_id: str,
    ) -> OrderState: ...
    async def fetch_order(self, order_id: str, symbol: str) -> OrderState: ...
    async def cancel_order(self, order_id: str, symbol: str) -> bool: ...
    async def fetch_open_orders(self, symbol: str) -> list[OrderState]: ...
    async def fetch_position(self, symbol: str) -> PositionState | None: ...


# ---------------------------------------------------------------------------
# ccxt implementation
# ---------------------------------------------------------------------------
class ExchangeClient:
    """Bybit USDT-perp client. All calls retried and error-classified."""

    def __init__(self, cfg: Settings) -> None:
        if not CCXT_AVAILABLE:  # pragma: no cover
            raise RuntimeError("ccxt is not installed; install it or run in DRY_RUN mode")
        self.cfg = cfg
        self.ex: Any = None

    # -------------------------------------------------------------- lifecycle
    async def open(self) -> None:
        self.ex = ccxt.bybit(
            {
                "apiKey": self.cfg.api_key,
                "secret": self.cfg.api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "swap", "defaultSubType": "linear"},
            }
        )
        if self.cfg.use_testnet:
            self.ex.set_sandbox_mode(True)
            log.info("exchange_sandbox_enabled")
        await self._call("load_markets", self.ex.load_markets)
        log.info("exchange_ready markets=%d testnet=%s", len(self.ex.markets), self.cfg.use_testnet)

    async def close(self) -> None:
        if self.ex is not None:
            try:
                await self.ex.close()
            except Exception as exc:  # noqa: BLE001 - shutdown must not raise
                log.warning("exchange_close_error %s", exc)

    # ------------------------------------------------------------ retry engine
    def _classify(self, exc: Exception) -> str:
        """Return 'fatal', 'rate_limit', or 'retry'."""
        fatal = (
            ccxt.InsufficientFunds,
            ccxt.InvalidOrder,
            ccxt.AuthenticationError,
            ccxt.PermissionDenied,
            ccxt.BadSymbol,
            ccxt.ArgumentsRequired,
        )
        if isinstance(exc, fatal):
            return "fatal"
        if isinstance(exc, (ccxt.RateLimitExceeded, ccxt.DDoSProtection)):
            return "rate_limit"
        if isinstance(
            exc, (ccxt.NetworkError, ccxt.RequestTimeout, ccxt.ExchangeNotAvailable)
        ):
            return "retry"
        # ExchangeError and anything unknown: retry once or twice. A transient
        # venue 500 is common; a genuine logic error will exhaust and surface.
        return "retry"

    async def _call(self, description: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.cfg.retry_attempts):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - classified immediately below
                kind = self._classify(exc)
                last_exc = exc
                if kind == "fatal":
                    log.error(
                        "exchange_call_fatal op=%s err=%s msg=%s",
                        description,
                        type(exc).__name__,
                        exc,
                    )
                    raise FatalExchangeError(f"{description}: {type(exc).__name__}: {exc}") from exc

                if attempt == self.cfg.retry_attempts - 1:
                    break

                base = self.cfg.retry_base_delay_sec * (4.0 if kind == "rate_limit" else 1.0)
                delay = min(base * (2**attempt), self.cfg.retry_max_delay_sec)
                delay *= 0.5 + random.random()  # full-ish jitter, avoids retry convoys
                log.warning(
                    "exchange_call_retry op=%s attempt=%d/%d kind=%s err=%s sleep=%.2fs",
                    description,
                    attempt + 1,
                    self.cfg.retry_attempts,
                    kind,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)

        raise ExchangeCallFailed(
            f"{description} failed after {self.cfg.retry_attempts} attempts: "
            f"{type(last_exc).__name__}: {last_exc}"
        ) from last_exc

    # ----------------------------------------------------------------- markets
    def _step_from_precision(self, value: Any, fallback: float) -> float:
        if value is None:
            return fallback
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return fallback
        if numeric <= 0:
            return fallback
        # ccxt exposes precision either as a tick size (bybit) or as a count of
        # decimal places. Values >= 1 that are whole numbers are decimal places.
        if self.ex is not None and getattr(self.ex, "precisionMode", None) == getattr(
            ccxt, "DECIMAL_PLACES", 2
        ):
            return float(10 ** -int(numeric))
        return numeric

    async def market_spec(self, symbol: str) -> MarketSpec:
        market = self.ex.market(symbol)
        limits = market.get("limits") or {}
        amount_limits = limits.get("amount") or {}
        cost_limits = limits.get("cost") or {}
        precision = market.get("precision") or {}
        return MarketSpec(
            symbol=symbol,
            amount_step=self._step_from_precision(precision.get("amount"), 1e-8),
            amount_min=float(amount_limits.get("min") or 0.0),
            price_step=self._step_from_precision(precision.get("price"), 1e-8),
            min_notional=float(cost_limits.get("min") or 0.0),
            max_amount=float(amount_limits["max"]) if amount_limits.get("max") else None,
            contract_size=float(market.get("contractSize") or 1.0),
        )

    async def prepare_symbol(self, symbol: str, leverage: float) -> None:
        """Set one-way mode and leverage. Tolerates 'already set' errors.

        One-way mode matters: in hedge mode ``reduceOnly`` is ambiguous about
        which side it reduces, and a protective stop could close the wrong leg.
        """
        try:
            await self._call("set_position_mode", self.ex.set_position_mode, False, symbol)
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            log.info("set_position_mode_skipped symbol=%s reason=%s", symbol, exc)
        try:
            await self._call("set_leverage", self.ex.set_leverage, int(leverage), symbol)
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            log.info("set_leverage_skipped symbol=%s reason=%s", symbol, exc)

    # ------------------------------------------------------------ account data
    async def fetch_equity(self) -> float:
        balance = await self._call("fetch_balance", self.ex.fetch_balance)
        # Bybit unified accounts report equity in several places depending on
        # account type; try each rather than assuming one shape.
        candidates: list[Any] = []
        total = balance.get("total") or {}
        candidates.append(total.get("USDT"))
        usdt = balance.get("USDT") or {}
        candidates.append(usdt.get("total"))
        try:
            info_list = balance["info"]["result"]["list"]
            if info_list:
                candidates.append(info_list[0].get("totalEquity"))
        except (KeyError, IndexError, TypeError):
            pass
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                value = float(candidate)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        raise ExchangeCallFailed(
            "could not determine account equity from fetch_balance; "
            "check the API key has read permission on the unified account"
        )

    async def fetch_mark_price(self, symbol: str) -> float:
        ticker = await self._call("fetch_ticker", self.ex.fetch_ticker, symbol)
        for key in ("last", "mark", "close", "bid", "ask"):
            value = ticker.get(key)
            if value:
                return float(value)
        info_mark = (ticker.get("info") or {}).get("markPrice")
        if info_mark:
            return float(info_mark)
        raise ExchangeCallFailed(f"no usable price in ticker for {symbol}")

    # ------------------------------------------------------------------ orders
    def _normalise(self, order: dict[str, Any], symbol: str) -> OrderState:
        info = order.get("info") or {}
        reduce_only = bool(
            order.get("reduceOnly")
            if order.get("reduceOnly") is not None
            else str(info.get("reduceOnly", "")).lower() == "true"
        )
        trigger = order.get("triggerPrice") or order.get("stopPrice") or info.get("triggerPrice")
        return OrderState(
            id=str(order.get("id") or ""),
            symbol=order.get("symbol") or symbol,
            side=str(order.get("side") or ""),
            type=str(order.get("type") or ""),
            status=str(order.get("status") or "open"),
            amount=float(order.get("amount") or 0.0),
            filled=float(order.get("filled") or 0.0),
            average=float(order["average"]) if order.get("average") else None,
            price=float(order["price"]) if order.get("price") else None,
            trigger_price=float(trigger) if trigger else None,
            reduce_only=reduce_only,
            client_order_id=order.get("clientOrderId") or info.get("orderLinkId"),
            raw=order,
        )

    async def create_entry_limit(
        self, symbol: str, side: str, qty: float, price: float, client_order_id: str
    ) -> OrderState:
        params = {
            "timeInForce": "GTC",
            "clientOrderId": client_order_id,
            "positionIdx": 0,
            "reduceOnly": False,
        }
        order = await self._call(
            f"create_entry_limit[{symbol}]",
            self.ex.create_order,
            symbol,
            "limit",
            side,
            qty,
            price,
            params,
        )
        return self._normalise(order, symbol)

    async def create_stop_market(
        self,
        symbol: str,
        position_side: str,
        qty: float,
        trigger_price: float,
        client_order_id: str,
    ) -> OrderState:
        """Reduce-only stop-market. ``position_side`` is the side being protected."""
        exit_side = "sell" if position_side == "long" else "buy"
        params = {
            "clientOrderId": client_order_id,
            "positionIdx": 0,
            "reduceOnly": True,
            # ccxt maps stopLossPrice onto Bybit's conditional-order fields and
            # derives triggerDirection from the position side.
            "stopLossPrice": trigger_price,
            "triggerDirection": 2 if position_side == "long" else 1,
        }
        order = await self._call(
            f"create_stop_market[{symbol}]",
            self.ex.create_order,
            symbol,
            "market",
            exit_side,
            qty,
            None,
            params,
        )
        return self._normalise(order, symbol)

    async def create_tp_limit(
        self,
        symbol: str,
        position_side: str,
        qty: float,
        price: float,
        client_order_id: str,
    ) -> OrderState:
        """Reduce-only resting limit at the target. Rests as maker."""
        exit_side = "sell" if position_side == "long" else "buy"
        params = {
            "timeInForce": "GTC",
            "clientOrderId": client_order_id,
            "positionIdx": 0,
            "reduceOnly": True,
        }
        order = await self._call(
            f"create_tp_limit[{symbol}]",
            self.ex.create_order,
            symbol,
            "limit",
            exit_side,
            qty,
            price,
            params,
        )
        return self._normalise(order, symbol)

    async def fetch_order(self, order_id: str, symbol: str) -> OrderState:
        order = await self._call(
            f"fetch_order[{order_id}]", self.ex.fetch_order, order_id, symbol
        )
        return self._normalise(order, symbol)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            await self._call(f"cancel_order[{order_id}]", self.ex.cancel_order, order_id, symbol)
            return True
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            # Already gone is the common case and is a success for our purposes.
            if "OrderNotFound" in str(exc) or "not exists" in str(exc).lower():
                log.info("cancel_order_already_gone id=%s symbol=%s", order_id, symbol)
                return True
            log.error("cancel_order_failed id=%s symbol=%s err=%s", order_id, symbol, exc)
            return False

    async def fetch_open_orders(self, symbol: str) -> list[OrderState]:
        orders = await self._call(
            f"fetch_open_orders[{symbol}]", self.ex.fetch_open_orders, symbol
        )
        normalised = [self._normalise(o, symbol) for o in orders]
        # Bybit keeps conditional orders in a separate query bucket on some
        # account types; fetch them explicitly and merge, de-duplicating by id.
        try:
            stop_orders = await self._call(
                f"fetch_open_stop_orders[{symbol}]",
                self.ex.fetch_open_orders,
                symbol,
                None,
                None,
                {"orderFilter": "StopOrder"},
            )
            seen = {o.id for o in normalised}
            normalised.extend(
                self._normalise(o, symbol) for o in stop_orders if str(o.get("id")) not in seen
            )
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            log.debug("stop_order_query_unsupported symbol=%s err=%s", symbol, exc)
        return normalised

    async def fetch_position(self, symbol: str) -> PositionState | None:
        positions = await self._call(
            f"fetch_positions[{symbol}]", self.ex.fetch_positions, [symbol]
        )
        for pos in positions:
            qty = float(pos.get("contracts") or 0.0)
            if qty <= 0:
                continue
            side = str(pos.get("side") or "").lower()
            if side not in ("long", "short"):
                continue
            return PositionState(
                symbol=symbol,
                side=side,
                qty=qty,
                entry_price=float(pos.get("entryPrice") or 0.0),
                unrealized_pnl=float(pos.get("unrealizedPnl") or 0.0),
                raw=pos,
            )
        return None


# ---------------------------------------------------------------------------
# In-memory simulator (DRY_RUN + tests)
# ---------------------------------------------------------------------------
class PaperExchange:
    """Deterministic exchange simulator.

    Intentionally does NOT auto-cancel the sibling protective order when a
    position closes: cleaning that up is the reconciler's responsibility, and
    the test suite must be able to observe it happening.
    """

    def __init__(
        self,
        cfg: Settings | None = None,
        *,
        equity: float = 10_000.0,
        specs: dict[str, MarketSpec] | None = None,
        auto_fill_entry: bool = True,
        auto_fill_ratio: float = 1.0,
    ) -> None:
        self.cfg = cfg
        self.equity = equity if cfg is None else (cfg.dry_run_equity if cfg.mode is Mode.DRY_RUN else equity)
        self.auto_fill_entry = auto_fill_entry
        # <1.0 simulates an entry that only partially fills before the timeout.
        self.auto_fill_ratio = auto_fill_ratio
        self.specs: dict[str, MarketSpec] = specs or {}
        self.orders: dict[str, OrderState] = {}
        self.positions: dict[str, PositionState] = {}
        self.prices: dict[str, float] = {}
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.prepared: list[str] = []
        self._seq = 0
        self.fail_next: dict[str, Exception] = {}

    # ----------------------------------------------------------------- helpers
    def _next_id(self, prefix: str = "ord") -> str:
        self._seq += 1
        return f"{prefix}-{self._seq}"

    def _maybe_fail(self, op: str) -> None:
        exc = self.fail_next.pop(op, None)
        if exc is not None:
            raise exc

    def _default_spec(self, symbol: str) -> MarketSpec:
        return MarketSpec(
            symbol=symbol,
            amount_step=0.001,
            amount_min=0.001,
            price_step=0.1,
            min_notional=5.0,
        )

    def set_price(self, symbol: str, price: float) -> None:
        self.prices[symbol] = price

    # -------------------------------------------------------------- lifecycle
    async def open(self) -> None:
        self.calls.append(("open", ()))

    async def close(self) -> None:
        self.calls.append(("close", ()))

    async def market_spec(self, symbol: str) -> MarketSpec:
        return self.specs.get(symbol) or self._default_spec(symbol)

    async def fetch_equity(self) -> float:
        self._maybe_fail("fetch_equity")
        return self.equity

    async def fetch_mark_price(self, symbol: str) -> float:
        return self.prices.get(symbol, 0.0)

    async def prepare_symbol(self, symbol: str, leverage: float) -> None:
        self.prepared.append(symbol)

    # ----------------------------------------------------------------- orders
    def _record(self, order: OrderState) -> OrderState:
        self.orders[order.id] = order
        return order

    async def create_entry_limit(
        self, symbol: str, side: str, qty: float, price: float, client_order_id: str
    ) -> OrderState:
        self._maybe_fail("create_entry_limit")
        self.calls.append(("create_entry_limit", (symbol, side, qty, price)))
        for existing in self.orders.values():
            if existing.client_order_id == client_order_id:
                # Mirrors a venue rejecting a duplicate orderLinkId.
                return existing
        order = OrderState(
            id=self._next_id("entry"),
            symbol=symbol,
            side=side,
            type="limit",
            status="open",
            amount=qty,
            price=price,
            client_order_id=client_order_id,
        )
        self._record(order)
        if self.auto_fill_entry:
            self.fill_order(order.id, qty=qty * self.auto_fill_ratio)
        return self.orders[order.id]

    async def create_stop_market(
        self,
        symbol: str,
        position_side: str,
        qty: float,
        trigger_price: float,
        client_order_id: str,
    ) -> OrderState:
        self._maybe_fail("create_stop_market")
        self.calls.append(("create_stop_market", (symbol, position_side, qty, trigger_price)))
        return self._record(
            OrderState(
                id=self._next_id("stop"),
                symbol=symbol,
                side="sell" if position_side == "long" else "buy",
                type="market",
                status="open",
                amount=qty,
                trigger_price=trigger_price,
                reduce_only=True,
                client_order_id=client_order_id,
            )
        )

    async def create_tp_limit(
        self,
        symbol: str,
        position_side: str,
        qty: float,
        price: float,
        client_order_id: str,
    ) -> OrderState:
        self._maybe_fail("create_tp_limit")
        self.calls.append(("create_tp_limit", (symbol, position_side, qty, price)))
        return self._record(
            OrderState(
                id=self._next_id("tp"),
                symbol=symbol,
                side="sell" if position_side == "long" else "buy",
                type="limit",
                status="open",
                amount=qty,
                price=price,
                reduce_only=True,
                client_order_id=client_order_id,
            )
        )

    async def fetch_order(self, order_id: str, symbol: str) -> OrderState:
        order = self.orders.get(order_id)
        if order is None:
            raise FatalExchangeError(f"OrderNotFound: {order_id}")
        return order

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        self.calls.append(("cancel_order", (order_id, symbol)))
        order = self.orders.get(order_id)
        if order is None:
            return True
        if order.is_open:
            order.status = "canceled"
        return True

    async def fetch_open_orders(self, symbol: str) -> list[OrderState]:
        return [o for o in self.orders.values() if o.symbol == symbol and o.is_open]

    async def fetch_position(self, symbol: str) -> PositionState | None:
        return self.positions.get(symbol)

    # ------------------------------------------------------------- test hooks
    def fill_order(self, order_id: str, qty: float | None = None, price: float | None = None) -> OrderState:
        """Fill an order fully or partially and apply it to the position book."""
        order = self.orders[order_id]
        fill_qty = order.remaining if qty is None else min(qty, order.remaining)
        fill_price = price if price is not None else (order.price or order.trigger_price or 0.0)
        if fill_qty <= 0:
            return order

        order.filled += fill_qty
        order.average = fill_price
        order.status = "closed" if order.remaining <= 1e-12 else "open"

        pos = self.positions.get(order.symbol)
        if order.reduce_only:
            if pos is not None:
                pos.qty = round(pos.qty - fill_qty, 12)
                if pos.qty <= 1e-12:
                    del self.positions[order.symbol]
        else:
            side = "long" if order.side == "buy" else "short"
            if pos is None:
                self.positions[order.symbol] = PositionState(
                    symbol=order.symbol, side=side, qty=fill_qty, entry_price=fill_price
                )
            else:
                total = pos.qty + fill_qty
                pos.entry_price = (pos.entry_price * pos.qty + fill_price * fill_qty) / total
                pos.qty = total
        return order

    def trigger_stop(self, symbol: str, price: float | None = None) -> OrderState | None:
        """Simulate the stop-market trigger firing and filling."""
        for order in self.orders.values():
            if order.symbol == symbol and order.is_open and order.reduce_only and order.type == "market":
                return self.fill_order(order.id, price=price if price is not None else order.trigger_price)
        return None

    def fill_take_profit(self, symbol: str) -> OrderState | None:
        for order in self.orders.values():
            if order.symbol == symbol and order.is_open and order.reduce_only and order.type == "limit":
                return self.fill_order(order.id)
        return None

    def seed_position(
        self, symbol: str, side: str, qty: float, entry_price: float
    ) -> PositionState:
        """Create a position with no local record - simulates a crash mid-entry."""
        pos = PositionState(symbol=symbol, side=side, qty=qty, entry_price=entry_price)
        self.positions[symbol] = pos
        return pos

    def open_orders_of(self, symbol: str, purpose: str) -> list[OrderState]:
        want_market = purpose == "stop"
        return [
            o
            for o in self.orders.values()
            if o.symbol == symbol
            and o.is_open
            and o.reduce_only
            and (o.type == "market") == want_market
        ]


def build_exchange(cfg: Settings) -> ExchangeAPI:
    """Pick an implementation from the configured mode."""
    if cfg.mode is Mode.DRY_RUN:
        log.warning("DRY_RUN mode: no orders will reach an exchange")
        return PaperExchange(cfg, equity=cfg.dry_run_equity)
    return ExchangeClient(cfg)


__all__ = [
    "ExchangeAPI",
    "ExchangeCallFailed",
    "ExchangeClient",
    "FatalExchangeError",
    "OrderState",
    "PaperExchange",
    "PositionState",
    "build_exchange",
    "make_client_order_id",
    "round_to_step",
]
