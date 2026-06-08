"""Portfolio-level risk controls and the emergency kill switch.

The ``PortfolioRiskManager`` is the single authority the execution engine must
consult *before every entry*.  It enforces:

  * max concurrent positions
  * daily loss limit  (resets each UTC day)
  * weekly loss limit (resets each ISO week)
  * peak-to-trough kill switch — once tripped, no new entries are permitted and
    the engine should flatten / halt.

It is pure-Python and side-effect free except for its own in-memory state, so it
is trivially unit-testable and can be snapshotted to Redis/Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from quantbot.config import RiskConfig


@dataclass
class RiskState:
    equity: float
    peak_equity: float
    day_start_equity: float
    week_start_equity: float
    open_positions: int = 0
    current_day: date = field(default_factory=lambda: datetime.now(timezone.utc).date())
    current_week: int = field(default_factory=lambda: datetime.now(timezone.utc).isocalendar()[1])
    kill_switch_active: bool = False


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""


class PortfolioRiskManager:
    def __init__(self, config: RiskConfig | None = None, initial_equity: float = 10_000.0) -> None:
        self.cfg = config or RiskConfig()
        self.state = RiskState(
            equity=initial_equity,
            peak_equity=initial_equity,
            day_start_equity=initial_equity,
            week_start_equity=initial_equity,
        )

    # --------------------------------------------------------- bookkeeping
    def _roll_periods(self, now: datetime) -> None:
        today = now.date()
        week = now.isocalendar()[1]
        if today != self.state.current_day:
            self.state.current_day = today
            self.state.day_start_equity = self.state.equity
        if week != self.state.current_week:
            self.state.current_week = week
            self.state.week_start_equity = self.state.equity

    def update_equity(self, equity: float, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._roll_periods(now)
        self.state.equity = equity
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity
        # Trip the kill switch on breach of the peak-to-trough limit.
        if self.current_drawdown() <= -self.cfg.kill_switch_drawdown:
            self.state.kill_switch_active = True

    def set_open_positions(self, n: int) -> None:
        self.state.open_positions = n

    # -------------------------------------------------------------- queries
    def current_drawdown(self) -> float:
        if self.state.peak_equity <= 0:
            return 0.0
        return self.state.equity / self.state.peak_equity - 1.0

    def daily_pnl_pct(self) -> float:
        if self.state.day_start_equity <= 0:
            return 0.0
        return self.state.equity / self.state.day_start_equity - 1.0

    def weekly_pnl_pct(self) -> float:
        if self.state.week_start_equity <= 0:
            return 0.0
        return self.state.equity / self.state.week_start_equity - 1.0

    # -------------------------------------------------------------- gating
    def can_open(self, now: datetime | None = None) -> RiskDecision:
        now = now or datetime.now(timezone.utc)
        self._roll_periods(now)

        if self.state.kill_switch_active:
            return RiskDecision(False, "kill_switch_active")
        if self.current_drawdown() <= -self.cfg.kill_switch_drawdown:
            self.state.kill_switch_active = True
            return RiskDecision(False, "kill_switch_drawdown_breach")
        if self.state.open_positions >= self.cfg.max_concurrent_positions:
            return RiskDecision(False, "max_concurrent_positions")
        if self.daily_pnl_pct() <= -self.cfg.daily_loss_limit:
            return RiskDecision(False, "daily_loss_limit")
        if self.weekly_pnl_pct() <= -self.cfg.weekly_loss_limit:
            return RiskDecision(False, "weekly_loss_limit")
        return RiskDecision(True, "ok")

    def trip_kill_switch(self, reason: str = "manual") -> None:
        self.state.kill_switch_active = True

    def reset_kill_switch(self) -> None:
        """Manual re-arm (operator action only — never automatic)."""
        self.state.kill_switch_active = False
        self.state.peak_equity = self.state.equity
