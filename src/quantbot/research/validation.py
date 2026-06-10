"""Candidate-edge validation harness.

Every candidate (signal × symbol(s)) runs the same gauntlet:

1. **IS/OOS split** — parameters chosen on the first 70% by small-grid
   search; the last 30% is touched once, with those frozen parameters.
2. **Walk-forward** — rolling re-fit/re-test windows across the OOS region;
   consistency across windows matters more than the headline number.
3. **Monte Carlo** — block bootstrap of OOS bar returns (preserving
   short-horizon autocorrelation): how bad is the 5th-percentile path?
4. **Parameter sensitivity** — performance must be a plateau, not a spike:
   the median grid neighbour should retain most of the chosen point's Sharpe.
5. **Regime breakdown** — OOS performance per market regime; one
   catastrophic regime fails the candidate.
6. **Execution-lag stress** — everything is re-run with one extra bar of
   delay; an edge that dies with +1 bar latency is microstructure noise.
7. **Deflated Sharpe** — the OOS Sharpe is discounted for the number of
   trials (grid size × any sibling candidates) per Bailey & López de Prado
   (2014); we require the *deflated* probability to clear the bar.

Hard gates reject; survivors get a composite robustness score for ranking.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Type

import numpy as np
import pandas as pd

from quantbot.backtest.metrics import bars_per_year, max_drawdown, sharpe
from quantbot.research.regimes import detect_regimes, regime_performance
from quantbot.research.signals.base import PanelSignal, ResearchSignal
from quantbot.research.vector_engine import (
    CostModel,
    VectorBacktestResult,
    backtest_panel,
    backtest_positions,
)

EULER_MASCHERONI = 0.5772156649015329


# --------------------------------------------------------------------- gates


@dataclass(frozen=True)
class ResearchGates:
    """Hard accept/reject thresholds for a candidate edge (all on OOS)."""

    min_oos_sharpe: float = 1.0
    min_oos_profit_factor: float = 1.15
    max_oos_drawdown: float = 0.25
    min_oos_trades: int = 25
    require_positive_oos: bool = True
    min_oos_is_sharpe_ratio: float = 0.4     # overfit detector
    min_wf_positive_windows: float = 0.5     # ≥ half the WF windows profitable
    max_mc_p05_drawdown: float = 0.35        # 5th-pct bootstrap path DD ceiling
    min_sensitivity_retention: float = 0.3   # median grid Sharpe / best Sharpe
    min_deflated_prob: float = 0.80          # P(true SR > 0 | trials)
    min_lag_stress_sharpe: float = 0.0       # +1 bar lag must not flip negative
    worst_regime_max_drawdown: float = 0.35


@dataclass
class GateOutcome:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "checks": self.checks, "reasons": self.reasons}


# ----------------------------------------------------------- deflated sharpe


def probabilistic_sharpe_ratio(
    sr: float, sr_benchmark: float, n_obs: int, skew: float, kurt: float
) -> float:
    """P(true SR > benchmark) given a per-bar SR estimate over n_obs bars.

    Mertens (2002) standard error with skew/kurtosis adjustment; see Bailey &
    López de Prado, 'The Sharpe Ratio Efficient Frontier' (2012).  All SRs
    here are PER-BAR (not annualised) — annualisation cancels nowhere in this
    formula and mixing conventions is the classic implementation bug.
    """
    if n_obs < 3:
        return 0.0
    var_term = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    if var_term <= 0:
        return 0.0
    from scipy.stats import norm

    z = (sr - sr_benchmark) * math.sqrt(n_obs - 1) / math.sqrt(var_term)
    return float(norm.cdf(z))


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """E[max SR] across n_trials zero-skill trials (false-discovery bar)."""
    if n_trials <= 1 or sr_variance <= 0:
        return 0.0
    from scipy.stats import norm

    z1 = norm.ppf(1.0 - 1.0 / n_trials)
    z2 = norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(math.sqrt(sr_variance) * ((1.0 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2))


def deflated_sharpe_ratio(
    returns: pd.Series, n_trials: int, trial_sr_variance: float | None = None
) -> float:
    """P(true SR > 0) after deflating for selection across n_trials.

    trial_sr_variance: variance of per-bar SR across the trials actually run
    (grid points).  If unknown, the candidate's own SR variance estimate is a
    conservative floor.
    """
    r = returns.dropna().to_numpy()
    if len(r) < 10 or r.std(ddof=0) == 0:
        return 0.0
    sr = float(r.mean() / r.std(ddof=0))
    from scipy.stats import kurtosis, skew

    g3 = float(skew(r))
    g4 = float(kurtosis(r, fisher=False))
    if trial_sr_variance is None or not np.isfinite(trial_sr_variance):
        trial_sr_variance = max(1.0 / len(r), sr**2 / 4.0)
    sr_star = expected_max_sharpe(max(2, n_trials), trial_sr_variance)
    return probabilistic_sharpe_ratio(sr, sr_star, len(r), g3, g4)


# -------------------------------------------------------------- monte carlo


@dataclass
class BlockBootstrapResult:
    n_sims: int
    terminal_p05: float
    terminal_p50: float
    prob_loss: float
    max_dd_p05: float       # 5th-percentile (worst tail) of path max drawdown
    max_dd_median: float

    def to_dict(self) -> dict:
        return self.__dict__


def block_bootstrap_paths(
    returns: pd.Series,
    block: int = 24,
    n_sims: int = 1000,
    seed: int = 42,
) -> BlockBootstrapResult:
    """Resample contiguous return blocks, preserving autocorrelation, and
    measure the dispersion of terminal wealth and max drawdown."""
    r = returns.dropna().to_numpy(dtype=float)
    if len(r) < block * 3:
        return BlockBootstrapResult(0, 1.0, 1.0, 1.0, 0.0, 0.0)
    rng = np.random.default_rng(seed)
    n = len(r)
    n_blocks = int(np.ceil(n / block))
    terminals = np.empty(n_sims)
    dds = np.empty(n_sims)
    for i in range(n_sims):
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        path = np.concatenate([r[s : s + block] for s in starts])[:n]
        eq = np.cumprod(1.0 + path)
        terminals[i] = eq[-1]
        peak = np.maximum.accumulate(eq)
        dds[i] = float((eq / peak - 1.0).min())
    return BlockBootstrapResult(
        n_sims=n_sims,
        terminal_p05=float(np.percentile(terminals, 5)),
        terminal_p50=float(np.percentile(terminals, 50)),
        prob_loss=float((terminals < 1.0).mean()),
        max_dd_p05=float(np.percentile(dds, 5)),
        max_dd_median=float(np.median(dds)),
    )


# ----------------------------------------------------------------- runners


def _run(
    signal_cls: Type[ResearchSignal],
    params: dict[str, Any],
    data: pd.DataFrame | dict[str, pd.DataFrame],
    timeframe: str,
    costs: CostModel,
    extra_lag: int = 0,
) -> VectorBacktestResult:
    sig = signal_cls(**params)
    if isinstance(sig, PanelSignal):
        if not isinstance(data, dict):
            raise TypeError(f"{sig.name} needs a panel (dict of frames)")
        positions = sig.generate_panel(data)
        return backtest_panel(data, positions, timeframe, costs, extra_lag)
    if isinstance(data, dict):
        raise TypeError(f"{sig.name} is single-asset; got a panel")
    pos = sig.generate(data)
    return backtest_positions(data, pos, timeframe, costs, extra_lag)


def _slice(data, lo: int | None = None, hi: int | None = None):
    """Positional slice; for panels, positions refer to the UNION index and
    each frame is cut by timestamp (frames may have different coverage)."""
    if isinstance(data, dict):
        idx = _index_of(data)
        lo_ts = idx[lo] if lo else None
        hi_ts = idx[hi - 1] if hi is not None and hi <= len(idx) else None
        out = {}
        for k, v in data.items():
            d = v
            if lo_ts is not None:
                d = d.loc[d.index >= lo_ts]
            if hi_ts is not None:
                d = d.loc[d.index <= hi_ts]
            out[k] = d
        return out
    return data.iloc[lo:hi]


def _index_of(data) -> pd.Index:
    if isinstance(data, dict):
        idx = None
        for v in data.values():
            idx = v.index if idx is None else idx.union(v.index)
        return idx
    return data.index


def _select_params(
    signal_cls: Type[ResearchSignal],
    data,
    timeframe: str,
    costs: CostModel,
    min_trades: int = 10,
) -> tuple[dict[str, Any], list[float]]:
    """Grid-search the (small) declared grid on TRAINING data only.

    Returns (best_params, all_grid_sharpes) — the grid Sharpes feed both the
    sensitivity gate and the deflated-Sharpe trial variance.
    """
    best, best_score = None, -np.inf
    grid_sharpes: list[float] = []
    for params in signal_cls.grid_combinations():
        try:
            res = _run(signal_cls, params, data, timeframe, costs)
        except Exception:
            grid_sharpes.append(float("nan"))
            continue
        s = res.metrics.sharpe
        grid_sharpes.append(s)
        score = s if res.metrics.n_trades >= min_trades else s - 10.0
        if score > best_score:
            best, best_score = params, score
    if best is None:
        best = dict(signal_cls.default_params)
    return best, grid_sharpes


def walk_forward_signal(
    signal_cls: Type[ResearchSignal],
    data,
    timeframe: str,
    costs: CostModel,
    n_splits: int = 5,
    train_frac: float = 0.6,
) -> dict:
    """Rolling re-fit / re-test.  Test blocks tile the last (1-train_frac) of
    the data; each uses parameters chosen only on data before it.  Signals are
    generated on the full history up to each block's end (indicator warm-up),
    which is exactly the information a live deployment would have."""
    index = _index_of(data)
    n = len(index)
    test_total = int(n * (1.0 - train_frac))
    test_size = max(test_total // n_splits, 30)
    windows = []
    oos_returns: list[pd.Series] = []
    start = n - test_size * n_splits
    if start < int(n * 0.2):
        raise ValueError("not enough data for walk-forward")

    for k in range(n_splits):
        lo = start + k * test_size
        hi = min(n, lo + test_size)
        train = _slice(data, None, lo)
        full = _slice(data, None, hi)
        params, _ = _select_params(signal_cls, train, timeframe, costs)
        res = _run(signal_cls, params, full, timeframe, costs)
        seg = res.returns.iloc[lo:hi] if not isinstance(data, dict) else res.returns.reindex(index[lo:hi]).fillna(0.0)
        oos_returns.append(seg)
        windows.append(
            {
                "window": k,
                "test_start": str(index[lo]),
                "test_end": str(index[hi - 1]),
                "params": params,
                "sharpe": sharpe(seg, timeframe),
                "total_return": float((1.0 + seg).prod() - 1.0),
            }
        )

    stitched = pd.concat(oos_returns)
    eq = (1.0 + stitched).cumprod()
    positive = [w for w in windows if w["total_return"] > 0]
    return {
        "windows": windows,
        "returns": stitched,
        "sharpe": sharpe(stitched, timeframe),
        "total_return": float(eq.iloc[-1] - 1.0),
        "max_drawdown": max_drawdown(eq),
        "positive_window_frac": len(positive) / max(1, len(windows)),
    }


# ------------------------------------------------------------ full pipeline


@dataclass
class CandidateValidation:
    signal_name: str
    family: str
    symbols: tuple[str, ...]
    timeframe: str
    best_params: dict
    is_stats: dict
    oos_stats: dict
    walk_forward: dict
    monte_carlo: dict
    sensitivity: dict
    regimes: dict
    lag_stress: dict
    deflated_prob: float
    n_trials: int
    gates: GateOutcome
    robustness_score: float = 0.0

    def to_row(self) -> dict:
        return {
            "signal": self.signal_name,
            "family": self.family,
            "symbols": "+".join(self.symbols),
            "timeframe": self.timeframe,
            "passed": self.gates.passed,
            "oos_sharpe": self.oos_stats.get("sharpe", 0.0),
            "oos_total_return": self.oos_stats.get("total_return", 0.0),
            "oos_max_dd": self.oos_stats.get("max_drawdown", 0.0),
            "oos_profit_factor": self.oos_stats.get("profit_factor", 0.0),
            "oos_win_rate": self.oos_stats.get("win_rate", 0.0),
            "oos_trades": self.oos_stats.get("n_trades", 0),
            "oos_cagr": self.oos_stats.get("cagr", 0.0),
            "oos_exposure": self.oos_stats.get("exposure", 0.0),
            "is_sharpe": self.is_stats.get("sharpe", 0.0),
            "wf_sharpe": self.walk_forward.get("sharpe", 0.0),
            "wf_positive_windows": self.walk_forward.get("positive_window_frac", 0.0),
            "mc_dd_p05": self.monte_carlo.get("max_dd_p05", 0.0),
            "mc_prob_loss": self.monte_carlo.get("prob_loss", 1.0),
            "sens_retention": self.sensitivity.get("retention", 0.0),
            "lag_sharpe": self.lag_stress.get("sharpe", 0.0),
            "worst_regime_dd": self.regimes.get("worst_drawdown", 0.0),
            "deflated_prob": self.deflated_prob,
            "robustness_score": self.robustness_score,
            "reject_reasons": "; ".join(self.gates.reasons),
            "best_params": str(self.best_params),
        }


def validate_candidate(
    signal_cls: Type[ResearchSignal],
    data: pd.DataFrame | dict[str, pd.DataFrame],
    timeframe: str,
    symbols: tuple[str, ...],
    costs: CostModel | None = None,
    gates: ResearchGates | None = None,
    is_frac: float = 0.7,
    wf_splits: int = 4,
    mc_sims: int = 500,
    extra_trials: int = 0,
) -> CandidateValidation:
    """Run the full validation gauntlet for one candidate.

    extra_trials: trials performed elsewhere in the discovery sweep that this
    candidate competed against (sibling symbols etc.) — added to the
    deflated-Sharpe trial count so family-level selection is paid for.
    """
    costs = costs or CostModel()
    g = gates or ResearchGates()
    index = _index_of(data)
    n = len(index)
    split = int(n * is_frac)

    # --- 1) parameter selection strictly on IS ------------------------------
    train = _slice(data, None, split)
    best_params, grid_sharpes = _select_params(signal_cls, train, timeframe, costs)
    is_res = _run(signal_cls, best_params, train, timeframe, costs)

    # --- 2) frozen-parameter OOS --------------------------------------------
    full_res = _run(signal_cls, best_params, data, timeframe, costs)
    oos_returns = (
        full_res.returns.iloc[split:]
        if not isinstance(data, dict)
        else full_res.returns.reindex(index[split:]).fillna(0.0)
    )
    oos_eq = (1.0 + oos_returns).cumprod()
    oos_pos = full_res.positions.reindex(oos_returns.index).fillna(0.0)
    if isinstance(data, dict):
        # Panel positions are net-absolute; take trades from the blotter.
        split_ts = index[split]
        oos_trades = full_res.trades[full_res.trades["entry_time"] >= split_ts]
    else:
        from quantbot.research.vector_engine import _segment_trades

        oos_trades = _segment_trades(
            oos_pos.to_numpy(), oos_returns.to_numpy(), oos_returns.index
        )
    from quantbot.backtest.metrics import compute_metrics

    oos_metrics = compute_metrics(oos_eq, timeframe, oos_trades["return"].to_numpy())
    oos_stats = oos_metrics.to_dict()
    oos_stats["exposure"] = float((oos_pos.abs() > 1e-12).mean())

    # --- 3) walk-forward ------------------------------------------------------
    try:
        wf = walk_forward_signal(signal_cls, data, timeframe, costs, n_splits=wf_splits)
    except ValueError:
        wf = {"windows": [], "sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0,
              "positive_window_frac": 0.0, "returns": pd.Series(dtype=float)}

    # --- 4) Monte Carlo on OOS returns ---------------------------------------
    mc = block_bootstrap_paths(oos_returns, block=24, n_sims=mc_sims)

    # --- 5) parameter sensitivity --------------------------------------------
    finite = [s for s in grid_sharpes if np.isfinite(s)]
    best_sharpe = max(finite) if finite else 0.0
    median_sharpe = float(np.median(finite)) if finite else 0.0
    retention = (median_sharpe / best_sharpe) if best_sharpe > 1e-9 else 0.0
    sensitivity = {
        "grid_size": len(grid_sharpes),
        "best_is_sharpe": best_sharpe,
        "median_is_sharpe": median_sharpe,
        "retention": float(np.clip(retention, -1.0, 1.0)),
        "positive_frac": float(np.mean([s > 0 for s in finite])) if finite else 0.0,
    }

    # --- 6) regime breakdown on OOS -------------------------------------------
    if isinstance(data, dict):
        ref = data[sorted(data)[0]]
    else:
        ref = data
    regs = detect_regimes(ref)
    per_regime = regime_performance(oos_returns, regs, timeframe)
    worst_dd = min((v["max_drawdown"] for v in per_regime.values()), default=0.0)
    worst_sharpe = min((v["sharpe"] for v in per_regime.values()), default=0.0)
    regimes = {"per_regime": per_regime, "worst_drawdown": worst_dd, "worst_sharpe": worst_sharpe}

    # --- 7) execution-lag stress ----------------------------------------------
    lag_res = _run(signal_cls, best_params, data, timeframe, costs, extra_lag=1)
    lag_oos = (
        lag_res.returns.iloc[split:]
        if not isinstance(data, dict)
        else lag_res.returns.reindex(index[split:]).fillna(0.0)
    )
    lag_stress = {"sharpe": sharpe(lag_oos, timeframe),
                  "total_return": float((1.0 + lag_oos).prod() - 1.0)}

    # --- 8) deflated Sharpe -----------------------------------------------------
    n_trials = len(grid_sharpes) + max(0, extra_trials)
    ann = math.sqrt(bars_per_year(timeframe))
    trial_var = float(np.var([s / ann for s in finite])) if len(finite) > 1 else None
    deflated = deflated_sharpe_ratio(oos_returns, n_trials, trial_var)

    # ---------------------------------------------------------------- gates
    out = GateOutcome(passed=True)

    def check(name: str, ok: bool, why: str) -> None:
        out.checks[name] = bool(ok)
        if not ok:
            out.reasons.append(why)

    if g.require_positive_oos:
        check("oos_positive", oos_stats["total_return"] > 0,
              f"OOS return {oos_stats['total_return']:.1%} ≤ 0")
    check("oos_sharpe", oos_stats["sharpe"] >= g.min_oos_sharpe,
          f"OOS Sharpe {oos_stats['sharpe']:.2f} < {g.min_oos_sharpe}")
    check("profit_factor", oos_stats["profit_factor"] >= g.min_oos_profit_factor,
          f"OOS PF {oos_stats['profit_factor']:.2f} < {g.min_oos_profit_factor}")
    check("max_drawdown", abs(oos_stats["max_drawdown"]) <= g.max_oos_drawdown,
          f"OOS maxDD {abs(oos_stats['max_drawdown']):.1%} > {g.max_oos_drawdown:.0%}")
    check("min_trades", oos_stats["n_trades"] >= g.min_oos_trades,
          f"{oos_stats['n_trades']} OOS trades < {g.min_oos_trades}")
    if is_res.metrics.sharpe > 0:
        ratio = oos_stats["sharpe"] / is_res.metrics.sharpe
        check("is_oos_consistency", ratio >= g.min_oos_is_sharpe_ratio,
              f"OOS/IS Sharpe {ratio:.2f} < {g.min_oos_is_sharpe_ratio} (overfit)")
    check("wf_consistency", wf["positive_window_frac"] >= g.min_wf_positive_windows,
          f"only {wf['positive_window_frac']:.0%} WF windows positive")
    check("mc_drawdown", abs(mc.max_dd_p05) <= g.max_mc_p05_drawdown if mc.n_sims else True,
          f"MC p05 drawdown {abs(mc.max_dd_p05):.1%} > {g.max_mc_p05_drawdown:.0%}")
    check("sensitivity", sensitivity["retention"] >= g.min_sensitivity_retention,
          f"param retention {sensitivity['retention']:.2f} < {g.min_sensitivity_retention} "
          "(performance is a parameter spike)")
    check("deflated_sharpe", deflated >= g.min_deflated_prob,
          f"deflated P(SR>0) {deflated:.2f} < {g.min_deflated_prob} "
          f"(not distinguishable from luck over {n_trials} trials)")
    check("lag_stress", lag_stress["sharpe"] >= g.min_lag_stress_sharpe,
          f"+1-bar-lag Sharpe {lag_stress['sharpe']:.2f} — edge dies with delay")
    check("regime_floor", abs(regimes["worst_drawdown"]) <= g.worst_regime_max_drawdown,
          f"worst regime DD {abs(regimes['worst_drawdown']):.1%} > {g.worst_regime_max_drawdown:.0%}")

    out.passed = all(out.checks.values())

    cv = CandidateValidation(
        signal_name=signal_cls.name,
        family=signal_cls.family,
        symbols=tuple(symbols),
        timeframe=timeframe,
        best_params=best_params,
        is_stats=is_res.stats,
        oos_stats=oos_stats,
        walk_forward={k: v for k, v in wf.items() if k != "returns"},
        monte_carlo=mc.to_dict(),
        sensitivity=sensitivity,
        regimes=regimes,
        lag_stress=lag_stress,
        deflated_prob=deflated,
        n_trials=n_trials,
        gates=out,
    )
    cv.robustness_score = robustness_score(cv)
    return cv


def robustness_score(cv: CandidateValidation) -> float:
    """Composite 0-100 ranking score.  Deliberately NOT dominated by return:
    consistency, plateau-ness, tail behaviour and statistical confidence get
    70% of the weight."""
    oos_sharpe = np.clip(cv.oos_stats.get("sharpe", 0.0) / 3.0, 0.0, 1.0)
    calmar = np.clip(cv.oos_stats.get("calmar", 0.0) / 5.0, 0.0, 1.0)
    pf = np.clip((cv.oos_stats.get("profit_factor", 0.0) - 1.0) / 1.0, 0.0, 1.0)
    wf_cons = np.clip(cv.walk_forward.get("positive_window_frac", 0.0), 0.0, 1.0)
    sens = np.clip(cv.sensitivity.get("retention", 0.0), 0.0, 1.0)
    mc_dd = np.clip(1.0 - abs(cv.monte_carlo.get("max_dd_p05", 1.0)) / 0.5, 0.0, 1.0)
    regime_floor = np.clip(1.0 - abs(cv.regimes.get("worst_drawdown", 1.0)) / 0.5, 0.0, 1.0)
    dsr = np.clip(cv.deflated_prob, 0.0, 1.0)
    lag = np.clip(cv.lag_stress.get("sharpe", 0.0) / max(cv.oos_stats.get("sharpe", 1e-9), 1e-9), 0.0, 1.0)

    score = (
        0.18 * oos_sharpe
        + 0.07 * calmar
        + 0.05 * pf
        + 0.20 * wf_cons
        + 0.12 * sens
        + 0.10 * mc_dd
        + 0.08 * regime_floor
        + 0.15 * dsr
        + 0.05 * lag
    )
    return float(round(100.0 * score, 2))
