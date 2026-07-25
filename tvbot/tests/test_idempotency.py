"""Idempotency: TradingView resends alerts, and one alert must mean one order."""

from __future__ import annotations

import asyncio

from app.exchange import make_client_order_id

from .conftest import BTC


def test_claim_signal_is_atomic(store):
    assert store.claim_signal("s1", "{}", "BTCUSDT.P", "long") is True
    assert store.claim_signal("s1", "{}", "BTCUSDT.P", "long") is False
    assert store.count_signals() == 1


async def test_concurrent_duplicate_deliveries_yield_exactly_one_claim(store):
    """Two deliveries racing through the handler must not both win."""
    results = await asyncio.gather(
        *[
            asyncio.to_thread(store.claim_signal, "race-1", "{}", "BTCUSDT.P", "long")
            for _ in range(16)
        ]
    )
    assert sum(results) == 1
    assert store.count_signals() == 1


async def test_duplicate_webhook_places_only_one_entry_order(engine, paper, make_payload):
    payload = make_payload()

    assert engine.claim(payload) is True
    result = await engine.execute_entry(payload)
    assert result.status == "filled"

    entry_calls = [c for c in paper.calls if c[0] == "create_entry_limit"]
    assert len(entry_calls) == 1

    # Redelivery of the identical alert: the claim fails, so main.py returns
    # 200 without ever entering the execution pipeline.
    assert engine.claim(payload) is False

    entry_calls = [c for c in paper.calls if c[0] == "create_entry_limit"]
    assert len(entry_calls) == 1


async def test_client_order_id_is_deterministic_and_venue_dedupes(paper):
    """Defence in depth for the case where our own retry is the duplicate.

    If create_order times out on the network but actually landed, the retry
    presents the same clientOrderId and the venue rejects it rather than
    opening a second position.
    """
    coid = make_client_order_id("e", "BTCUSDT.P-60-1730812800000")
    assert coid == make_client_order_id("e", "BTCUSDT.P-60-1730812800000")
    assert len(coid) <= 36

    first = await paper.create_entry_limit(BTC, "buy", 0.01, 64_000.0, coid)
    second = await paper.create_entry_limit(BTC, "buy", 0.01, 64_000.0, coid)
    assert first.id == second.id
    assert paper.positions[BTC].qty == 0.01  # not 0.02


def test_different_signals_get_different_client_order_ids():
    assert make_client_order_id("e", "sig-a") != make_client_order_id("e", "sig-b")
    # Purpose prefixes keep entry/stop/tp ids distinct for the same signal.
    assert make_client_order_id("e", "sig-a") != make_client_order_id("s", "sig-a")
    assert make_client_order_id("s", "sig-a") != make_client_order_id("s", "sig-a", nonce=7)


def test_rejected_signal_is_still_recorded_so_it_cannot_be_retried(store):
    """A rejected alert keeps its claim; a resend must not get a second look."""
    assert store.claim_signal("rejected-1", "{}", "BTCUSDT.P", "long") is True
    assert store.claim_signal("rejected-1", "{}", "BTCUSDT.P", "long") is False
