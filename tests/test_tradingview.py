import json

import pytest

from quantbot.config import CostConfig, RiskConfig, Settings
from quantbot.execution.engine import LiveEngine
from quantbot.execution.paper_broker import PaperBroker
from quantbot.integrations.tradingview import (
    AlertError,
    TradingViewAlert,
    TradingViewBridge,
    normalize_symbol,
)

SECRET = "test-secret-0123456789"


def _bridge(**kw):
    s = Settings(risk=RiskConfig(**kw))
    broker = PaperBroker(starting_cash=10_000, costs=CostConfig(taker_fee=0.0, slippage_bps=0.0))
    engine = LiveEngine(broker, {}, settings=s, starting_equity=10_000)
    return TradingViewBridge(engine, SECRET)


def _alert(**kw):
    body = {"secret": SECRET, "action": "buy", "symbol": "BINANCE:BTCUSDT", "price": 100.0}
    body.update(kw)
    return json.dumps(body)


@pytest.mark.parametrize("raw,expected", [
    ("BINANCE:BTCUSDT", "BTC/USDT"),
    ("BTCUSDT.P", "BTC/USDT"),
    ("ethusdc", "ETH/USDC"),
    ("SOL/USDT", "SOL/USDT"),
    ("COINBASE:BTC-USD", "BTC/USD"),
])
def test_normalize_symbol(raw, expected):
    assert normalize_symbol(raw) == expected


def test_parse_rejects_bad_secret():
    with pytest.raises(AlertError) as e:
        TradingViewAlert.parse(_alert(secret="nope"), SECRET)
    assert e.value.status == 401


@pytest.mark.parametrize("body", [
    "not json",
    _alert(action="hold"),
    _alert(symbol=""),
    _alert(price="abc"),
    _alert(stop=150.0),          # stop above entry for a long
    _alert(take_profit=90.0),    # target below entry for a long
])
def test_parse_rejects_malformed(body):
    with pytest.raises(AlertError):
        TradingViewAlert.parse(body, SECRET)


def test_bridge_requires_secret():
    with pytest.raises(ValueError):
        TradingViewBridge(engine=None, secret="")


def test_buy_then_sell_round_trip():
    b = _bridge()
    r = b.handle(_alert(stop=90.0))
    assert r["status"] == "opened"
    pos = b.engine.positions["BTC/USDT"]
    # 0.75% of 10k risked over a 10-point stop -> 7.5 units.
    assert pos.qty == pytest.approx(7.5)
    assert pos.stop_price == 90.0

    r = b.handle(_alert(action="sell", price=110.0))
    assert r["status"] == "closed"
    assert b.engine.positions == {}
    assert b.engine.equity == pytest.approx(10_075.0)


def test_second_buy_is_not_pyramided():
    b = _bridge()
    b.handle(_alert(stop=90.0))
    assert b.handle(_alert(stop=90.0, price=101.0))["status"] == "already_open"


def test_close_without_position():
    assert _bridge().handle(_alert(action="close"))["status"] == "no_position"


def test_stop_hit_on_next_alert():
    b = _bridge()
    b.handle(_alert(stop=90.0))
    # Any later alert for the symbol at/below the stop exits the position.
    r = b.handle(_alert(action="sell", price=89.0))
    assert r["status"] == "stop"
    assert b.engine.positions == {}


def test_duplicate_alert_id_is_ignored():
    b = _bridge()
    first = b.handle(_alert(stop=90.0, id="2026-10-15T10:00:00Z"))
    dup = b.handle(_alert(stop=90.0, id="2026-10-15T10:00:00Z"))
    assert first["status"] == "opened"
    assert dup["duplicate"] is True
    assert b.engine.positions["BTC/USDT"].qty == pytest.approx(7.5)


def test_risk_gate_blocks_entries():
    b = _bridge(max_concurrent_positions=1)
    assert b.handle(_alert(stop=90.0))["status"] == "opened"
    r = b.handle(_alert(symbol="ETHUSDT", price=50.0, stop=45.0))
    assert r["status"] == "max_concurrent_positions"


def test_symbol_allowlist():
    b = _bridge()
    b.allowed_symbols = {"ETH/USDT"}
    with pytest.raises(AlertError) as e:
        b.handle(_alert())
    assert e.value.status == 403


def test_paper_alert_without_price_is_rejected():
    with pytest.raises(AlertError):
        _bridge().handle(_alert(price=None))


def test_webhook_http_endpoint():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from quantbot.execution.webhook_server import create_app

    b = _bridge()
    client = TestClient(create_app(b))
    assert client.get("/health").json() == {"status": "ok"}

    r = client.post("/webhook/tradingview", content=_alert(secret="wrong"))
    assert r.status_code == 401

    r = client.post("/webhook/tradingview", content=_alert(stop=90.0))
    assert r.status_code == 200 and r.json()["status"] == "opened"
    assert "BTC/USDT" in client.get("/api/status").json()["positions"]

    blocked = TestClient(create_app(b, allowed_ips=frozenset({"52.89.214.238"})))
    assert blocked.post("/webhook/tradingview", content=_alert()).status_code == 403
