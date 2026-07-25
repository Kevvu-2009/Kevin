"""Pre-trade risk gates and hard kill switches.

Everything here answers one question: *should this signal be allowed to create
an order right now?* Nothing in this module places or cancels orders, and no
gate here ever touches an existing position - a kill switch stops new entries
and deliberately leaves live stops alone. Removing protection from an open
position because a limit tripped would be the worst possible response.

Gate order is chosen so the cheapest and most decisive checks run first, and so
that the staleness check runs before anything that could have a side effect.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings
from .models import WebhookPayload, timeframe_to_ms
from .sizing import validate_rr, validate_stop_distance
from .state import Store


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    code: str = "ok"
    reason: str = ""

    @classmethod
    def ok(cls) -> RiskDecision:
        return cls(True)

    @classmethod
    def deny(cls, code: str, reason: str) -> RiskDecision:
        return cls(False, code, reason)


def utc_day_start_ms(now_ms: int) -> int:
    dt = datetime.fromtimestamp(now_ms / 1000, tz=UTC)
    start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


def utc_day_key(now_ms: int) -> str:
    return datetime.fromtimestamp(now_ms / 1000, tz=UTC).strftime("%Y-%m-%d")


class RiskManager:
    def __init__(self, cfg: Settings, store: Store) -> None:
        self.cfg = cfg
        self.store = store

    # ------------------------------------------------------------- kill switch
    def halt_state(self) -> tuple[bool, str]:
        """Manual kill switch: a file on disk or an env flag.

        Deliberately re-read on every call rather than cached, so `touch HALT`
        takes effect immediately without a restart.
        """
        if self.cfg.halt_env:
            return True, "HALT env flag is set"
        try:
            if Path(self.cfg.halt_file).expanduser().exists():
                return True, f"HALT file present at {self.cfg.halt_file}"
        except OSError as exc:  # pragma: no cover - defensive
            return True, f"cannot stat HALT file ({exc}); failing closed"
        return False, ""

    # ------------------------------------------------------------ daily anchor
    def daily_anchor_equity(self, equity: float, now_ms: int | None = None) -> float:
        """Equity recorded at the first observation of the current UTC day.

        ``kv_setdefault`` means a restart mid-day re-reads the original anchor
        rather than re-baselining, so a bot that restarts after a -2.5% morning
        still halts at -3% instead of getting a fresh budget.
        """
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        key = f"daily_anchor_equity:{utc_day_key(now)}"
        return float(self.store.kv_setdefault(key, repr(float(equity))))

    def daily_drawdown_pct(self, equity: float, now_ms: int | None = None) -> float:
        anchor = self.daily_anchor_equity(equity, now_ms)
        if anchor <= 0:
            return 0.0
        return (equity - anchor) / anchor

    def consecutive_losses(self) -> int:
        n = 0
        for pos in self.store.recent_closed_positions(limit=100):
            if pos.realized_pnl is not None and pos.realized_pnl < 0:
                n += 1
            else:
                break
        return n

    # --------------------------------------------------------------- the gates
    def check_staleness(
        self, payload: WebhookPayload, now_ms: int, timeframe_ms: int | None = None
    ) -> RiskDecision:
        age_ms = payload.age_ms(now_ms, timeframe_ms)
        max_age_ms = self.cfg.max_signal_age_sec * 1000
        if age_ms > max_age_ms:
            return RiskDecision.deny(
                "stale_signal",
                f"signal bar closed {age_ms / 1000:.1f}s ago, limit is "
                f"{self.cfg.max_signal_age_sec}s (queued alert or restarted VPS)",
            )
        # A bar that closes in the future means clock skew on this host or a
        # bad timestamp. Acting on it would defeat the staleness check entirely.
        if age_ms < -30_000:
            return RiskDecision.deny(
                "future_signal",
                f"signal bar closes {-age_ms / 1000:.1f}s in the future; "
                "check NTP on this host",
            )
        return RiskDecision.ok()

    def evaluate_entry(
        self,
        payload: WebhookPayload,
        ccxt_symbol: str,
        equity: float,
        now_ms: int | None = None,
    ) -> RiskDecision:
        """Run every pre-trade gate. First failure wins."""
        now = now_ms if now_ms is not None else int(time.time() * 1000)

        halted, why = self.halt_state()
        if halted:
            return RiskDecision.deny("halted", why)

        tf_ms = timeframe_to_ms(payload.timeframe)
        stale = self.check_staleness(payload, now, tf_ms)
        if not stale.allowed:
            return stale

        if payload.timeframe.strip() != self.cfg.expected_timeframe.strip():
            return RiskDecision.deny(
                "wrong_timeframe",
                f"timeframe {payload.timeframe!r} != configured "
                f"{self.cfg.expected_timeframe!r}; refusing to trade an "
                "un-validated resolution",
            )

        rr_ok, rr, rr_reason = validate_rr(
            payload.entry, payload.stop, payload.target, self.cfg.rr_min, self.cfg.rr_max
        )
        if not rr_ok:
            return RiskDecision.deny("bad_rr", rr_reason)

        dist_ok, _pct, dist_reason = validate_stop_distance(
            payload.entry,
            payload.stop,
            self.cfg.stop_dist_min_pct,
            self.cfg.stop_dist_max_pct,
        )
        if not dist_ok:
            return RiskDecision.deny("bad_stop_distance", dist_reason)

        if self.store.get_open_position(ccxt_symbol) is not None:
            return RiskDecision.deny(
                "position_exists",
                f"already holding {ccxt_symbol}; max "
                f"{self.cfg.max_positions_per_symbol} per symbol",
            )

        open_count = self.store.count_open_positions()
        if open_count >= self.cfg.max_positions_total:
            return RiskDecision.deny(
                "max_positions",
                f"{open_count} open positions, limit is {self.cfg.max_positions_total}",
            )

        dd = self.daily_drawdown_pct(equity, now)
        if dd <= -self.cfg.daily_loss_limit_pct:
            return RiskDecision.deny(
                "daily_loss_limit",
                f"daily drawdown {dd:.2%} at or beyond limit "
                f"-{self.cfg.daily_loss_limit_pct:.2%}; halted until 00:00 UTC",
            )

        losses = self.consecutive_losses()
        if losses >= self.cfg.max_consecutive_losses:
            return RiskDecision.deny(
                "consecutive_losses",
                f"{losses} consecutive losing trades, limit is "
                f"{self.cfg.max_consecutive_losses}",
            )

        return RiskDecision.ok()

    # ----------------------------------------------------------------- summary
    def snapshot(self, equity: float, now_ms: int | None = None) -> dict[str, object]:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        halted, why = self.halt_state()
        return {
            "halted": halted,
            "halt_reason": why,
            "equity": equity,
            "daily_anchor_equity": self.daily_anchor_equity(equity, now),
            "daily_drawdown_pct": self.daily_drawdown_pct(equity, now),
            "daily_loss_limit_pct": -self.cfg.daily_loss_limit_pct,
            "realized_pnl_today": self.store.realized_pnl_since(utc_day_start_ms(now)),
            "consecutive_losses": self.consecutive_losses(),
            "max_consecutive_losses": self.cfg.max_consecutive_losses,
            "open_positions": self.store.count_open_positions(),
            "max_positions_total": self.cfg.max_positions_total,
        }
