"""Position sizing: rounding edges, exchange minimums, leverage cap."""

from __future__ import annotations

import pytest

from app.sizing import (
    MarketSpec,
    floor_to_step,
    round_to_step,
    size_position,
    slippage_bounded_limit_price,
    validate_rr,
    validate_stop_distance,
    within_slippage,
)

BTC_SPEC = MarketSpec(
    "BTC/USDT:USDT", amount_step=0.001, amount_min=0.001, price_step=0.1, min_notional=5.0
)


# --------------------------------------------------------------------- rounding
def test_floor_to_step_survives_binary_float_representation():
    """0.29 / 0.001 is 289.99999999999994 in binary floating point.

    A naive ``//`` implementation silently loses a whole lot step here, which on
    a real order is a permanent, invisible under-fill of every position.
    """
    assert floor_to_step(0.29, 0.001) == pytest.approx(0.29)
    assert floor_to_step(0.07, 0.001) == pytest.approx(0.07)
    assert floor_to_step(1.1, 0.1) == pytest.approx(1.1)


def test_floor_to_step_always_rounds_down():
    assert floor_to_step(0.0709999, 0.001) == pytest.approx(0.070)
    assert floor_to_step(0.0700001, 0.001) == pytest.approx(0.070)
    assert floor_to_step(0.9999, 1.0) == pytest.approx(0.0)


def test_round_to_step_goes_to_nearest():
    assert round_to_step(64306.8157, 0.1) == pytest.approx(64306.8)
    assert round_to_step(64306.86, 0.1) == pytest.approx(64306.9)


# ----------------------------------------------------------------- happy path
def test_basic_sizing_risks_the_configured_fraction():
    result = size_position(
        equity=10_000.0,
        risk_pct=0.005,
        entry=64210.5,
        stop=63500.0,
        spec=BTC_SPEC,
        max_leverage=3.0,
    )
    assert result.ok
    # 50 USDT budget / 710.5 per-unit risk = 0.070373..., floored to the lot step.
    assert result.qty == pytest.approx(0.070)
    assert result.notional == pytest.approx(0.070 * 64210.5)
    # Realised risk is at or just under the 50 USDT budget, never over.
    assert result.risk_cash == pytest.approx(0.070 * 710.5)
    assert result.risk_cash <= 10_000.0 * 0.005
    assert not result.clamped_by_leverage
    assert result.leverage == pytest.approx(0.4494735)


def test_short_sizing_matches_long_for_equal_stop_distance():
    long_side = size_position(10_000.0, 0.005, 100.0, 99.0, BTC_SPEC, 3.0)
    short_side = size_position(10_000.0, 0.005, 100.0, 101.0, BTC_SPEC, 3.0)
    assert long_side.qty == pytest.approx(short_side.qty)


# ------------------------------------------------------------ exchange minimums
def test_quantity_below_lot_step_is_rejected_not_rounded_up():
    result = size_position(
        equity=100.0,  # 0.50 USDT of risk budget
        risk_pct=0.005,
        entry=64210.5,
        stop=63500.0,
        spec=BTC_SPEC,
        max_leverage=3.0,
    )
    assert not result.ok
    assert "rounds to zero" in result.reason


def test_quantity_below_exchange_minimum_is_rejected():
    fine_spec = MarketSpec(
        "X/USDT:USDT", amount_step=0.0001, amount_min=0.01, price_step=0.1, min_notional=0.0
    )
    result = size_position(100.0, 0.005, 64210.5, 63500.0, fine_spec, 3.0)
    assert not result.ok
    assert "below exchange minimum" in result.reason
    # The critical property: it did not round UP to reach the minimum.
    assert result.qty < fine_spec.amount_min


def test_notional_below_min_notional_is_rejected():
    spec = MarketSpec(
        "X/USDT:USDT", amount_step=0.001, amount_min=0.001, price_step=0.1, min_notional=10_000.0
    )
    result = size_position(10_000.0, 0.005, 64210.5, 63500.0, spec, 3.0)
    assert not result.ok
    assert "below exchange minimum" in result.reason or "notional" in result.reason


# ----------------------------------------------------------------- leverage cap
def test_leverage_cap_clamps_quantity_downward():
    """A very tight stop demands more notional than the cap allows."""
    result = size_position(
        equity=10_000.0,
        risk_pct=0.005,
        entry=100.0,
        stop=99.9,  # 0.1% stop -> 5x implied leverage at 0.5% risk
        spec=BTC_SPEC,
        max_leverage=3.0,
    )
    assert result.ok
    assert result.clamped_by_leverage
    assert result.qty == pytest.approx(300.0)  # 10_000 * 3 / 100
    assert result.notional == pytest.approx(30_000.0)
    assert result.leverage <= 3.0 + 1e-9


def test_leverage_cap_never_binds_inside_the_configured_stop_band():
    """At the 0.4% minimum stop distance, implied leverage is 1.25x."""
    result = size_position(10_000.0, 0.005, 100.0, 99.6, BTC_SPEC, 3.0)
    assert result.ok
    assert not result.clamped_by_leverage
    assert result.leverage == pytest.approx(1.25, rel=1e-3)


def test_max_amount_is_respected():
    spec = MarketSpec(
        "X/USDT:USDT", amount_step=0.001, amount_min=0.001, price_step=0.1, max_amount=0.01
    )
    result = size_position(10_000.0, 0.005, 64210.5, 63500.0, spec, 3.0)
    assert result.ok
    assert result.qty == pytest.approx(0.01)


# --------------------------------------------------------------- bad arguments
@pytest.mark.parametrize(
    ("equity", "entry", "stop", "risk_pct"),
    [
        (0.0, 100.0, 99.0, 0.005),
        (-1.0, 100.0, 99.0, 0.005),
        (10_000.0, 0.0, 99.0, 0.005),
        (10_000.0, 100.0, 100.0, 0.005),  # zero stop distance
        (10_000.0, 100.0, 99.0, 0.0),
        (10_000.0, 100.0, 99.0, 1.5),
    ],
)
def test_invalid_inputs_are_rejected(equity, entry, stop, risk_pct):
    result = size_position(equity, risk_pct, entry, stop, BTC_SPEC, 3.0)
    assert not result.ok
    assert result.qty == 0.0 or result.reason


# ------------------------------------------------------------------ RR / regime
def test_validate_rr_accepts_the_target_band():
    ok, rr, _ = validate_rr(64210.5, 63500.0, 66341.5, 2.9, 3.1)
    assert ok
    assert rr == pytest.approx(3.0, abs=0.01)


@pytest.mark.parametrize("target", [65000.0, 70000.0])
def test_validate_rr_rejects_outside_band(target):
    ok, _rr, reason = validate_rr(64210.5, 63500.0, target, 2.9, 3.1)
    assert not ok
    assert "outside accepted band" in reason


def test_validate_rr_rejects_zero_risk():
    ok, _rr, reason = validate_rr(100.0, 100.0, 130.0, 2.9, 3.1)
    assert not ok
    assert "zero" in reason


def test_validate_stop_distance_band():
    ok, pct, _ = validate_stop_distance(64210.5, 63500.0, 0.004, 0.03)
    assert ok
    assert pct == pytest.approx(0.011065, rel=1e-3)

    too_tight, _, reason = validate_stop_distance(100.0, 99.9, 0.004, 0.03)
    assert not too_tight
    assert "below minimum" in reason

    too_wide, _, reason = validate_stop_distance(100.0, 95.0, 0.004, 0.03)
    assert not too_wide
    assert "above maximum" in reason


# -------------------------------------------------------------------- slippage
def test_slippage_bounded_limit_price_crosses_the_spread_by_a_bounded_amount():
    long_px = slippage_bounded_limit_price(64210.5, True, 0.0015, 0.1)
    short_px = slippage_bounded_limit_price(64210.5, False, 0.0015, 0.1)
    assert long_px == pytest.approx(64306.8)
    assert short_px == pytest.approx(64114.2)
    assert long_px > 64210.5 > short_px


def test_within_slippage_bounds():
    assert within_slippage(64210.5, 64250.0, 0.0015)
    assert not within_slippage(64210.5, 64500.0, 0.0015)
    assert not within_slippage(0.0, 100.0, 0.0015)
