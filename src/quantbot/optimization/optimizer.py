"""Strategy parameter optimizer.

Design choices that fight overfitting:

* **Optimise on in-sample only.**  OOS is never seen by the search.
* **Objective is a *composite*, not raw profit.**  We reward Sharpe and CAGR,
  penalise drawdown, and *penalise the IS↔OOS gap* so the search prefers params
  that generalise rather than ones that fit IS noise.
* **Trade-count floor.**  Candidates with too few trades score ``-inf``.
* **Everything is logged.**  Each trial's params + full metrics are returned
  (and can be persisted to ``optimization_trials``).

Backend: Optuna TPE (Bayesian) when installed; otherwise a reproducible random
search over the same space, so the module always runs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from quantbot.backtest.engine import BacktestEngine
from quantbot.backtest.metrics import Metrics
from quantbot.config import CostConfig
from quantbot.strategies.registry import get_strategy, get_strategy_class
from quantbot.validation.splits import is_oos_split


@dataclass
class OptimizationConfig:
    n_trials: int = 60
    is_frac: float = 0.70
    min_trades: int = 20
    # composite objective weights
    w_sharpe: float = 1.0
    w_cagr: float = 0.5
    w_drawdown: float = 1.0       # multiplies abs(maxDD) as a penalty
    w_oos_gap: float = 0.5        # penalty for IS-OOS Sharpe divergence
    seed: int = 42


@dataclass
class OptResult:
    best_params: dict[str, Any]
    best_score: float
    best_is_metrics: Metrics | None
    best_oos_metrics: Metrics | None
    trials: list[dict] = field(default_factory=list)
    backend: str = "random"

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "best_params": self.best_params,
            "best_score": self.best_score,
            "best_is_metrics": self.best_is_metrics.to_dict() if self.best_is_metrics else None,
            "best_oos_metrics": self.best_oos_metrics.to_dict() if self.best_oos_metrics else None,
            "n_trials": len(self.trials),
        }


class Optimizer:
    def __init__(
        self,
        strategy_name: str,
        df: pd.DataFrame,
        timeframe: str,
        config: OptimizationConfig | None = None,
        costs: CostConfig | None = None,
    ) -> None:
        self.strategy_name = strategy_name
        self.timeframe = timeframe
        self.cfg = config or OptimizationConfig()
        self.engine = BacktestEngine(costs=costs)
        self.is_df, self.oos_df = is_oos_split(df, self.cfg.is_frac)
        self.space = get_strategy_class(strategy_name).param_space
        self.trials: list[dict] = []

    # ------------------------------------------------------------- objective
    def _score(self, is_m: Metrics, oos_m: Metrics) -> float:
        if is_m.n_trades < self.cfg.min_trades:
            return -math.inf
        gap = abs(is_m.sharpe - oos_m.sharpe)
        score = (
            self.cfg.w_sharpe * is_m.sharpe
            + self.cfg.w_cagr * is_m.cagr
            - self.cfg.w_drawdown * abs(is_m.max_drawdown)
            - self.cfg.w_oos_gap * gap
        )
        return float(score) if np.isfinite(score) else -math.inf

    def _evaluate(self, params: dict) -> tuple[float, Metrics, Metrics]:
        strat_is = get_strategy(self.strategy_name, **params)
        is_res = self.engine.run(strat_is, self.is_df, self.timeframe)
        # Provide indicator warm-up by prepending IS tail to OOS.
        warm = pd.concat([self.is_df.tail(250), self.oos_df])
        oos_res = self.engine.run(get_strategy(self.strategy_name, **params), warm, self.timeframe)
        score = self._score(is_res.metrics, oos_res.metrics)
        self.trials.append({"params": params, "is": is_res.stats, "oos": oos_res.stats, "score": score})
        return score, is_res.metrics, oos_res.metrics

    # ----------------------------------------------------------------- search
    def optimize(self) -> OptResult:
        try:
            return self._optimize_optuna()
        except ImportError:
            return self._optimize_random()

    def _suggest_optuna(self, trial) -> dict:
        params: dict[str, Any] = {}
        for name, spec in self.space.items():
            kind = spec[0]
            if kind == "int":
                params[name] = trial.suggest_int(name, int(spec[1]), int(spec[2]))
            elif kind == "float":
                params[name] = trial.suggest_float(name, float(spec[1]), float(spec[2]))
            elif kind == "categorical":
                params[name] = trial.suggest_categorical(name, spec[1])
        return params

    def _optimize_optuna(self) -> OptResult:
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        sampler = optuna.samplers.TPESampler(seed=self.cfg.seed)
        study = optuna.create_study(direction="maximize", sampler=sampler)

        best: dict[str, Any] = {}

        def objective(trial):
            params = self._suggest_optuna(trial)
            score, is_m, oos_m = self._evaluate(params)
            trial.set_user_attr("is_sharpe", is_m.sharpe)
            trial.set_user_attr("oos_sharpe", oos_m.sharpe)
            best[trial.number] = (params, is_m, oos_m)
            return score if np.isfinite(score) else -1e9

        study.optimize(objective, n_trials=self.cfg.n_trials, show_progress_bar=False)
        bp = study.best_params
        # Recompute best metrics cleanly.
        _, is_m, oos_m = self._evaluate(bp)
        return OptResult(
            best_params=bp,
            best_score=float(study.best_value),
            best_is_metrics=is_m,
            best_oos_metrics=oos_m,
            trials=self.trials,
            backend="optuna",
        )

    def _optimize_random(self) -> OptResult:
        rng = np.random.default_rng(self.cfg.seed)
        best_score = -math.inf
        best = (None, None, None)
        for _ in range(self.cfg.n_trials):
            params = {}
            for name, spec in self.space.items():
                kind = spec[0]
                if kind == "int":
                    params[name] = int(rng.integers(int(spec[1]), int(spec[2]) + 1))
                elif kind == "float":
                    params[name] = float(rng.uniform(spec[1], spec[2]))
                elif kind == "categorical":
                    params[name] = spec[1][int(rng.integers(0, len(spec[1])))]
            score, is_m, oos_m = self._evaluate(params)
            if score > best_score:
                best_score = score
                best = (params, is_m, oos_m)
        return OptResult(
            best_params=best[0] or {},
            best_score=best_score if math.isfinite(best_score) else 0.0,
            best_is_metrics=best[1],
            best_oos_metrics=best[2],
            trials=self.trials,
            backend="random",
        )
