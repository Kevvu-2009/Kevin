"""Edge-discovery pipeline.

Sweeps the full signal library across a symbol universe, validates every
candidate with the complete gauntlet, charges the *whole sweep's* trial count
to each survivor's deflated Sharpe (you cannot test 200 things and then
pretend the winner was your only idea), ranks survivors by robustness score,
and emits a leaderboard plus per-candidate dossiers.

Stat-arb pairs are pre-screened on the TRAINING window only: pairs must be
cointegrated (Engle-Granger p < threshold) or top-correlated there before
they are allowed to consume a validation slot.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from quantbot.logging_setup import get_logger
from quantbot.research.signals import SIGNAL_REGISTRY, PanelSignal
from quantbot.research.signals.statarb import engle_granger_pvalue
from quantbot.research.validation import (
    CandidateValidation,
    CostModel,
    ResearchGates,
    validate_candidate,
)

log = get_logger("research.discovery")


@dataclass
class DiscoveryConfig:
    timeframe: str = "1h"
    families: tuple[str, ...] = ()          # empty = all families
    exclude_signals: tuple[str, ...] = ()
    costs: CostModel = field(default_factory=CostModel)
    gates: ResearchGates = field(default_factory=ResearchGates)
    is_frac: float = 0.7
    wf_splits: int = 4
    mc_sims: int = 500
    min_bars: int = 2000                    # refuse to "discover" on tiny samples
    coint_p_threshold: float = 0.05
    max_pairs: int = 4                      # validation slots for stat-arb pairs
    include_ml: bool = True                 # ML candidates are slow; allow opting out


@dataclass
class DiscoveryResult:
    candidates: list[CandidateValidation]
    leaderboard: pd.DataFrame
    selected: list[CandidateValidation]
    n_trials: int
    runtime_s: float
    universe: tuple[str, ...]
    timeframe: str
    notes: list[str] = field(default_factory=list)

    @property
    def found_edge(self) -> bool:
        return len(self.selected) > 0


def _eligible_signals(cfg: DiscoveryConfig) -> list[type]:
    out = []
    for name, cls in sorted(SIGNAL_REGISTRY.items()):
        if cfg.families and cls.family not in cfg.families:
            continue
        if name in cfg.exclude_signals:
            continue
        if cls.family == "machine_learning" and not cfg.include_ml:
            continue
        out.append(cls)
    return out


def _candidate_pairs(
    panel: dict[str, pd.DataFrame], cfg: DiscoveryConfig
) -> list[tuple[str, str]]:
    """Stat-arb pair pre-selection on the TRAINING window only."""
    symbols = sorted(panel)
    if len(symbols) < 2:
        return []
    scored: list[tuple[float, tuple[str, str]]] = []
    for a, b in itertools.combinations(symbols, 2):
        idx = panel[a].index.intersection(panel[b].index)
        if len(idx) < cfg.min_bars:
            continue
        split = int(len(idx) * cfg.is_frac)
        train_idx = idx[:split]
        la = np.log(panel[a]["close"].reindex(train_idx))
        lb = np.log(panel[b]["close"].reindex(train_idx))
        p = engle_granger_pvalue(la, lb)
        if np.isnan(p):
            # statsmodels unavailable → correlation fallback (weaker screen).
            corr = la.diff().corr(lb.diff())
            p = 1.0 - abs(corr if np.isfinite(corr) else 0.0)
        scored.append((p, (a, b)))
    scored.sort(key=lambda t: t[0])
    chosen = [pair for p, pair in scored if p <= cfg.coint_p_threshold][: cfg.max_pairs]
    if not chosen and scored:
        log.info("discovery_no_cointegrated_pairs",
                 best_p=scored[0][0] if scored else None)
    return chosen


def count_planned_trials(panel: dict[str, pd.DataFrame], cfg: DiscoveryConfig) -> int:
    """Total parameter evaluations the sweep will perform — the multiple-
    testing bill that every candidate's deflated Sharpe must pay."""
    signals = _eligible_signals(cfg)
    symbols = sorted(panel)
    total = 0
    for cls in signals:
        grid = len(cls.grid_combinations())
        if issubclass(cls, PanelSignal):
            if cls.name == "xsec_momentum":
                total += grid
            else:
                total += grid * min(cfg.max_pairs, max(0, len(symbols) * (len(symbols) - 1) // 2))
        else:
            total += grid * len(symbols)
    return total


def run_discovery(
    panel: dict[str, pd.DataFrame],
    cfg: DiscoveryConfig | None = None,
) -> DiscoveryResult:
    """Run the sweep.  ``panel``: symbol -> OHLCV frame (same timeframe)."""
    cfg = cfg or DiscoveryConfig()
    t0 = time.time()
    notes: list[str] = []

    panel = {s: df.sort_index() for s, df in panel.items() if len(df) >= cfg.min_bars}
    if not panel:
        raise ValueError(f"no symbol has >= {cfg.min_bars} bars; refusing to run")
    symbols = sorted(panel)

    n_trials = count_planned_trials(panel, cfg)
    notes.append(f"Total planned parameter evaluations (trial count for DSR): {n_trials}")

    signals = _eligible_signals(cfg)
    results: list[CandidateValidation] = []

    for cls in signals:
        if issubclass(cls, PanelSignal):
            if cls.name == "xsec_momentum":
                jobs: list[tuple[tuple[str, ...], dict]] = [(tuple(symbols), panel)]
            else:
                jobs = [
                    ((a, b), {a: panel[a], b: panel[b]})
                    for a, b in _candidate_pairs(panel, cfg)
                ]
        else:
            jobs = [((s,), panel[s]) for s in symbols]

        for syms, data in jobs:
            label = f"{cls.name}[{'+'.join(syms)}]"
            try:
                cv = validate_candidate(
                    cls,
                    data,
                    cfg.timeframe,
                    syms,
                    costs=cfg.costs,
                    gates=cfg.gates,
                    is_frac=cfg.is_frac,
                    wf_splits=cfg.wf_splits,
                    mc_sims=cfg.mc_sims,
                    extra_trials=n_trials - len(cls.grid_combinations()),
                )
                results.append(cv)
                log.info(
                    "candidate_validated",
                    candidate=label,
                    passed=cv.gates.passed,
                    oos_sharpe=round(cv.oos_stats.get("sharpe", 0.0), 2),
                    score=cv.robustness_score,
                )
            except Exception as e:
                notes.append(f"{label}: validation error — {e}")
                log.warning("candidate_failed", candidate=label, error=str(e))

    leaderboard = pd.DataFrame([cv.to_row() for cv in results])
    if len(leaderboard):
        leaderboard = leaderboard.sort_values(
            ["passed", "robustness_score"], ascending=[False, False]
        ).reset_index(drop=True)

    selected = sorted(
        (cv for cv in results if cv.gates.passed),
        key=lambda cv: cv.robustness_score,
        reverse=True,
    )

    if not selected:
        notes.append(
            "NO ROBUST EDGE FOUND: no candidate cleared every validation gate "
            "on this data. This is a valid (and common) outcome — do not "
            "lower the gates to force a deployment."
        )

    return DiscoveryResult(
        candidates=results,
        leaderboard=leaderboard,
        selected=selected,
        n_trials=n_trials,
        runtime_s=round(time.time() - t0, 1),
        universe=tuple(symbols),
        timeframe=cfg.timeframe,
        notes=notes,
    )
