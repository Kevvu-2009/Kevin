"""Crash recovery and the reconciliation invariant.

The invariant under test: every open position has a live reduce-only stop on
the exchange, and the bot refuses to accept new signals until it has verified
that.
"""

from __future__ import annotations

import pytest

from app.engine import Engine
from app.exchange import PaperExchange
from app.notify import Level
from app.reconcile import Reconciler
from app.risk import RiskManager
from app.state import Store

from .conftest import BTC, ENTRY, STOP


def _messages(notifier) -> str:
    return " | ".join(text for _level, text in notifier.sent_messages)


def test_reconciler_starts_refusing_webhooks(reconciler):
    """Nothing may trade before the first successful reconciliation."""
    assert reconciler.ready is False


async def test_startup_reconcile_marks_ready(reconciler):
    report = await reconciler.startup()
    assert report.ok
    assert reconciler.ready is True


async def test_untracked_position_is_adopted_and_given_a_stop(
    reconciler, paper, store, notifier, settings
):
    """Crash between the entry fill and the stop placement.

    The venue holds a position we have no record of, and no protective order
    exists. Reconciliation must adopt it and protect it immediately.
    """
    paper.seed_position(BTC, "long", 0.05, 64_000.0)
    assert store.get_open_position(BTC) is None

    report = await reconciler.reconcile_once()

    assert report.ok
    local = store.get_open_position(BTC)
    assert local is not None
    assert local.adopted is True
    assert local.qty == pytest.approx(0.05)

    stops = paper.open_orders_of(BTC, "stop")
    assert len(stops) == 1
    assert stops[0].amount == pytest.approx(0.05)
    # Synthesised at the widest stop distance the risk config permits.
    assert stops[0].trigger_price == pytest.approx(
        64_000.0 * (1 - settings.stop_dist_max_pct), rel=1e-6
    )

    assert any(level is Level.CRITICAL for level, _ in notifier.sent_messages)
    assert "ADOPTED UNTRACKED POSITION" in _messages(notifier)


async def test_missing_stop_is_replaced_and_alerted(
    engine, reconciler, paper, store, notifier, make_payload
):
    """The venue dropped our conditional order while the position was live."""
    payload = make_payload()
    engine.claim(payload)
    await engine.execute_entry(payload)

    original = paper.open_orders_of(BTC, "stop")[0]
    original.status = "canceled"  # simulate the venue dropping it
    assert paper.open_orders_of(BTC, "stop") == []

    report = await reconciler.reconcile_once()

    replacements = paper.open_orders_of(BTC, "stop")
    assert len(replacements) == 1
    assert replacements[0].id != original.id
    assert replacements[0].trigger_price == pytest.approx(STOP)
    assert replacements[0].amount == pytest.approx(0.070)
    assert store.get_open_position(BTC).stop_order_id == replacements[0].id
    assert any("replaced missing stop" in r for r in report.repairs)
    assert "STOP WAS MISSING" in _messages(notifier)


async def test_mis_sized_stop_is_rebuilt_to_match_the_position(
    engine, reconciler, paper, store, make_payload
):
    """A stop covering less than the position leaves a naked remainder."""
    payload = make_payload()
    engine.claim(payload)
    await engine.execute_entry(payload)

    stop = paper.open_orders_of(BTC, "stop")[0]
    stop.amount = 0.030  # drifted away from the 0.070 position

    report = await reconciler.reconcile_once()

    stops = paper.open_orders_of(BTC, "stop")
    assert len(stops) == 1
    assert stops[0].amount == pytest.approx(0.070)
    assert any("mis-sized stop" in r for r in report.repairs)


async def test_local_position_is_closed_when_the_venue_is_flat(reconciler, paper, store):
    """We crashed after the exit filled; local state still thinks we are in."""
    store.open_position(
        symbol=BTC,
        signal_id="orphan-1",
        side="long",
        qty=0.070,
        entry_price=64_000.0,
        stop_price=STOP,
        target_price=66_000.0,
    )
    assert BTC not in paper.positions

    report = await reconciler.reconcile_once()

    assert report.ok
    assert store.get_open_position(BTC) is None
    assert len(store.recent_closed_positions()) == 1


async def test_crash_mid_position_restart_restores_state(
    settings, specs, notifier, make_payload
):
    """Full crash-and-restart cycle.

    The process dies while a protected position is live. On restart a brand new
    Store is opened against the same file and reconciled against the venue.
    """
    # --- first process ---------------------------------------------------
    store_before = Store(settings.db_path)
    paper = PaperExchange(settings, equity=10_000.0, specs=specs)
    paper.set_price(BTC, ENTRY)
    engine = Engine(settings, paper, store_before, RiskManager(settings, store_before), notifier)

    payload = make_payload()
    engine.claim(payload)
    result = await engine.execute_entry(payload)
    assert result.status == "filled"

    store_before.close()  # crash: process gone, venue state untouched

    # --- restarted process ----------------------------------------------
    store_after = Store(settings.db_path)
    try:
        reconciler = Reconciler(settings, paper, store_after, notifier)
        report = await reconciler.startup()

        assert report.ok
        assert reconciler.ready is True

        restored = store_after.get_open_position(BTC)
        assert restored is not None
        assert restored.qty == pytest.approx(0.070)
        assert restored.adopted is False  # it was tracked, not adopted
        assert restored.stop_price == pytest.approx(STOP)

        # The stop survived and is still the right size: no repair was needed.
        stops = paper.open_orders_of(BTC, "stop")
        assert len(stops) == 1
        assert stops[0].amount == pytest.approx(0.070)
        assert report.repairs == []

        # Idempotency survives the restart: the same alert cannot re-fire.
        assert store_after.claim_signal(payload.signal_id, "{}", "BTCUSDT.P", "long") is False
    finally:
        store_after.close()


async def test_reconcile_is_idempotent(engine, reconciler, paper, make_payload):
    """Running the loop repeatedly must not churn orders."""
    payload = make_payload()
    engine.claim(payload)
    await engine.execute_entry(payload)

    first = await reconciler.reconcile_once()
    second = await reconciler.reconcile_once()

    assert first.repairs == []
    assert second.repairs == []
    assert len(paper.open_orders_of(BTC, "stop")) == 1
    assert len(paper.open_orders_of(BTC, "tp")) == 1


async def test_position_quantity_drift_is_corrected(engine, reconciler, paper, store, make_payload):
    payload = make_payload()
    engine.claim(payload)
    await engine.execute_entry(payload)

    # The venue reports less than we think we hold (e.g. partial liquidation).
    paper.positions[BTC].qty = 0.050

    report = await reconciler.reconcile_once()

    assert store.get_open_position(BTC).qty == pytest.approx(0.050)
    assert any("qty corrected" in r for r in report.repairs)
    # And the protective orders were resized to match.
    assert paper.open_orders_of(BTC, "stop")[0].amount == pytest.approx(0.050)
