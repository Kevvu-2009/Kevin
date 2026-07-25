"""Wire schema and internal enums.

``WebhookPayload`` is the *only* thing the outside world can hand us, so it is
validated aggressively: unknown fields are rejected, prices must be positive,
and the entry/stop/target geometry must be internally consistent with the
declared side. A malformed alert that got this far would otherwise be sized and
sent to the exchange.

Note the deliberate split of responsibilities:
  * this module rejects payloads that are *impossible* (bad geometry, absurd
    timestamps) - checks that do not depend on wall-clock time, so they are
    trivially testable;
  * ``risk.py`` rejects payloads that are *unwanted right now* (stale, wrong
    RR band, kill switch active).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Sanity bounds for millisecond epochs: 2020-01-01 .. 2100-01-01.
# Anything outside this is a unit error (seconds instead of ms) or garbage.
MIN_PLAUSIBLE_MS = 1_577_836_800_000
MAX_PLAUSIBLE_MS = 4_102_444_800_000


def timeframe_to_ms(timeframe: str) -> int | None:
    """Convert a TradingView ``timeframe.period`` string to milliseconds.

    TradingView encodes intraday resolutions as bare minute counts ("60" is
    1H), seconds as "<n>S", and higher resolutions as D/W/M. Returns ``None``
    for anything unrecognised so callers can decide how strict to be.
    """
    tf = timeframe.strip().upper()
    if not tf:
        return None
    if tf.isdigit():
        return int(tf) * 60_000
    head, unit = tf[:-1], tf[-1]
    if head and not head.isdigit():
        return None
    count = int(head) if head else 1
    unit_ms = {
        "S": 1_000,
        "D": 86_400_000,
        "W": 604_800_000,
        "M": 2_592_000_000,  # calendar month approximated as 30d
    }
    if unit not in unit_ms:
        return None
    return count * unit_ms[unit]


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"

    @property
    def exit_order_side(self) -> str:
        """The ccxt order side that reduces a position of this side."""
        return "sell" if self is Side.LONG else "buy"

    @property
    def entry_order_side(self) -> str:
        return "buy" if self is Side.LONG else "sell"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1


class OrderPurpose(str, Enum):
    ENTRY = "entry"
    STOP = "stop"
    TAKE_PROFIT = "take_profit"
    EMERGENCY_STOP = "emergency_stop"


class SignalStatus(str, Enum):
    RECEIVED = "received"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    SUBMITTED = "submitted"
    FILLED = "filled"
    ABANDONED = "abandoned"
    ERROR = "error"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class WebhookPayload(BaseModel):
    """The JSON body TradingView POSTs to ``/webhook``.

    ``bar_close_time`` is an addition to the originally specified schema and is
    optional. See ``effective_close_ms`` for why it matters.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    secret: str = Field(min_length=1, max_length=256)
    signal_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:\-]+$")
    action: Literal["entry"]
    side: Side
    symbol: str = Field(min_length=1, max_length=32)
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    target: float = Field(gt=0)
    timeframe: str = Field(min_length=1, max_length=8)
    bar_time: int
    bar_close_time: int | None = None

    @model_validator(mode="after")
    def _check_geometry_and_time(self) -> WebhookPayload:
        if not MIN_PLAUSIBLE_MS <= self.bar_time <= MAX_PLAUSIBLE_MS:
            raise ValueError(
                f"bar_time={self.bar_time} is not a plausible millisecond epoch "
                f"(expected {MIN_PLAUSIBLE_MS}..{MAX_PLAUSIBLE_MS}); "
                "a value ~1e10 means seconds were sent instead of milliseconds"
            )
        if self.bar_close_time is not None:
            if not MIN_PLAUSIBLE_MS <= self.bar_close_time <= MAX_PLAUSIBLE_MS:
                raise ValueError(
                    f"bar_close_time={self.bar_close_time} is not a plausible millisecond epoch"
                )
            if self.bar_close_time <= self.bar_time:
                raise ValueError("bar_close_time must be strictly after bar_time")

        # Geometry must match the declared side. This is the check that stops a
        # long signal whose "stop" is above entry from being sized as though the
        # distance were tiny (or negative) and blowing up the notional.
        if self.side is Side.LONG:
            if not self.stop < self.entry < self.target:
                raise ValueError(
                    f"long requires stop < entry < target, got "
                    f"stop={self.stop} entry={self.entry} target={self.target}"
                )
        else:
            if not self.target < self.entry < self.stop:
                raise ValueError(
                    f"short requires target < entry < stop, got "
                    f"target={self.target} entry={self.entry} stop={self.stop}"
                )
        return self

    # -- derived quantities ---------------------------------------------------
    @property
    def is_long(self) -> bool:
        return self.side is Side.LONG

    @property
    def stop_distance(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def stop_distance_pct(self) -> float:
        return self.stop_distance / self.entry

    @property
    def reward_distance(self) -> float:
        return abs(self.target - self.entry)

    @property
    def rr(self) -> float:
        """Realised reward:risk multiple implied by the payload's own prices."""
        risk = self.stop_distance
        if risk <= 0:
            return 0.0
        return self.reward_distance / risk

    def effective_close_ms(self, timeframe_ms: int | None = None) -> int:
        """Millisecond epoch at which this signal's bar CLOSED.

        This distinction is the single most important detail in the staleness
        check. ``bar_time`` in TradingView is the bar's OPEN time, so on a 1H
        chart it is already 3,600,000 ms old the instant the alert fires.
        Comparing it against a 90-second freshness window would reject 100% of
        signals; "fixing" that by widening the window to an hour would happily
        accept an hour-old signal replayed after a restart.

        We therefore prefer the explicit ``bar_close_time`` emitted by the Pine
        script, and fall back to ``bar_time + one bar`` when it is absent.
        """
        if self.bar_close_time is not None:
            return self.bar_close_time
        tf_ms = timeframe_ms if timeframe_ms is not None else timeframe_to_ms(self.timeframe)
        if tf_ms is None:
            # Unknown resolution and no explicit close time: treat bar_time as
            # the close. Conservative - it can only make the signal look older.
            return self.bar_time
        return self.bar_time + tf_ms

    def age_ms(self, now_ms: int, timeframe_ms: int | None = None) -> int:
        return now_ms - self.effective_close_ms(timeframe_ms)

    def redacted(self) -> dict[str, object]:
        """Payload for logging, with the shared secret removed."""
        data = self.model_dump(mode="json")
        data.pop("secret", None)
        return data
