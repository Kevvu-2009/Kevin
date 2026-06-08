"""Polymarket integration.

Polymarket is a CLOB-based prediction market on Polygon.  Two surfaces are used:

* **Gamma API** (``gamma-api.polymarket.com``) — public market/event metadata,
  resolution status, prices.  No auth required for reads.
* **CLOB API** (``clob.polymarket.com``) — order placement / positions.  Signed
  with an EOA private key; the ``py-clob-client`` SDK handles the L1/L2 auth and
  EIP-712 order signing.  Loaded lazily so the package imports without it.

Prices/positions are expressed as probabilities in [0, 1] per outcome token.
All credentials come from the environment.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from quantbot.integrations.base import (
    Balance,
    BrokerError,
    Candle,
    Order,
    OrderSide,
    OrderStatus,
    Position,
    TradingVenue,
)
from quantbot.logging_setup import get_logger

log = get_logger("integrations.polymarket")


class PolymarketVenue(TradingVenue):
    name = "polymarket"

    def __init__(
        self,
        private_key: str | None = None,
        clob_url: str | None = None,
        gamma_url: str | None = None,
        chain_id: int | None = None,
        api_creds: dict | None = None,
        signature_type: int | None = None,
        funder: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.private_key = private_key or os.getenv("POLYMARKET_PRIVATE_KEY", "")
        self.clob_url = (clob_url or os.getenv("POLYMARKET_CLOB_URL", "https://clob.polymarket.com")).rstrip("/")
        self.gamma_url = (gamma_url or os.getenv("POLYMARKET_GAMMA_URL", "https://gamma-api.polymarket.com")).rstrip("/")
        self.chain_id = int(chain_id or os.getenv("POLYMARKET_CHAIN_ID", "137"))
        self.api_creds = api_creds or {
            "key": os.getenv("POLYMARKET_API_KEY", ""),
            "secret": os.getenv("POLYMARKET_API_SECRET", ""),
            "passphrase": os.getenv("POLYMARKET_API_PASSPHRASE", ""),
        }
        # signature_type: 0=EOA, 1=Magic/email proxy, 2=browser/Gnosis-Safe.
        # funder = address that HOLDS the USDC (your Polymarket proxy/Safe), which
        # differs from the signing key for proxy wallets. Mismatches here are the
        # #1 cause of "invalid signature" / orders attributed to the wrong wallet.
        self.signature_type = (
            int(signature_type)
            if signature_type is not None
            else int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))
        )
        self.funder = funder or os.getenv("POLYMARKET_FUNDER", "") or None
        self.timeout = timeout
        self._clob = None
        self._http = None

    # ------------------------------------------------------------- transport
    def _gamma(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(base_url=self.gamma_url, timeout=self.timeout)
        return self._http

    def _clob_client(self):
        if self._clob is None:
            try:
                from py_clob_client.client import ClobClient
                from py_clob_client.clob_types import ApiCreds
            except ImportError as e:  # pragma: no cover
                raise BrokerError("py-clob-client not installed; required for Polymarket trading") from e
            if not self.private_key:
                raise BrokerError("POLYMARKET_PRIVATE_KEY not configured")
            creds = None
            if self.api_creds.get("key"):
                creds = ApiCreds(
                    api_key=self.api_creds["key"],
                    api_secret=self.api_creds["secret"],
                    api_passphrase=self.api_creds["passphrase"],
                )
            kwargs = {"key": self.private_key, "chain_id": self.chain_id,
                      "signature_type": self.signature_type}
            if self.funder:
                kwargs["funder"] = self.funder
            self._clob = ClobClient(self.clob_url, **kwargs)
            # L2 API creds authenticate read/trade endpoints. Use provided ones
            # or derive them deterministically from the signing key.
            if creds is not None:
                self._clob.set_api_creds(creds)
            else:
                self._clob.set_api_creds(self._clob.create_or_derive_api_creds())
        return self._clob

    # ------------------------------------------------------------- lifecycle
    def authenticate(self) -> None:
        if not self.private_key:
            raise BrokerError("Polymarket credentials not configured (set POLYMARKET_PRIVATE_KEY)")
        self._clob_client()  # forces credential derivation
        log.info("polymarket_authenticated", chain_id=self.chain_id)

    def close(self) -> None:  # pragma: no cover
        if self._http is not None:
            self._http.close()

    # ----------------------------------------------------- market / events
    def list_markets(self, active: bool = True, limit: int = 100) -> list[dict]:
        resp = self._gamma().get("/markets", params={"active": str(active).lower(), "limit": limit})
        resp.raise_for_status()
        return resp.json()

    def list_events(self, limit: int = 100) -> list[dict]:
        """Event monitoring — upcoming/active events with their markets."""
        resp = self._gamma().get("/events", params={"limit": limit, "active": "true"})
        resp.raise_for_status()
        return resp.json()

    def get_market(self, condition_id: str) -> dict:
        resp = self._gamma().get(f"/markets/{condition_id}")
        resp.raise_for_status()
        return resp.json()

    def get_ticker(self, symbol: str) -> float:
        """``symbol`` is a CLOB token id; returns its mid price (0-1)."""
        try:
            book = self._clob_client().get_order_book(symbol)
            bid = float(book.bids[0].price) if book.bids else 0.0
            ask = float(book.asks[0].price) if book.asks else 1.0
            return (bid + ask) / 2.0
        except BrokerError:
            raise
        except Exception as e:  # pragma: no cover
            raise BrokerError(f"polymarket ticker error: {e}") from e

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        """Prediction markets have sparse trade prints; we return prices-history
        from the CLOB pricing endpoint mapped to pseudo-candles."""
        try:
            hist = self._clob_client().get_price_history(symbol)
        except Exception as e:  # pragma: no cover
            raise BrokerError(f"polymarket history error: {e}") from e
        out = []
        for pt in (hist or [])[-limit:]:
            t = pt.get("t") or pt.get("timestamp")
            p = float(pt.get("p") or pt.get("price"))
            out.append(
                Candle(
                    ts=datetime.fromtimestamp(int(t), tz=timezone.utc),
                    open=p, high=p, low=p, close=p, volume=0.0,
                )
            )
        return out

    # ---------------------------------------------------------------- trading
    def submit_order(self, order: Order) -> Order:
        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL
        except ImportError as e:  # pragma: no cover
            raise BrokerError("py-clob-client not installed") from e

        client = self._clob_client()
        side = BUY if order.side == OrderSide.BUY else SELL
        # Polymarket requires a limit price (probability, 0-1) per outcome token.
        price = order.limit_price if order.limit_price is not None else self.get_ticker(order.symbol)
        args = OrderArgs(token_id=order.symbol, price=float(price), size=float(order.qty), side=side)
        try:
            signed = client.create_order(args)
            # GTC = good-till-cancelled limit order on the CLOB.
            resp = client.post_order(signed, OrderType.GTC)
        except Exception as e:  # pragma: no cover
            raise BrokerError(f"polymarket order error: {e}") from e
        order.venue_order_id = str(resp.get("orderID") or resp.get("id") or "")
        order.status = OrderStatus.SUBMITTED if resp.get("success", True) else OrderStatus.REJECTED
        log.info("polymarket_order_submitted", client_id=order.client_id, venue_order_id=order.venue_order_id)
        return order

    def cancel_order(self, venue_order_id: str, symbol: str | None = None) -> bool:
        try:
            self._clob_client().cancel(order_id=venue_order_id)
            return True
        except Exception as e:  # pragma: no cover
            raise BrokerError(f"polymarket cancel error: {e}") from e

    def get_positions(self) -> list[Position]:
        try:
            raw = self._clob_client().get_positions()
        except Exception:  # pragma: no cover
            raw = []
        return [
            Position(
                symbol=str(p.get("asset") or p.get("token_id")),
                qty=float(p.get("size", 0) or 0),
                avg_price=float(p.get("avgPrice", 0) or 0),
                venue=self.name,
                meta={"market": p.get("market")},
            )
            for p in (raw or [])
        ]

    def get_balances(self) -> list[Balance]:
        # Collateral is USDC on Polygon; the CLOB exposes it via balance/allowance.
        free = 0.0
        try:
            from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            bal = self._clob_client().get_balance_allowance(params)
            # SDK returns USDC in 6-decimal base units.
            raw = bal.get("balance", 0) if isinstance(bal, dict) else getattr(bal, "balance", 0)
            free = float(raw or 0) / 1e6
        except Exception:  # pragma: no cover
            free = 0.0
        return [Balance(currency="USDC", free=free, total=free)]

    def update_allowance(self) -> dict:
        """Approve the CLOB exchange to move your USDC collateral (one-time).

        Required before the first trade. With a relayer key this is gasless;
        otherwise the signing wallet needs a little MATIC for gas.
        """
        from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        return self._clob_client().update_balance_allowance(params)

    def get_trade_history(self, symbol: str | None = None, limit: int = 100) -> list[dict]:
        try:
            return self._clob_client().get_trades() or []
        except Exception:  # pragma: no cover
            return []


def new_client_id(prefix: str = "pm") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"
