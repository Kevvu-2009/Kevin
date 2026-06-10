"""Research-signal interface and registry.

A ``ResearchSignal`` maps an OHLCV frame to a target-position series in
[-1, 1], decided at each bar's close.  It must be causal — the vector engine
adds the execution delay, the signal must simply never read past its bar.

Every signal carries its *investment thesis* (why the inefficiency should
exist), a *persistence* argument (why it shouldn't be arbitraged away
immediately) and *risks/failure modes*.  The discovery report quotes these
verbatim: a candidate without an economic story is just a curve fit.

``grid`` defines the small parameter grid used by walk-forward re-fitting and
sensitivity analysis.  Grids are intentionally tiny (≤ ~30 combinations):
selection bias grows with the number of trials, and the deflated-Sharpe
correction in validation is only as honest as the trial count we feed it.
"""

from __future__ import annotations

import itertools
from abc import ABC, abstractmethod
from typing import Any, Iterable, Type

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


class ResearchSignal(ABC):
    name: str = "base"
    family: str = "unclassified"           # trend | momentum | mean_reversion | ...
    requires_panel: bool = False           # True -> multi-symbol signal
    default_params: dict[str, Any] = {}
    grid: dict[str, list] = {}             # param -> candidate values

    # Economic documentation (quoted in research reports).
    thesis: str = ""
    persistence: str = ""
    risks: str = ""

    def __init__(self, **params: Any) -> None:
        self.params = {**self.default_params, **params}

    # ------------------------------------------------------------- interface
    @abstractmethod
    def generate(self, df: pd.DataFrame) -> pd.Series:
        """Target position in [-1, 1] at each bar close.  Must be causal."""

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _validate(df: pd.DataFrame) -> None:
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"OHLCV frame missing columns: {missing}")
        if not df.index.is_monotonic_increasing:
            raise ValueError("index must be sorted ascending")

    @classmethod
    def grid_combinations(cls) -> list[dict[str, Any]]:
        """All parameter dicts in the declared grid (default params if none)."""
        if not cls.grid:
            return [dict(cls.default_params)]
        keys = sorted(cls.grid)
        combos = []
        for values in itertools.product(*(cls.grid[k] for k in keys)):
            params = dict(cls.default_params)
            params.update(dict(zip(keys, values)))
            combos.append(params)
        return combos

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}({self.params})"


class PanelSignal(ResearchSignal):
    """Multi-symbol signal (cross-sectional / statistical arbitrage).

    ``generate_panel`` returns one position series per symbol; the vector
    engine's ``backtest_panel`` combines the legs.  ``generate`` is
    intentionally unsupported.
    """

    requires_panel = True

    def generate(self, df: pd.DataFrame) -> pd.Series:  # pragma: no cover
        raise NotImplementedError(f"{self.name} is a panel signal; use generate_panel")

    @abstractmethod
    def generate_panel(self, panel: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        ...


# -------------------------------------------------------------------- registry

SIGNAL_REGISTRY: dict[str, Type[ResearchSignal]] = {}


def register_signal(cls: Type[ResearchSignal]) -> Type[ResearchSignal]:
    key = cls.name.lower()
    existing = SIGNAL_REGISTRY.get(key)
    if existing is not None and existing is not cls:
        raise ValueError(f"signal '{key}' already registered")
    SIGNAL_REGISTRY[key] = cls
    return cls


def get_signal(name: str, **params: Any) -> ResearchSignal:
    key = name.lower()
    if key not in SIGNAL_REGISTRY:
        raise KeyError(f"unknown signal '{name}'; available: {sorted(SIGNAL_REGISTRY)}")
    return SIGNAL_REGISTRY[key](**params)


def list_signals(family: str | None = None) -> list[str]:
    if family is None:
        return sorted(SIGNAL_REGISTRY)
    return sorted(k for k, v in SIGNAL_REGISTRY.items() if v.family == family)


def signal_families() -> list[str]:
    return sorted({v.family for v in SIGNAL_REGISTRY.values()})


# ------------------------------------------------------------------ utilities


def hysteresis_positions(
    enter_long: pd.Series | np.ndarray,
    exit_long: pd.Series | np.ndarray,
    enter_short: pd.Series | np.ndarray | None = None,
    exit_short: pd.Series | np.ndarray | None = None,
    index: pd.Index | None = None,
) -> pd.Series:
    """Stateful enter/exit → position series (the common signal idiom).

    Long opens on ``enter_long``, closes on ``exit_long`` (or flips on
    ``enter_short``).  Vectorisation of hysteresis is error-prone; a tight
    numpy loop is fast enough (~1M bars/sec) and obviously correct.
    """

    def _arr(x, n):
        if x is None:
            return np.zeros(n, dtype=bool)
        if isinstance(x, pd.Series):
            return x.fillna(False).to_numpy(dtype=bool)
        return np.asarray(x, dtype=bool)

    if isinstance(enter_long, pd.Series):
        idx = enter_long.index
    elif index is not None:
        idx = index
    else:
        raise ValueError("provide an index when passing raw arrays")

    n = len(idx)
    el, xl = _arr(enter_long, n), _arr(exit_long, n)
    es, xs = _arr(enter_short, n), _arr(exit_short, n)

    pos = np.zeros(n)
    state = 0
    for i in range(n):
        if state == 1 and (xl[i] or es[i]):
            state = 0
        elif state == -1 and (xs[i] or el[i]):
            state = 0
        if state == 0:
            if el[i]:
                state = 1
            elif es[i]:
                state = -1
        pos[i] = state
    return pd.Series(pos, index=idx)
