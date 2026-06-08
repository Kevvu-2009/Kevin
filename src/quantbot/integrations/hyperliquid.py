"""Hyperliquid integration (spot + perps).

Hyperliquid is a high-performance on-chain orderbook DEX with a first-class
programmatic API — the right home for the continuous-price OHLCV strategies in
this project (trend / breakout / mean-reversion / regime).

Auth model (built for bots):
    * Generate an **API wallet (agent)** at https://app.hyperliquid.xyz/API.
    * Its private key SIGNS orders but **cannot withdraw funds**.
    * Set that key as ``HYPERLIQUID_SECRET_KEY`` and your **main wallet address**
      (not the agent's) as ``HYPERLIQUID_ACCOUNT_ADDRESS``.
Market data (candles, mids, order books) is a fully public endpoint — no auth.

The official ``hyperliquid-python-sdk`` is imported lazily so the rest of the
package imports without it.
"""

from __future__ import annotations

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

log = get_logger("integrations.hyperliquid")

# Our timeframes map 1:1 to Hyperliquid candle intervals.
_INTERVALS = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
_TF_MS = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
# Hyperliquid's default market-order slippage guard.
_DEFAULT_SLIPPAGE = 0.05


def coin_of(symbol: str) -> str:
    """Normalise 'BTC/USDT' or 'BTC-PERP' to the Hyperliquid coin name 'BTC'."""
    return symbol.split("/")[0].split("-")[0].upper()


class HyperliquidVenue(TradingVenue):
    name = "hyperliquid"

    def __init__(
        self,
        secret_key: str | None = None,
        account_address: str | None = None,
        base_url: str | None = None,
        testnet: bool | None = None,
    ) -> None:
        self.secret_key = secret_key or os.getenv("HYPERLIQUID_SECRET_KEY", "")
        self.account_address = account_address or os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS", "")
        env_testnet = os.getenv("HYPERLIQUID_TESTNET", "false").lower() in {"1", "true", "yes"}
        self.testnet = env_testnet if testnet is None else testnet
        self._base_url = base_url or os.getenv("HYPERLIQUID_API_URL", "")
        self._info = None
        self._exchange = None
        self._account = None

    # ------------------------------------------------------------- transport
    def _urls(self):
        from hyperliquid.utils import constants

        if self._base_url:
            return self._base_url
        return constants.TESTNET_API_URL if self.testnet else constants.MAINNET_API_URL

    def info(self):
        """Public info client (no auth needed)."""
        if self._info is None:
            try:
                from hyperliquid.info import Info
            except ImportError as e:  # pragma: no cover
                raise BrokerError("hyperliquid-python-sdk not installed") from e
            self._info = Info(self._urls(), skip_ws=True)
        return self._info

    def _exch(self):
        if self._exchange is None:
            try:
                import eth_account
                from hyperliquid.exchange import Exchange
            except ImportError as e:  # pragma: no cover
                raise BrokerError("hyperliquid-python-sdk not installed") from e
            if not self.secret_key:
                raise BrokerError("HYPERLIQUID_SECRET_KEY not configured (API wallet key)")
            self._account = eth_account.Account.from_key(self.secret_key)
            # account_address = MAIN wallet; the agent key signs on its behalf.
            address = self.account_address or self._account.address
            self._exchange = Exchange(self._account, self._urls(), account_address=address)
        return self._exchange

    @property
    def address(self) -> str:
        if self.account_address:
            return self.account_address
        return self._exch().account_address

    # ------------------------------------------------------------- lifecycle
    def authenticate(self) -> None:
        if not self.secret_key:
            raise BrokerError("Hyperliquid credentials not configured (set HYPERLIQUID_SECRET_KEY)")
        self._exch()  # builds signer
        # A user_state read validates the address has an account.
        self.info().user_state(self.address)
        log.info("hyperliquid_authenticated", testnet=self.testnet, address=self.address)

    # ----------------------------------------------------------- market data
    def get_ticker(self, symbol: str) -> float:
        mids = self.info().all_mids()
        coin = coin_of(symbol)
        if coin not in mids:
            raise BrokerError(f"no mid price for {coin}")
        return float(mids[coin])

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        if timeframe not in _INTERVALS:
            raise BrokerError(f"unsupported timeframe {timeframe}")
        coin = coin_of(symbol)
        end = int(time.time() * 1000)
        start = end - limit * _TF_MS[timeframe]
        raw = self.info().candles_snapshot(coin, _INTERVALS[timeframe], start, end)
        return [_to_candle(c) for c in (raw or [])][-limit:]

    # ---------------------------------------------------------------- trading
    def submit_order(self, order: Order) -> Order:
        ex = self._exch()
        coin = coin_of(order.symbol)
        is_buy = order.side == OrderSide.BUY
        try:
            if order.type == OrderType.MARKET:
                # SDK computes an aggressive price from the current mid + slippage.
                resp = ex.market_open(coin, is_buy, float(order.qty), None, _DEFAULT_SLIPPAGE)
            else:
                px = float(order.limit_price)
                resp = ex.order(coin, is_buy, float(order.qty), px, {"limit": {"tif": "Gtc"}})
        except Exception as e:  # pragma: no cover - network/signing
            raise BrokerError(f"hyperliquid order error: {e}") from e
        _apply_order_response(order, resp)
        log.info("hyperliquid_order", client_id=order.client_id, coin=coin,
                 side=order.side.value, status=order.status.value,
                 venue_order_id=order.venue_order_id)
        return order

    def cancel_order(self, venue_order_id: str, symbol: str | None = None) -> bool:
        if symbol is None:
            raise BrokerError("hyperliquid cancel requires the symbol/coin")
        try:
            resp = self._exch().cancel(coin_of(symbol), int(venue_order_id))
            return isinstance(resp, dict) and resp.get("status") == "ok"
        except Exception as e:  # pragma: no cover
            raise BrokerError(f"hyperliquid cancel error: {e}") from e

    def get_positions(self) -> list[Position]:
        us = self.info().user_state(self.address)
        out = []
        for ap in us.get("assetPositions", []):
            p = ap.get("position", {})
            szi = float(p.get("szi", 0) or 0)
            if szi == 0:
                continue
            out.append(
                Position(
                    symbol=p.get("coin", ""),
                    qty=szi,  # signed: >0 long, <0 short
                    avg_price=float(p.get("entryPx", 0) or 0),
                    unrealized_pnl=float(p.get("unrealizedPnl", 0) or 0),
                    venue=self.name,
                    meta={"leverage": p.get("leverage")},
                )
            )
        return out

    def get_balances(self) -> list[Balance]:
        us = self.info().user_state(self.address)
        summary = us.get("marginSummary", {})
        total = float(summary.get("accountValue", 0) or 0)
        free = float(us.get("withdrawable", 0) or 0)
        return [Balance(currency="USDC", free=free, total=total)]

    def get_trade_history(self, symbol: str | None = None, limit: int = 100) -> list[dict]:
        fills = self.info().user_fills(self.address) or []
        if symbol:
            coin = coin_of(symbol)
            fills = [f for f in fills if f.get("coin") == coin]
        return fills[:limit]

    # ----------------------------------------------------------------- agents
    def approve_agent(self, name: str | None = None) -> dict:
        """One-time: authorise this API wallet as an agent of the main account.

        Run once from a context that holds the MAIN wallet key, or do it in the
        Hyperliquid web UI (https://app.hyperliquid.xyz/API). Included for
        completeness/automation.
        """
        return self._exch().approve_agent(name)


def _to_candle(c: dict) -> Candle:
    return Candle(
        ts=datetime.fromtimestamp(int(c["t"]) / 1000, tz=timezone.utc),
        open=float(c["o"]), high=float(c["h"]), low=float(c["l"]),
        close=float(c["c"]), volume=float(c["v"]),
    )


def _apply_order_response(order: Order, resp: dict) -> None:
    """Map a Hyperliquid order response onto our Order object."""
    if not isinstance(resp, dict) or resp.get("status") != "ok":
        order.status = OrderStatus.REJECTED
        order.reason = str(resp)
        return
    try:
        statuses = resp["response"]["data"]["statuses"]
        st = statuses[0] if statuses else {}
    except (KeyError, IndexError, TypeError):
        order.status = OrderStatus.SUBMITTED
        return
    if "error" in st:
        order.status = OrderStatus.REJECTED
        order.reason = st["error"]
    elif "resting" in st:
        order.status = OrderStatus.SUBMITTED
        order.venue_order_id = str(st["resting"].get("oid", ""))
    elif "filled" in st:
        f = st["filled"]
        order.status = OrderStatus.FILLED
        order.venue_order_id = str(f.get("oid", ""))
        order.filled_qty = float(f.get("totalSz", order.qty) or order.qty)
        order.avg_fill_price = float(f.get("avgPx", 0) or 0)
    else:
        order.status = OrderStatus.SUBMITTED


def new_client_id(prefix: str = "hl") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"
