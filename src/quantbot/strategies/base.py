"""Strategy interface.

A strategy is a pure function of a single instrument's OHLCV history to a set of
**aligned signal series**.  It must not look ahead: the signal on bar *t* may
only use information available at the close of bar *t*.  The backtester and live
engine both add an execution-latency delay (default: act on next bar open), so
strategies themselves should express *intent at bar close*.

Signal contract (all indexed identically to the input frame):
    entries    : bool  — open/append a long at this bar's decision point
    exits      : bool  — flatten an existing long
    stop        : float — current protective stop *price* while in a position
                          (NaN when no stop applies); the engine treats a bar
                          whose low pierces this level as a stop-out.
    direction  : int   — +1 long (shorts reserved; these strategies are long-only)

Strategies expose ``param_space`` for the optimizer and ``default_params``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass
class StrategyResult:
    entries: pd.Series
    exits: pd.Series
    stop: pd.Series
    direction: int = 1
    meta: dict[str, Any] = field(default_factory=dict)

    def as_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"entries": self.entries, "exits": self.exits, "stop": self.stop}
        )


class Strategy(ABC):
    """Base class for all strategies."""

    name: str = "base"
    #: parameter search space for the optimizer.  Each entry is one of:
    #:   ("int", low, high) | ("float", low, high) | ("categorical", [..])
    param_space: dict[str, tuple] = {}
    default_params: dict[str, Any] = {}

    def __init__(self, **params: Any) -> None:
        self.params: dict[str, Any] = {**self.default_params, **params}

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _validate(df: pd.DataFrame) -> None:
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"OHLCV frame missing columns: {missing}")
        if not df.index.is_monotonic_increasing:
            raise ValueError("OHLCV frame index must be sorted ascending")

    @abstractmethod
    def generate(self, df: pd.DataFrame) -> StrategyResult:
        """Produce the signal series for ``df``."""

    # Convenience used by the regime-adaptive strategy.
    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}({self.params})"


def empty_signals(index: pd.Index) -> StrategyResult:
    false = pd.Series(False, index=index)
    nan = pd.Series(np.nan, index=index)
    return StrategyResult(entries=false.copy(), exits=false.copy(), stop=nan)
