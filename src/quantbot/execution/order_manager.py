"""Order management with retry/backoff and idempotency.

Wraps a ``TradingVenue`` to add:
  * client-id idempotency keys (so a retried submit never double-fills),
  * bounded exponential-backoff retries on transient ``BrokerError``,
  * structured logging of every order/fill,
  * an in-memory record the engine and dashboard can read.
"""

from __future__ import annotations

import time
import uuid

from quantbot.integrations.base import BrokerError, Order, OrderStatus, TradingVenue
from quantbot.logging_setup import get_logger, log_fill, log_order

log = get_logger("execution.order_manager")


class OrderManager:
    def __init__(self, venue: TradingVenue, max_retries: int = 4, base_delay: float = 1.0) -> None:
        self.venue = venue
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.orders: dict[str, Order] = {}

    @staticmethod
    def new_client_id(prefix: str = "ord") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:16]}"

    def submit(self, order: Order, sleep=time.sleep) -> Order:
        if order.client_id in self.orders and self.orders[order.client_id].status in (
            OrderStatus.FILLED,
            OrderStatus.SUBMITTED,
        ):
            # Idempotency: already acted on this client id.
            return self.orders[order.client_id]

        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                result = self.venue.submit_order(order)
                self.orders[order.client_id] = result
                log_order(
                    log, client_id=order.client_id, symbol=order.symbol,
                    side=order.side.value, qty=order.qty, status=result.status.value,
                    venue=self.venue.name,
                )
                if result.status == OrderStatus.FILLED:
                    log_fill(
                        log, client_id=order.client_id, symbol=order.symbol,
                        qty=result.filled_qty, price=result.avg_fill_price, fee=result.fee,
                    )
                return result
            except BrokerError as e:
                last_err = e
                delay = self.base_delay * (2 ** attempt)
                log.warning("order_retry", client_id=order.client_id, attempt=attempt,
                            delay=delay, error=str(e))
                sleep(delay)
        order.status = OrderStatus.REJECTED
        order.reason = f"max_retries_exceeded: {last_err}"
        self.orders[order.client_id] = order
        log.error("order_failed", client_id=order.client_id, error=str(last_err))
        return order

    def cancel(self, venue_order_id: str, symbol: str | None = None) -> bool:
        try:
            return self.venue.cancel_order(venue_order_id, symbol)
        except BrokerError as e:  # pragma: no cover
            log.error("cancel_failed", venue_order_id=venue_order_id, error=str(e))
            return False
