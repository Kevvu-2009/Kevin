"""End-to-end flow against the mocked exchange.

Covers the full lifecycle the spec calls for:
entry fill -> stop/TP placement -> stop fill -> sibling cancellation.
"""

from __future__ import annotations

import pytest

from app.engine import Engine
from app.exchange import PaperExchange

from .conftest import BTC, ENTRY, STOP, TARGET


async def test_entry_fill_places_reduce_only_stop_and_take_profit(
    engine, paper, store, make_payload
):
    payload = make_payload()
    assert engine.claim(payload)

    result = await engine.execute_entry(payload)

    assert result.status == "filled"
    assert result.qty == pytest.approx(0.070)

    # Position at the venue.
    position = paper.positions[BTC]
    assert position.side == "long"
    assert position.qty == pytest.approx(0.070)
    # Filled at the bounded-slippage limit, not the raw signal price.
    assert position.entry_price == pytest.approx(64_306.8)

    stops = paper.open_orders_of(BTC, "stop")
    tps = paper.open_orders_of(BTC, "tp")
    assert len(stops) == 1
    assert len(tps) == 1

    stop_order = stops[0]
    assert stop_order.reduce_only
    assert stop_order.side == "sell"  # reduces a long
    assert stop_order.trigger_price == pytest.approx(STOP)
    assert stop_order.amount == pytest.approx(0.070)

    tp_order = tps[0]
    assert tp_order.reduce_only
    assert tp_order.side == "sell"
    assert tp_order.price == pytest.approx(TARGET)
    assert tp_order.amount == pytest.approx(0.070)

    local = store.get_open_position(BTC)
    assert local is not None
    assert local.stop_order_id == stop_order.id
    assert local.tp_order_id == tp_order.id
    assert local.stop_price == pytest.approx(STOP)


async def test_stop_fill_then_reconciler_cancels_the_sibling_take_profit(
    engine, reconciler, paper, store, make_payload
):
    payload = make_payload()
    engine.claim(payload)
    await engine.execute_entry(payload)

    assert len(paper.open_orders_of(BTC, "tp")) == 1

    # The stop triggers and fills; the position is gone.
    paper.trigger_stop(BTC)
    assert BTC not in paper.positions
    # The venue left the take-profit resting - this is the OCO gap.
    assert len(paper.open_orders_of(BTC, "tp")) == 1

    report = await reconciler.reconcile_once()

    assert report.ok
    assert paper.open_orders_of(BTC, "tp") == []  # sibling cancelled
    assert store.get_open_position(BTC) is None

    closed = store.recent_closed_positions()
    assert len(closed) == 1
    # Entry 64306.8, stopped at 63500, 0.07 units.
    assert closed[0].realized_pnl == pytest.approx((STOP - 64_306.8) * 0.070)
    assert closed[0].realized_pnl < 0


async def test_take_profit_fill_then_reconciler_cancels_the_sibling_stop(
    engine, reconciler, paper, store, make_payload
):
    payload = make_payload()
    engine.claim(payload)
    await engine.execute_entry(payload)

    paper.fill_take_profit(BTC)
    assert BTC not in paper.positions
    assert len(paper.open_orders_of(BTC, "stop")) == 1

    report = await reconciler.reconcile_once()

    assert report.ok
    assert paper.open_orders_of(BTC, "stop") == []
    closed = store.recent_closed_positions()
    assert closed[0].realized_pnl == pytest.approx((TARGET - 64_306.8) * 0.070)
    assert closed[0].realized_pnl > 0


async def test_partial_fill_sizes_exits_to_the_actual_filled_quantity(
    settings, specs, store, risk, notifier, make_payload
):
    """Half the entry fills before the timeout; exits must match reality."""
    paper = PaperExchange(settings, equity=10_000.0, specs=specs, auto_fill_ratio=0.5)
    paper.set_price(BTC, ENTRY)
    engine = Engine(settings, paper, store, risk, notifier)

    payload = make_payload()
    engine.claim(payload)
    result = await engine.execute_entry(payload)

    assert result.status == "filled"
    assert result.qty == pytest.approx(0.035)
    assert paper.positions[BTC].qty == pytest.approx(0.035)

    # The unfilled remainder was cancelled rather than chased.
    assert any(call[0] == "cancel_order" for call in paper.calls)

    assert paper.open_orders_of(BTC, "stop")[0].amount == pytest.approx(0.035)
    assert paper.open_orders_of(BTC, "tp")[0].amount == pytest.approx(0.035)
    assert store.get_open_position(BTC).qty == pytest.approx(0.035)


async def test_no_fill_abandons_the_signal_without_a_position(
    settings, specs, store, risk, notifier, make_payload
):
    paper = PaperExchange(settings, equity=10_000.0, specs=specs, auto_fill_entry=False)
    paper.set_price(BTC, ENTRY)
    engine = Engine(settings, paper, store, risk, notifier)

    payload = make_payload()
    engine.claim(payload)
    result = await engine.execute_entry(payload)

    assert result.status == "abandoned"
    assert BTC not in paper.positions
    assert store.get_open_position(BTC) is None
    assert paper.open_orders_of(BTC, "stop") == []


async def test_market_that_ran_away_is_not_chased(engine, paper, make_payload):
    paper.set_price(BTC, ENTRY * 1.01)  # 1% away, tolerance is 0.15%
    payload = make_payload()
    engine.claim(payload)

    result = await engine.execute_entry(payload)

    assert result.status == "rejected"
    assert "slippage_exceeded" in result.reason
    assert not [c for c in paper.calls if c[0] == "create_entry_limit"]


async def test_unknown_symbol_is_rejected(engine, paper, make_payload):
    payload = make_payload(symbol="SOLUSDT.P", signal_id="SOLUSDT.P-60-1")
    engine.claim(payload)

    result = await engine.execute_entry(payload)

    assert result.status == "rejected"
    assert "unknown_symbol" in result.reason
    assert not [c for c in paper.calls if c[0] == "create_entry_limit"]


async def test_short_entry_places_buy_side_exits(engine, paper, store, make_payload):
    payload = make_payload(
        side="short",
        symbol="ETHUSDT.P",
        signal_id="ETHUSDT.P-60-1",
        entry=3_000.0,
        stop=3_030.0,
        target=2_910.0,
    )
    engine.claim(payload)
    result = await engine.execute_entry(payload)

    assert result.status == "filled"
    eth = "ETH/USDT:USDT"
    assert paper.positions[eth].side == "short"
    assert paper.open_orders_of(eth, "stop")[0].side == "buy"
    assert paper.open_orders_of(eth, "tp")[0].side == "buy"
    assert store.get_open_position(eth).side == "short"


async def test_position_and_orders_are_persisted(engine, store, make_payload):
    payload = make_payload()
    engine.claim(payload)
    await engine.execute_entry(payload)

    orders = store.orders_for_signal(payload.signal_id)
    purposes = {o["purpose"] for o in orders}
    assert purposes == {"entry", "stop", "take_profit"}

    signal = store.get_signal(payload.signal_id)
    assert signal["status"] == "filled"
