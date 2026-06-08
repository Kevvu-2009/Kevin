"""Bullpen integration.

Implements the ``TradingVenue`` interface against Bullpen's REST API for crypto
trading.  Credentials come from the environment (``BULLPEN_API_KEY`` /
``BULLPEN_API_SECRET``); nothing is hard-coded.

NOTE ON ENDPOINTS
-----------------
The exact REST paths and signing scheme should be confirmed against the current
Bullpen API documentation for your account tier.  This client centralises every
venue-specific detail in one place (``_request`` + the path constants below) so
adapting to the live spec is a localised change.  Authentication uses the common
HMAC-SHA256 "timestamp + method + path + body" signature pattern; switch the
scheme in ``_sign`` if Bullpen uses bearer tokens instead.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone

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
from quantbot.logging_setup import get_logger

log = get_logger("integrations.bullpen")

# Endpoint paths (confirm against live docs).
_PATHS = {
    "ticker": "/v1/market/ticker",
    "ohlcv": "/v1/market/candles",
    "order": "/v1/orders",
    "positions": "/v1/positions",
    "balances": "/v1/account/balances",
    "trades": "/v1/trades",
}


class BullpenVenue(TradingVenue):
    name = "bullpen"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("BULLPEN_API_KEY", "")
        self.api_secret = api_secret or os.getenv("BULLPEN_API_SECRET", "")
        self.base_url = (base_url or os.getenv("BULLPEN_BASE_URL", "https://api.bullpen.xyz")).rstrip("/")
        self.timeout = timeout
        self._client = None

    # ------------------------------------------------------------- transport
    def _http(self):
        if self._client is None:
            import httpx

            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        return self._client

    def _sign(self, method: str, path: str, body: str, ts: str) -> str:
        prehash = f"{ts}{method.upper()}{path}{body}"
        return hmac.new(self.api_secret.encode(), prehash.encode(), hashlib.sha256).hexdigest()

    def _headers(self, method: str, path: str, body: str) -> dict:
        ts = str(int(time.time() * 1000))
        return {
            "BP-API-KEY": self.api_key,
            "BP-API-TIMESTAMP": ts,
            "BP-API-SIGN": self._sign(method, path, body, ts),
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        body_str = json.dumps(body) if body else ""
        try:
            resp = self._http().request(
                method, path, params=params,
                content=body_str or None,
                headers=self._headers(method, path, body_str),
            )
        except Exception as e:  # pragma: no cover - network
            raise BrokerError(f"bullpen network error: {e}") from e
        if resp.status_code >= 400:
            raise BrokerError(f"bullpen {resp.status_code}: {resp.text}")
        return resp.json() if resp.content else {}

    # ------------------------------------------------------------- lifecycle
    def authenticate(self) -> None:
        if not self.api_key or not self.api_secret:
            raise BrokerError("Bullpen credentials not configured (set BULLPEN_API_KEY/SECRET)")
        # A lightweight authenticated call validates the credentials.
        self._request("GET", _PATHS["balances"])
        log.info("bullpen_authenticated")

    def close(self) -> None:  # pragma: no cover
        if self._client is not None:
            self._client.close()

    # ----------------------------------------------------------- market data
    def get_ticker(self, symbol: str) -> float:
        data = self._request("GET", _PATHS["ticker"], params={"symbol": symbol})
        return float(data.get("price") or data.get("last"))

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        data = self._request(
            "GET", _PATHS["ohlcv"], params={"symbol": symbol, "interval": timeframe, "limit": limit}
        )
        rows = data.get("candles", data if isinstance(data, list) else [])
        out = []
        for r in rows:
            ts = r[0] if isinstance(r, list) else r["ts"]
            out.append(
                Candle(
                    ts=datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc),
                    open=float(r[1] if isinstance(r, list) else r["open"]),
                    high=float(r[2] if isinstance(r, list) else r["high"]),
                    low=float(r[3] if isinstance(r, list) else r["low"]),
                    close=float(r[4] if isinstance(r, list) else r["close"]),
                    volume=float(r[5] if isinstance(r, list) else r["volume"]),
                )
            )
        return out

    # ---------------------------------------------------------------- trading
    def submit_order(self, order: Order) -> Order:
        body = {
            "clientId": order.client_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "type": order.type.value,
            "quantity": order.qty,
        }
        if order.type == OrderType.LIMIT and order.limit_price is not None:
            body["price"] = order.limit_price
        data = self._request("POST", _PATHS["order"], body=body)
        order.venue_order_id = str(data.get("orderId") or data.get("id") or "")
        status = (data.get("status") or "submitted").lower()
        order.status = _map_status(status)
        order.filled_qty = float(data.get("filledQty", 0) or 0)
        order.avg_fill_price = float(data.get("avgPrice", 0) or 0)
        order.fee = float(data.get("fee", 0) or 0)
        log.info("bullpen_order_submitted", client_id=order.client_id,
                 venue_order_id=order.venue_order_id, status=order.status.value)
        return order

    def cancel_order(self, venue_order_id: str, symbol: str | None = None) -> bool:
        self._request("DELETE", f"{_PATHS['order']}/{venue_order_id}",
                      params={"symbol": symbol} if symbol else None)
        return True

    def get_positions(self) -> list[Position]:
        data = self._request("GET", _PATHS["positions"])
        rows = data.get("positions", data if isinstance(data, list) else [])
        return [
            Position(
                symbol=r["symbol"],
                qty=float(r.get("qty") or r.get("size") or 0),
                avg_price=float(r.get("avgPrice") or r.get("entryPrice") or 0),
                unrealized_pnl=float(r.get("unrealizedPnl", 0) or 0),
                venue=self.name,
            )
            for r in rows
        ]

    def get_balances(self) -> list[Balance]:
        data = self._request("GET", _PATHS["balances"])
        rows = data.get("balances", data if isinstance(data, list) else [])
        return [
            Balance(
                currency=r.get("currency") or r.get("asset"),
                free=float(r.get("free") or r.get("available") or 0),
                total=float(r.get("total") or r.get("balance") or 0),
            )
            for r in rows
        ]

    def get_trade_history(self, symbol: str | None = None, limit: int = 100) -> list[dict]:
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        data = self._request("GET", _PATHS["trades"], params=params)
        return data.get("trades", data if isinstance(data, list) else [])


def _map_status(s: str) -> OrderStatus:
    return {
        "new": OrderStatus.NEW,
        "open": OrderStatus.SUBMITTED,
        "submitted": OrderStatus.SUBMITTED,
        "partially_filled": OrderStatus.PARTIAL,
        "partial": OrderStatus.PARTIAL,
        "filled": OrderStatus.FILLED,
        "closed": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELLED,
        "cancelled": OrderStatus.CANCELLED,
        "rejected": OrderStatus.REJECTED,
    }.get(s.lower(), OrderStatus.SUBMITTED)


def new_client_id(prefix: str = "bp") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"
