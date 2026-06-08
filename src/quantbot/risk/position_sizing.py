"""Position sizing methods.

Both methods return a **base-asset quantity** (e.g. number of BTC) and are
capped to avoid leverage (notional <= equity).  Risk-per-trade is clamped to the
mandated 0.5%-1% band by the caller / config.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SizingResult:
    qty: float
    notional: float
    risk_cash: float
    method: str


def _clamp_risk(risk_per_trade: float) -> float:
    return min(max(risk_per_trade, 0.005), 0.01)


def fixed_fractional_size(
    equity: float,
    entry_price: float,
    stop_price: float,
    risk_per_trade: float = 0.0075,
    allow_fractional: bool = True,
    max_leverage: float = 1.0,
) -> SizingResult:
    """Risk a fixed fraction of equity, sized by the entry→stop distance.

    qty = (equity * risk_pct) / (entry - stop)
    so that being stopped out loses approximately ``equity * risk_pct``.
    """
    if entry_price <= 0:
        return SizingResult(0.0, 0.0, 0.0, "fixed_fractional")
    risk_pct = _clamp_risk(risk_per_trade)
    risk_cash = equity * risk_pct
    per_unit_risk = entry_price - stop_price
    if per_unit_risk <= 0:
        # No valid stop → fall back to a capped fraction of equity.
        qty = (equity * max_leverage) / entry_price
    else:
        qty = risk_cash / per_unit_risk
    # No leverage beyond max_leverage.
    qty = min(qty, equity * max_leverage / entry_price)
    if not allow_fractional:
        qty = float(int(qty))
    return SizingResult(qty=qty, notional=qty * entry_price, risk_cash=risk_cash,
                        method="fixed_fractional")


def volatility_adjusted_size(
    equity: float,
    entry_price: float,
    atr: float,
    risk_per_trade: float = 0.0075,
    atr_stop_mult: float = 3.0,
    allow_fractional: bool = True,
    max_leverage: float = 1.0,
) -> SizingResult:
    """Size from ATR so each position targets equal *volatility* risk.

    Implied stop distance = atr_stop_mult * ATR.  Quantity is then chosen so a
    move of that size costs ``equity * risk_pct`` — high-vol assets get smaller
    positions, low-vol assets larger ones (vol targeting / risk parity flavour).
    """
    if entry_price <= 0 or atr <= 0:
        return SizingResult(0.0, 0.0, 0.0, "volatility_adjusted")
    risk_pct = _clamp_risk(risk_per_trade)
    risk_cash = equity * risk_pct
    stop_distance = atr_stop_mult * atr
    qty = risk_cash / stop_distance
    qty = min(qty, equity * max_leverage / entry_price)
    if not allow_fractional:
        qty = float(int(qty))
    return SizingResult(qty=qty, notional=qty * entry_price, risk_cash=risk_cash,
                        method="volatility_adjusted")
