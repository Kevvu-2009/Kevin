"""Hyperliquid venue hardening: rate limiter, reconnect/retry, order types."""

import pytest

from quantbot.integrations.base import BrokerError, Order, OrderSide, OrderStatus, OrderType
from quantbot.integrations.hyperliquid import (
    HyperliquidVenue,
    RateLimiter,
    _is_transport_error,
)


def test_rate_limiter_throttles_bursts():
    rl = RateLimiter(max_calls=3, per_seconds=1.0)
    sleeps = []
    for _ in range(5):
        rl.acquire(sleep=sleeps.append)
    assert len(sleeps) == 2          # 4th and 5th call had to wait
    assert all(0 < s <= 1.0 for s in sleeps)


def test_transport_error_classification():
    assert _is_transport_error(ConnectionError("boom"))
    assert _is_transport_error(TimeoutError())
    assert _is_transport_error(Exception("Read timed out"))
    assert _is_transport_error(Exception("502 Bad Gateway"))
    assert not _is_transport_error(Exception("Insufficient margin"))
    assert not _is_transport_error(Exception("Order has invalid size"))


def test_call_retries_transport_then_succeeds():
    v = HyperliquidVenue(secret_key="", account_address="0xabc", testnet=True)
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("connection reset")
        return "ok"

    assert v._call(flaky, _sleep=lambda s: None) == "ok"
    assert attempts["n"] == 3


def test_call_does_not_retry_rejections():
    v = HyperliquidVenue(secret_key="", account_address="0xabc", testnet=True)
    attempts = {"n": 0}

    def rejected():
        attempts["n"] += 1
        raise Exception("Insufficient margin")

    with pytest.raises(Exception, match="margin"):
        v._call(rejected, _sleep=lambda s: None)
    assert attempts["n"] == 1        # no second attempt on a real rejection


class FakeExchange:
    """Captures SDK calls so order-type translation can be asserted."""

    def __init__(self):
        self.calls = []

    def _ok(self, oid=1):
        return {"status": "ok", "response": {"type": "order",
                "data": {"statuses": [{"resting": {"oid": oid}}]}}}

    def market_open(self, coin, is_buy, sz, px, slippage):
        self.calls.append(("market_open", coin, is_buy, sz))
        return {"status": "ok", "response": {"type": "order", "data": {"statuses": [
            {"filled": {"oid": 9, "totalSz": str(sz), "avgPx": "100.0"}}]}}}

    def market_close(self, coin, sz, px, slippage):
        self.calls.append(("market_close", coin, sz))
        return self._ok()

    def order(self, coin, is_buy, sz, px, order_type, reduce_only=False, **kw):
        self.calls.append(("order", coin, is_buy, sz, px, order_type, reduce_only))
        return self._ok()

    def update_leverage(self, leverage, coin, is_cross):
        self.calls.append(("update_leverage", leverage, coin, is_cross))
        return {"status": "ok"}


@pytest.fixture()
def venue():
    v = HyperliquidVenue(secret_key="", account_address="0xabc", testnet=True)
    v._exchange = FakeExchange()
    return v


def _order(**kw):
    base = dict(client_id="t1", symbol="BTC/USDT", side=OrderSide.BUY,
                type=OrderType.MARKET, qty=0.5)
    base.update(kw)
    return Order(**base)


def test_market_order_path(venue):
    o = venue.submit_order(_order())
    assert o.status == OrderStatus.FILLED
    assert venue._exchange.calls[0][:2] == ("market_open", "BTC")


def test_reduce_only_market_uses_close(venue):
    venue.submit_order(_order(reduce_only=True, side=OrderSide.SELL))
    assert venue._exchange.calls[0][0] == "market_close"


def test_limit_order_passes_reduce_only(venue):
    venue.submit_order(_order(type=OrderType.LIMIT, limit_price=101.5, reduce_only=True))
    name, coin, is_buy, sz, px, order_type, ro = venue._exchange.calls[0]
    assert name == "order" and px == 101.5 and ro is True
    assert order_type == {"limit": {"tif": "Gtc"}}


def test_stop_market_translates_to_sl_trigger(venue):
    venue.submit_order(_order(type=OrderType.STOP_MARKET, side=OrderSide.SELL,
                              trigger_price=95.0))
    name, coin, is_buy, sz, px, order_type, ro = venue._exchange.calls[0]
    assert order_type["trigger"]["tpsl"] == "sl"
    assert order_type["trigger"]["isMarket"] is True
    assert order_type["trigger"]["triggerPx"] == 95.0
    assert ro is True                # protective orders are always reduce-only
    assert px < 95.0                 # sell bound below trigger


def test_take_profit_translates_to_tp_trigger(venue):
    venue.submit_order(_order(type=OrderType.TAKE_PROFIT, side=OrderSide.SELL,
                              trigger_price=120.0))
    *_, order_type, ro = venue._exchange.calls[0]
    assert order_type["trigger"]["tpsl"] == "tp" and ro is True


def test_stop_without_trigger_price_rejected(venue):
    with pytest.raises(BrokerError, match="trigger_price"):
        venue.submit_order(_order(type=OrderType.STOP_MARKET))


def test_set_leverage(venue):
    venue.set_leverage("ETH/USDT", 3, is_cross=True)
    assert venue._exchange.calls[0] == ("update_leverage", 3, "ETH", True)
