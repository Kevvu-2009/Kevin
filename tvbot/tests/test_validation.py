"""Payload schema validation, staleness, and the pre-trade risk gates."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from app.models import WebhookPayload, timeframe_to_ms
from app.risk import RiskManager

from .conftest import BTC, ENTRY, SECRET, STOP, TARGET


# ------------------------------------------------------------- schema geometry
def test_long_with_stop_above_entry_is_rejected(make_payload):
    with pytest.raises(ValidationError, match="long requires stop < entry < target"):
        make_payload(stop=ENTRY + 100)


def test_long_with_target_below_entry_is_rejected(make_payload):
    with pytest.raises(ValidationError, match="long requires stop < entry < target"):
        make_payload(target=ENTRY - 100)


def test_valid_short_geometry_is_accepted(make_payload):
    payload = make_payload(side="short", entry=ENTRY, stop=ENTRY + 710.5, target=ENTRY - 2131.0)
    assert payload.side.value == "short"
    assert payload.rr == pytest.approx(3.0, abs=0.01)
    assert payload.side.entry_order_side == "sell"
    assert payload.side.exit_order_side == "buy"


def test_short_with_inverted_geometry_is_rejected(make_payload):
    with pytest.raises(ValidationError, match="short requires target < entry < stop"):
        make_payload(side="short")  # long geometry with a short side


def test_unknown_fields_are_rejected(make_payload):
    with pytest.raises(ValidationError):
        make_payload(qty=1.5)


def test_negative_prices_are_rejected(make_payload):
    with pytest.raises(ValidationError):
        make_payload(entry=-1.0)


def test_seconds_epoch_is_rejected_as_implausible():
    """A common integration mistake: sending seconds instead of milliseconds."""
    with pytest.raises(ValidationError, match="plausible millisecond epoch"):
        WebhookPayload.model_validate(
            {
                "secret": SECRET,
                "signal_id": "x-1",
                "action": "entry",
                "side": "long",
                "symbol": "BTCUSDT.P",
                "entry": ENTRY,
                "stop": STOP,
                "target": TARGET,
                "timeframe": "60",
                "bar_time": 1_730_812_800,  # seconds, not ms
            }
        )


def test_secret_is_excluded_from_log_payloads(make_payload):
    payload = make_payload()
    assert "secret" not in payload.redacted()
    assert "secret" not in payload.model_dump_json(exclude={"secret"})


# ---------------------------------------------------------------- timeframe
@pytest.mark.parametrize(
    ("timeframe", "expected_ms"),
    [("1", 60_000), ("60", 3_600_000), ("240", 14_400_000), ("D", 86_400_000), ("30S", 30_000)],
)
def test_timeframe_to_ms(timeframe, expected_ms):
    assert timeframe_to_ms(timeframe) == expected_ms


def test_timeframe_to_ms_returns_none_for_garbage():
    assert timeframe_to_ms("banana") is None
    assert timeframe_to_ms("") is None


# ------------------------------------------------------------------- staleness
def test_bar_time_alone_is_the_bar_open_and_must_not_be_used_directly(settings, store):
    """Regression guard for the highest-value bug in this system.

    TradingView's ``bar_time`` is the bar's OPEN. On a 1H chart a freshly closed
    bar carries a ``bar_time`` that is already 3,600,000 ms old. Comparing it
    against a 90-second window would reject every single signal; widening the
    window to compensate would accept genuinely hour-stale replays.
    """
    now_ms = int(time.time() * 1000)
    bar_open = now_ms - 3_600_000 - 5_000  # bar closed 5 seconds ago

    payload = WebhookPayload.model_validate(
        {
            "secret": SECRET,
            "signal_id": "x-1",
            "action": "entry",
            "side": "long",
            "symbol": "BTCUSDT.P",
            "entry": ENTRY,
            "stop": STOP,
            "target": TARGET,
            "timeframe": "60",
            "bar_time": bar_open,  # no bar_close_time: forces the fallback path
        }
    )

    # The naive interpretation would look 1 hour stale...
    assert now_ms - payload.bar_time > settings.max_signal_age_sec * 1000
    # ...but the derived close time is 5 seconds old, and is accepted.
    assert payload.effective_close_ms() == pytest.approx(now_ms - 5_000, abs=10)
    decision = RiskManager(settings, store).check_staleness(payload, now_ms)
    assert decision.allowed


def test_explicit_bar_close_time_is_preferred(make_payload):
    now_ms = int(time.time() * 1000)
    payload = make_payload(bar_close_time=now_ms - 1_000)
    assert payload.effective_close_ms() == now_ms - 1_000
    assert payload.age_ms(now_ms) == 1_000


def test_stale_signal_is_rejected(settings, store, make_payload):
    now_ms = int(time.time() * 1000)
    payload = make_payload(bar_close_time=now_ms - 200_000)
    decision = RiskManager(settings, store).check_staleness(payload, now_ms)
    assert not decision.allowed
    assert decision.code == "stale_signal"


def test_future_signal_is_rejected_as_clock_skew(settings, store, make_payload):
    now_ms = int(time.time() * 1000)
    payload = make_payload(bar_close_time=now_ms + 120_000)
    decision = RiskManager(settings, store).check_staleness(payload, now_ms)
    assert not decision.allowed
    assert decision.code == "future_signal"


def test_bar_close_time_must_follow_bar_time(make_payload):
    with pytest.raises(ValidationError, match="strictly after"):
        make_payload(bar_time=1_730_812_800_000, bar_close_time=1_730_812_700_000)


# ------------------------------------------------------------------ risk gates
def test_rr_outside_band_is_rejected(settings, store, make_payload):
    payload = make_payload(target=ENTRY + 710.5 * 2.0)  # RR 2.0
    decision = RiskManager(settings, store).evaluate_entry(payload, BTC, 10_000.0)
    assert not decision.allowed
    assert decision.code == "bad_rr"


def test_stop_distance_outside_band_is_rejected(settings, store, make_payload):
    # 0.1% stop: passes RR, fails the volatility-regime gate.
    entry, stop = 100.0, 99.9
    payload = make_payload(entry=entry, stop=stop, target=entry + 3 * (entry - stop))
    decision = RiskManager(settings, store).evaluate_entry(payload, BTC, 10_000.0)
    assert not decision.allowed
    assert decision.code == "bad_stop_distance"


def test_wrong_timeframe_is_rejected(settings, store, make_payload):
    payload = make_payload(timeframe="15")
    decision = RiskManager(settings, store).evaluate_entry(payload, BTC, 10_000.0)
    assert not decision.allowed
    assert decision.code == "wrong_timeframe"


def test_halt_file_blocks_new_entries(settings, store, make_payload, tmp_path):
    manager = RiskManager(settings, store)
    assert manager.evaluate_entry(make_payload(), BTC, 10_000.0).allowed

    (tmp_path / "HALT").write_text("stop trading")
    decision = manager.evaluate_entry(make_payload(), BTC, 10_000.0)
    assert not decision.allowed
    assert decision.code == "halted"


def test_daily_loss_limit_halts_new_entries(settings, store, make_payload):
    manager = RiskManager(settings, store)
    manager.daily_anchor_equity(10_000.0)  # anchor the day at 10k

    assert manager.evaluate_entry(make_payload(), BTC, 9_800.0).allowed  # -2%

    decision = manager.evaluate_entry(make_payload(), BTC, 9_650.0)  # -3.5%
    assert not decision.allowed
    assert decision.code == "daily_loss_limit"


def test_daily_anchor_survives_restart(settings, store):
    """A restart mid-drawdown must not hand the bot a fresh loss budget."""
    first = RiskManager(settings, store)
    first.daily_anchor_equity(10_000.0)

    restarted = RiskManager(settings, store)
    assert restarted.daily_anchor_equity(9_700.0) == pytest.approx(10_000.0)
    assert restarted.daily_drawdown_pct(9_700.0) == pytest.approx(-0.03)


def test_consecutive_losses_halt(settings, store, make_payload):
    for i in range(settings.max_consecutive_losses):
        pid = store.open_position(
            symbol=f"X{i}/USDT:USDT",
            signal_id=f"s{i}",
            side="long",
            qty=1.0,
            entry_price=100.0,
            stop_price=99.0,
            target_price=103.0,
        )
        store.close_position(pid, realized_pnl=-10.0)

    manager = RiskManager(settings, store)
    assert manager.consecutive_losses() == settings.max_consecutive_losses
    decision = manager.evaluate_entry(make_payload(), BTC, 10_000.0)
    assert not decision.allowed
    assert decision.code == "consecutive_losses"


def test_a_win_resets_the_consecutive_loss_counter(settings, store):
    for pnl in (-10.0, -10.0, +30.0, -10.0):
        pid = store.open_position(
            symbol=f"X{pnl}/USDT:USDT",
            signal_id=f"s{pnl}",
            side="long",
            qty=1.0,
            entry_price=100.0,
            stop_price=99.0,
            target_price=103.0,
        )
        store.close_position(pid, realized_pnl=pnl)
    assert RiskManager(settings, store).consecutive_losses() == 1


def test_max_total_positions_blocks_a_third_symbol(settings, store, make_payload):
    for i, symbol in enumerate(("A/USDT:USDT", "B/USDT:USDT")):
        store.open_position(
            symbol=symbol,
            signal_id=f"s{i}",
            side="long",
            qty=1.0,
            entry_price=100.0,
            stop_price=99.0,
            target_price=103.0,
        )
    decision = RiskManager(settings, store).evaluate_entry(make_payload(), BTC, 10_000.0)
    assert not decision.allowed
    assert decision.code == "max_positions"


def test_existing_position_on_the_same_symbol_blocks_a_second(settings, store, make_payload):
    store.open_position(
        symbol=BTC,
        signal_id="s0",
        side="long",
        qty=1.0,
        entry_price=100.0,
        stop_price=99.0,
        target_price=103.0,
    )
    decision = RiskManager(settings, store).evaluate_entry(make_payload(), BTC, 10_000.0)
    assert not decision.allowed
    assert decision.code == "position_exists"
