"""Deployment acceptance gates.

A strategy may be deployed only if it clears EVERY gate.  These thresholds are
the project mandate and are intentionally strict; the goal is to reject the many
plausible-looking-but-fragile candidates rather than to maximise approvals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quantbot.backtest.metrics import Metrics


@dataclass(frozen=True)
class AcceptanceCriteria:
    min_sharpe: float = 1.2
    min_profit_factor: float = 1.3
    max_drawdown: float = 0.20            # absolute, e.g. 0.20 == -20%
    require_positive_oos: bool = True
    min_trades: int = 30                  # statistical significance floor
    # Consistency: OOS Sharpe must retain at least this fraction of IS Sharpe.
    min_oos_is_sharpe_ratio: float = 0.5


@dataclass
class GateReport:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "reasons": self.reasons, "checks": self.checks}


def _check(report: GateReport, name: str, ok: bool, why: str) -> None:
    report.checks[name] = bool(ok)
    if not ok:
        report.reasons.append(why)


def evaluate_gates(
    is_metrics: Metrics,
    oos_metrics: Metrics,
    criteria: AcceptanceCriteria | None = None,
    regime_metrics: dict[str, Metrics] | None = None,
) -> GateReport:
    """Evaluate a strategy candidate against all deployment gates.

    Args:
        is_metrics:   in-sample metrics (training period)
        oos_metrics:  out-of-sample metrics (held-out future)
        regime_metrics: optional per-regime OOS metrics for consistency checks
    """
    c = criteria or AcceptanceCriteria()
    rep = GateReport(passed=True)

    # 1) Out-of-sample profitability.
    if c.require_positive_oos:
        _check(rep, "oos_positive", oos_metrics.total_return > 0,
               f"OOS total return not positive ({oos_metrics.total_return:.2%})")

    # 2) Risk-adjusted return (judged on OOS — the honest sample).
    _check(rep, "sharpe", oos_metrics.sharpe >= c.min_sharpe,
           f"OOS Sharpe {oos_metrics.sharpe:.2f} < {c.min_sharpe}")

    # 3) Profit factor.
    _check(rep, "profit_factor", oos_metrics.profit_factor >= c.min_profit_factor,
           f"OOS profit factor {oos_metrics.profit_factor:.2f} < {c.min_profit_factor}")

    # 4) Drawdown ceiling (check both samples; worst must still be within limit).
    worst_dd = min(is_metrics.max_drawdown, oos_metrics.max_drawdown)
    _check(rep, "max_drawdown", abs(worst_dd) <= c.max_drawdown,
           f"Max drawdown {abs(worst_dd):.2%} > {c.max_drawdown:.0%}")

    # 5) Sample size.
    _check(rep, "min_trades", oos_metrics.n_trades >= c.min_trades,
           f"Only {oos_metrics.n_trades} OOS trades (< {c.min_trades})")

    # 6) Consistency: OOS shouldn't collapse vs IS (overfit detector).
    if is_metrics.sharpe > 0:
        ratio = oos_metrics.sharpe / is_metrics.sharpe
        _check(rep, "is_oos_consistency", ratio >= c.min_oos_is_sharpe_ratio,
               f"OOS/IS Sharpe ratio {ratio:.2f} < {c.min_oos_is_sharpe_ratio} (overfit risk)")

    # 7) Cross-regime consistency (if provided): every regime non-catastrophic.
    if regime_metrics:
        for regime, m in regime_metrics.items():
            ok = m.max_drawdown >= -c.max_drawdown - 0.05  # small tolerance
            _check(rep, f"regime_{regime}", ok,
                   f"Regime '{regime}' drawdown {m.max_drawdown:.2%} too deep")

    rep.passed = all(rep.checks.values())
    return rep
