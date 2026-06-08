"""Parameter sensitivity analysis.

Perturb one parameter at a time around a chosen point and measure how the key
metrics move.  A robust strategy sits on a *plateau*: small parameter changes
produce small, smooth metric changes.  A sharp peak (high sensitivity) is the
fingerprint of overfitting and is penalised in selection.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quantbot.backtest.engine import BacktestEngine
from quantbot.config import CostConfig
from quantbot.strategies.registry import get_strategy, get_strategy_class


@dataclass
class SensitivityResult:
    table: pd.DataFrame          # rows: param/value, cols: metrics
    robustness: float            # 1 - mean(coeff. of variation of Sharpe); higher=better

    def to_dict(self) -> dict:
        return {"robustness": self.robustness, "table": self.table.to_dict(orient="records")}


def parameter_sensitivity(
    strategy_name: str,
    base_params: dict,
    df: pd.DataFrame,
    timeframe: str,
    steps: int = 5,
    rel_range: float = 0.25,
    costs: CostConfig | None = None,
    metric: str = "sharpe",
) -> SensitivityResult:
    """Sweep each numeric param ±``rel_range`` (steps points) around base."""
    cls = get_strategy_class(strategy_name)
    space = cls.param_space
    engine = BacktestEngine(costs=costs)

    records: list[dict] = []
    sharpe_by_param: dict[str, list[float]] = {}

    for pname, spec in space.items():
        if spec[0] not in ("int", "float"):
            continue
        base_val = base_params.get(pname, cls.default_params.get(pname))
        if base_val is None:
            continue
        lo = base_val * (1 - rel_range)
        hi = base_val * (1 + rel_range)
        grid = np.linspace(lo, hi, steps)
        sharpes: list[float] = []
        for v in grid:
            val = int(round(v)) if spec[0] == "int" else float(v)
            params = {**base_params, pname: val}
            try:
                res = engine.run(get_strategy(strategy_name, **params), df, timeframe)
                stat = res.stats
            except Exception:
                continue
            sharpes.append(stat.get(metric, 0.0))
            records.append({"param": pname, "value": val, **stat})
        if sharpes:
            sharpe_by_param[pname] = sharpes

    # Robustness = 1 - average coefficient of variation of the target metric.
    cvs = []
    for vals in sharpe_by_param.values():
        arr = np.asarray(vals, dtype=float)
        m = np.nanmean(arr)
        s = np.nanstd(arr)
        if abs(m) > 1e-9:
            cvs.append(abs(s / m))
    robustness = float(max(0.0, 1.0 - (np.mean(cvs) if cvs else 1.0)))
    table = pd.DataFrame(records)
    return SensitivityResult(table=table, robustness=robustness)
