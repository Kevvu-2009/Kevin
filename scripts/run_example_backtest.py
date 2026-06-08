#!/usr/bin/env python3
"""End-to-end demo: generate data, backtest all strategies, optimize the best,
run full validation + acceptance gates, and write example artifacts.

Runs fully offline on synthetic data so it works in any environment:

    python scripts/run_example_backtest.py

Outputs JSON + (if plotly installed) HTML reports under ./reports/ and prints a
leaderboard plus the gate verdict for the optimized strategy.
"""

from __future__ import annotations

import json
from pathlib import Path

from quantbot.backtest.engine import BacktestEngine
from quantbot.backtest.report import metrics_table, to_json
from quantbot.config import get_settings
from quantbot.data.synthetic import generate_ohlcv
from quantbot.optimization.optimizer import OptimizationConfig, Optimizer
from quantbot.strategies.registry import get_strategy, list_strategies
from quantbot.validation import (
    evaluate_gates,
    is_oos_split,
    monte_carlo_equity,
    parameter_sensitivity,
    walk_forward,
)

REPORTS = Path("reports")
REPORTS.mkdir(exist_ok=True)
TIMEFRAME = "4h"


def main() -> None:
    settings = get_settings()
    df = generate_ohlcv(n=4000, timeframe=TIMEFRAME, seed=11)
    engine = BacktestEngine(costs=settings.costs, risk_per_trade=settings.risk.risk_per_trade)

    print("=" * 70)
    print(f"Strategy leaderboard ({TIMEFRAME}, {len(df)} bars, costs+slippage+latency)")
    print("=" * 70)
    leaderboard = []
    for name in list_strategies():
        res = engine.run(get_strategy(name), df, TIMEFRAME)
        m = res.stats
        leaderboard.append((name, m))
        print(f"\n[{name}]")
        print(metrics_table(res))
        to_json(res, REPORTS / f"backtest_{name}.json")

    # Optimize the trend strategy as the worked example.
    target = "trend_following"
    print("\n" + "=" * 70)
    print(f"Bayesian optimization: {target}")
    print("=" * 70)
    opt = Optimizer(target, df, TIMEFRAME, OptimizationConfig(n_trials=40), costs=settings.costs)
    opt_res = opt.optimize()
    print(f"backend={opt_res.backend} best_score={opt_res.best_score:.3f}")
    print("best_params:", json.dumps(opt_res.best_params, indent=2))
    (REPORTS / "optimization_trend_following.json").write_text(
        json.dumps(opt_res.to_dict(), indent=2, default=str)
    )

    # Full validation on optimized params.
    print("\n" + "=" * 70)
    print("Validation pipeline (IS/OOS + walk-forward + Monte Carlo + gates)")
    print("=" * 70)
    is_df, oos_df = is_oos_split(df, 0.70)
    is_res = engine.run(get_strategy(target, **opt_res.best_params), is_df, TIMEFRAME)
    oos_res = engine.run(get_strategy(target, **opt_res.best_params), oos_df, TIMEFRAME)

    wf = walk_forward(
        target, df, TIMEFRAME,
        fit_fn=lambda _train: opt_res.best_params,
        n_splits=5, costs=settings.costs,
    )
    mc = monte_carlo_equity(oos_res.trades["return"].to_numpy() if len(oos_res.trades) else [])
    sens = parameter_sensitivity(target, opt_res.best_params, df, TIMEFRAME, costs=settings.costs)
    gates = evaluate_gates(is_res.metrics, oos_res.metrics)

    print(f"IS  Sharpe={is_res.metrics.sharpe:.2f}  PF={is_res.metrics.profit_factor:.2f}")
    print(f"OOS Sharpe={oos_res.metrics.sharpe:.2f}  PF={oos_res.metrics.profit_factor:.2f} "
          f"MaxDD={oos_res.metrics.max_drawdown:.2%}")
    print(f"WalkForward Sharpe={wf.metrics.sharpe:.2f}  CAGR={wf.metrics.cagr:.2%}")
    print(f"MonteCarlo P(profit)={mc.prob_profit:.2%}  CAGR p05={mc.cagr_p05:.2%}")
    print(f"Param robustness (0-1) = {sens.robustness:.2f}")
    print(f"\nGATE VERDICT: {'PASS ✅' if gates.passed else 'REJECT ❌'}")
    for reason in gates.reasons:
        print(f"  - {reason}")

    summary = {
        "leaderboard": {n: m for n, m in leaderboard},
        "optimized_params": opt_res.best_params,
        "is_metrics": is_res.stats,
        "oos_metrics": oos_res.stats,
        "walk_forward": wf.metrics.to_dict(),
        "monte_carlo": mc.to_dict(),
        "param_robustness": sens.robustness,
        "gates": gates.to_dict(),
    }
    (REPORTS / "example_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nArtifacts written to {REPORTS}/")


if __name__ == "__main__":
    main()
