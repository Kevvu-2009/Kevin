from datetime import datetime, timedelta, timezone

from quantbot.config import RiskConfig
from quantbot.risk.portfolio import PortfolioRiskManager
from quantbot.risk.position_sizing import (
    fixed_fractional_size,
    volatility_adjusted_size,
)


def test_fixed_fractional_risk_amount():
    r = fixed_fractional_size(equity=10_000, entry_price=100, stop_price=95, risk_per_trade=0.01)
    # risk 1% of 10k = 100; per-unit risk = 5 => qty = 20
    assert abs(r.qty - 20) < 1e-6
    assert abs(r.risk_cash - 100) < 1e-6


def test_fixed_fractional_no_leverage():
    r = fixed_fractional_size(equity=10_000, entry_price=100, stop_price=99.9, risk_per_trade=0.01)
    assert r.notional <= 10_000 + 1e-6  # capped at 1x


def test_risk_per_trade_clamped():
    r = fixed_fractional_size(10_000, 100, 90, risk_per_trade=0.05)  # 5% -> clamp 1%
    assert abs(r.risk_cash - 100) < 1e-6


def test_volatility_adjusted_inverse_to_vol():
    low_vol = volatility_adjusted_size(10_000, 100, atr=1.0)
    high_vol = volatility_adjusted_size(10_000, 100, atr=5.0)
    assert low_vol.qty > high_vol.qty


def test_max_positions_blocks():
    rm = PortfolioRiskManager(RiskConfig(max_concurrent_positions=2), initial_equity=10_000)
    rm.set_open_positions(2)
    assert not rm.can_open().allowed


def test_daily_loss_limit():
    rm = PortfolioRiskManager(RiskConfig(daily_loss_limit=0.03), initial_equity=10_000)
    rm.update_equity(9_600)  # -4%
    d = rm.can_open()
    assert not d.allowed and d.reason == "daily_loss_limit"


def test_kill_switch_trips_and_blocks():
    rm = PortfolioRiskManager(RiskConfig(kill_switch_drawdown=0.20), initial_equity=10_000)
    rm.update_equity(12_000)  # new peak
    rm.update_equity(9_000)   # -25% from peak
    assert rm.state.kill_switch_active
    assert not rm.can_open().allowed


def test_period_rollover_resets_daily():
    rm = PortfolioRiskManager(RiskConfig(daily_loss_limit=0.03), initial_equity=10_000)
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rm.update_equity(9_600, now=t0)
    assert not rm.can_open(now=t0).allowed
    t1 = t0 + timedelta(days=1)
    # New day resets the day-start baseline to current equity.
    assert rm.can_open(now=t1).allowed
