"""Position sizing. Pure functions, no IO, no exchange calls.

Every number the exchange receives is computed here from server-side inputs.
Sizes present in a webhook payload are never trusted and never read.

Two rules in this module are load-bearing and must not be "helpfully" relaxed:

1. **Quantity is always floored to the lot step, never rounded up.** Rounding
   up to reach the exchange minimum would silently exceed the risk budget.
   If the floored quantity is below a minimum, the signal is rejected.
2. **The leverage cap clamps quantity downward, it does not scale it up.**
   Clamping reduces realised risk below target, which is the safe direction;
   the result records ``clamped_by_leverage`` so the caller can log it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, InvalidOperation

# Guard against float noise when comparing against caps.
_EPS = 1e-12


@dataclass(frozen=True)
class MarketSpec:
    """The exchange's trading rules for one instrument.

    Populated from ccxt market metadata by ``exchange.ExchangeClient``.
    """

    symbol: str
    amount_step: float  # lot size increment, in base units
    amount_min: float  # smallest tradeable quantity
    price_step: float  # tick size
    min_notional: float = 0.0  # smallest order value in quote currency
    max_amount: float | None = None
    contract_size: float = 1.0

    def __post_init__(self) -> None:
        if self.amount_step <= 0:
            raise ValueError(f"{self.symbol}: amount_step must be positive")
        if self.price_step <= 0:
            raise ValueError(f"{self.symbol}: price_step must be positive")


@dataclass(frozen=True)
class SizingResult:
    ok: bool
    qty: float = 0.0
    notional: float = 0.0
    risk_cash: float = 0.0
    leverage: float = 0.0
    clamped_by_leverage: bool = False
    reason: str = ""


def _dec(value: float) -> Decimal:
    # str() round-trip avoids inheriting binary float noise into the Decimal.
    return Decimal(str(value))


def floor_to_step(value: float, step: float) -> float:
    """Round ``value`` DOWN to the nearest multiple of ``step``.

    Uses Decimal because ``0.29 // 0.001`` in binary floats lands on 289, not
    290 - which on a 0.001-lot instrument silently loses a full lot step.
    """
    if step <= 0:
        return value
    try:
        quotient = (_dec(value) / _dec(step)).to_integral_value(rounding=ROUND_FLOOR)
        return float(quotient * _dec(step))
    except (InvalidOperation, ZeroDivisionError):  # pragma: no cover - defensive
        return 0.0


def round_to_step(value: float, step: float) -> float:
    """Round ``value`` to the NEAREST multiple of ``step``.

    Used for trigger/limit prices, where the sub-tick difference is immaterial
    (a 0.1 tick against a stop hundreds of dollars away) but sending an
    off-tick price is an outright exchange rejection.
    """
    if step <= 0:
        return value
    try:
        quotient = (_dec(value) / _dec(step)).to_integral_value(rounding=ROUND_HALF_EVEN)
        return float(quotient * _dec(step))
    except (InvalidOperation, ZeroDivisionError):  # pragma: no cover - defensive
        return value


def validate_rr(
    entry: float,
    stop: float,
    target: float,
    rr_min: float,
    rr_max: float,
) -> tuple[bool, float, str]:
    """Check the implied reward:risk sits inside the accepted band.

    Returns ``(ok, rr, reason)``. A payload outside the band means the alert
    was malformed or the Pine script was edited without updating the server -
    either way it is not the strategy we validated, so it must not trade.
    """
    risk = abs(entry - stop)
    if risk <= 0:
        return False, 0.0, "stop equals entry: risk per unit is zero"
    rr = abs(target - entry) / risk
    if not rr_min <= rr <= rr_max:
        return False, rr, f"implied RR {rr:.3f} outside accepted band [{rr_min}, {rr_max}]"
    return True, rr, ""


def validate_stop_distance(
    entry: float,
    stop: float,
    min_pct: float,
    max_pct: float,
) -> tuple[bool, float, str]:
    """Re-check the volatility-regime gate server-side.

    The Pine script already applies this, but the server must not depend on
    the client having done so: stop distance is the denominator of the sizing
    formula, and a 0.05% stop at 0.5% risk demands 10x notional.
    """
    if entry <= 0:
        return False, 0.0, "entry price must be positive"
    pct = abs(entry - stop) / entry
    if pct < min_pct:
        return False, pct, f"stop distance {pct:.4%} below minimum {min_pct:.4%}"
    if pct > max_pct:
        return False, pct, f"stop distance {pct:.4%} above maximum {max_pct:.4%}"
    return True, pct, ""


def size_position(
    equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
    spec: MarketSpec,
    max_leverage: float,
) -> SizingResult:
    """Compute the order quantity for one signal.

        qty = (equity * risk_pct) / |entry - stop|

    then floor to the lot step and verify it against the exchange minimums and
    the leverage cap.
    """
    if equity <= 0:
        return SizingResult(ok=False, reason=f"non-positive equity ({equity})")
    if entry <= 0:
        return SizingResult(ok=False, reason=f"non-positive entry price ({entry})")
    if not 0 < risk_pct <= 1:
        return SizingResult(ok=False, reason=f"risk_pct {risk_pct} outside (0, 1]")
    if max_leverage <= 0:
        return SizingResult(ok=False, reason=f"max_leverage {max_leverage} must be positive")

    per_unit_risk = abs(entry - stop)
    if per_unit_risk <= 0:
        return SizingResult(ok=False, reason="stop equals entry: risk per unit is zero")

    risk_cash = equity * risk_pct
    raw_qty = risk_cash / per_unit_risk

    # Leverage cap, applied to quantity before rounding so the floor below can
    # only take us further under the cap.
    unit_notional = entry * spec.contract_size
    max_qty_by_leverage = (equity * max_leverage) / unit_notional
    target_qty = min(raw_qty, max_qty_by_leverage)
    clamped = target_qty < raw_qty - _EPS

    if spec.max_amount is not None:
        target_qty = min(target_qty, spec.max_amount)

    qty = floor_to_step(target_qty, spec.amount_step)

    if qty <= 0:
        return SizingResult(
            ok=False,
            clamped_by_leverage=clamped,
            reason=(
                f"quantity rounds to zero at lot step {spec.amount_step} "
                f"(wanted {target_qty:.10f}); equity too small for this stop distance"
            ),
        )
    if qty < spec.amount_min - _EPS:
        return SizingResult(
            ok=False,
            qty=qty,
            clamped_by_leverage=clamped,
            reason=(
                f"quantity {qty} below exchange minimum {spec.amount_min}; "
                "rejecting rather than rounding up past the risk budget"
            ),
        )

    notional = qty * unit_notional
    if notional < spec.min_notional - _EPS:
        return SizingResult(
            ok=False,
            qty=qty,
            notional=notional,
            clamped_by_leverage=clamped,
            reason=(
                f"notional {notional:.4f} below exchange minimum {spec.min_notional}; "
                "rejecting rather than rounding up past the risk budget"
            ),
        )

    leverage = notional / equity
    if leverage > max_leverage + 1e-9:
        # Unreachable given the clamp above; kept as an assertion because the
        # consequence of a sizing bug here is an oversized live position.
        return SizingResult(
            ok=False,
            qty=qty,
            notional=notional,
            leverage=leverage,
            clamped_by_leverage=clamped,
            reason=f"post-rounding leverage {leverage:.3f}x exceeds cap {max_leverage}x",
        )

    return SizingResult(
        ok=True,
        qty=qty,
        notional=notional,
        risk_cash=qty * per_unit_risk,
        leverage=leverage,
        clamped_by_leverage=clamped,
    )


def slippage_bounded_limit_price(
    entry: float,
    side_is_long: bool,
    max_slippage_pct: float,
    price_step: float,
) -> float:
    """Limit price for the entry order.

    A resting limit at exactly the signal bar's close would only fill if price
    came back to us - on a continuation strategy that mostly means missing the
    move. Instead we cross the spread by at most ``max_slippage_pct``, which
    behaves like a market order with a hard worst-price guarantee: it fills at
    the touch or better, and simply does not fill if the market has already run
    past our tolerance.
    """
    factor = (1 + max_slippage_pct) if side_is_long else (1 - max_slippage_pct)
    return round_to_step(entry * factor, price_step)


def within_slippage(entry: float, market_price: float, max_slippage_pct: float) -> bool:
    """True if the current market price is still close enough to act on.

    Checked before sending the order so a signal that arrived after a large
    move is abandoned rather than chased.
    """
    if entry <= 0:
        return False
    return abs(market_price - entry) / entry <= max_slippage_pct
