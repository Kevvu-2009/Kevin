from quantbot.integrations.base import Order, OrderSide, OrderStatus, OrderType
from quantbot.integrations.hyperliquid import (
    HyperliquidVenue,
    _apply_order_response,
    _to_candle,
    coin_of,
)


def test_coin_normalisation():
    assert coin_of("BTC/USDT") == "BTC"
    assert coin_of("eth-perp") == "ETH"
    assert coin_of("SOL") == "SOL"


def test_to_candle_parses_fields():
    c = _to_candle({"t": 1700000000000, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "100"})
    assert c.open == 1.0 and c.high == 2.0 and c.low == 0.5 and c.close == 1.5 and c.volume == 100.0


def _order():
    return Order(client_id="x", symbol="BTC", side=OrderSide.BUY, type=OrderType.LIMIT, qty=1.0, limit_price=10)


def test_order_response_resting():
    o = _order()
    resp = {"status": "ok", "response": {"type": "order", "data": {"statuses": [{"resting": {"oid": 42}}]}}}
    _apply_order_response(o, resp)
    assert o.status == OrderStatus.SUBMITTED and o.venue_order_id == "42"


def test_order_response_filled():
    o = _order()
    resp = {"status": "ok", "response": {"type": "order",
            "data": {"statuses": [{"filled": {"oid": 7, "totalSz": "1.0", "avgPx": "10.5"}}]}}}
    _apply_order_response(o, resp)
    assert o.status == OrderStatus.FILLED
    assert o.avg_fill_price == 10.5 and o.venue_order_id == "7"


def test_order_response_error():
    o = _order()
    _apply_order_response(o, {"status": "ok", "response": {"type": "order",
                          "data": {"statuses": [{"error": "insufficient margin"}]}}})
    assert o.status == OrderStatus.REJECTED and "margin" in (o.reason or "")


def test_order_response_failure_status():
    o = _order()
    _apply_order_response(o, {"status": "err", "response": "bad"})
    assert o.status == OrderStatus.REJECTED


def test_venue_constructs_without_sdk():
    v = HyperliquidVenue(secret_key="", account_address="0xabc", testnet=True)
    assert v.testnet is True and v.account_address == "0xabc"
