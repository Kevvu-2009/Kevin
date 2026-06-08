import pandas as pd

from quantbot.config import CostConfig, Settings
from quantbot.execution.engine import LiveEngine
from quantbot.execution.order_manager import OrderManager
from quantbot.execution.paper_broker import PaperBroker
from quantbot.integrations.base import BrokerError, Order, OrderSide, OrderStatus, OrderType
from quantbot.strategies.registry import get_strategy


def test_paper_broker_buy_sell_cycle():
    bk = PaperBroker(starting_cash=10_000, costs=CostConfig(taker_fee=0.0, slippage_bps=0.0))
    bk.set_price("BTC/USDT", 100.0)
    buy = Order(client_id="1", symbol="BTC/USDT", side=OrderSide.BUY, type=OrderType.MARKET, qty=10)
    r = bk.submit_order(buy)
    assert r.status == OrderStatus.FILLED
    assert abs(bk.cash - 9_000) < 1e-6
    assert bk.get_positions()[0].qty == 10

    bk.set_price("BTC/USDT", 110.0)
    sell = Order(client_id="2", symbol="BTC/USDT", side=OrderSide.SELL, type=OrderType.MARKET, qty=10)
    bk.submit_order(sell)
    assert abs(bk.equity() - 10_100) < 1e-6
    assert bk.get_positions() == []


def test_paper_broker_rejects_oversell():
    bk = PaperBroker(starting_cash=10_000)
    bk.set_price("ETH/USDT", 50.0)
    sell = Order(client_id="x", symbol="ETH/USDT", side=OrderSide.SELL, type=OrderType.MARKET, qty=1)
    r = bk.submit_order(sell)
    assert r.status == OrderStatus.REJECTED


class _FlakyVenue(PaperBroker):
    def __init__(self, fail_times=2, **kw):
        super().__init__(**kw)
        self.fail_times = fail_times
        self.calls = 0

    def submit_order(self, order):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise BrokerError("transient")
        return super().submit_order(order)


def test_order_manager_retries_then_succeeds():
    v = _FlakyVenue(fail_times=2, starting_cash=10_000, costs=CostConfig(taker_fee=0, slippage_bps=0))
    v.set_price("BTC/USDT", 100.0)
    om = OrderManager(v, max_retries=5, base_delay=0)
    order = Order(client_id="o1", symbol="BTC/USDT", side=OrderSide.BUY, type=OrderType.MARKET, qty=1)
    res = om.submit(order, sleep=lambda *_: None)
    assert res.status == OrderStatus.FILLED
    assert v.calls == 3


def test_order_manager_idempotent():
    v = PaperBroker(starting_cash=10_000, costs=CostConfig(taker_fee=0, slippage_bps=0))
    v.set_price("BTC/USDT", 100.0)
    om = OrderManager(v)
    o = Order(client_id="dup", symbol="BTC/USDT", side=OrderSide.BUY, type=OrderType.MARKET, qty=1)
    om.submit(o, sleep=lambda *_: None)
    cash_after_first = v.cash
    om.submit(o, sleep=lambda *_: None)  # same client_id -> no second fill
    assert v.cash == cash_after_first


def test_live_engine_replay_runs():
    from quantbot.data.synthetic import generate_ohlcv

    df = generate_ohlcv(n=800, timeframe="4h", seed=9)
    settings = Settings()
    broker = PaperBroker(starting_cash=10_000, costs=settings.costs)
    engine = LiveEngine(broker, {"BTC/USDT": get_strategy("trend_following")},
                        settings=settings, starting_equity=10_000)
    for i in range(210, len(df)):
        engine.on_bar("BTC/USDT", df.iloc[: i + 1])
    # Engine should have produced a finite equity and not crashed.
    assert engine.equity > 0
