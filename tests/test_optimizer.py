from quantbot.config import CostConfig
from quantbot.optimization.optimizer import OptimizationConfig, Optimizer


def test_random_optimizer_runs(ohlcv):
    opt = Optimizer(
        "mean_reversion", ohlcv, "4h",
        OptimizationConfig(n_trials=8, min_trades=1, seed=0),
        costs=CostConfig(),
    )
    # Force the dependency-free path for determinism in CI.
    res = opt._optimize_random()
    assert res.backend == "random"
    assert isinstance(res.best_params, dict)
    assert len(res.trials) == 8
    # best params must be within declared bounds
    for name, spec in opt.space.items():
        if spec[0] in ("int", "float") and name in res.best_params:
            assert spec[1] <= res.best_params[name] <= spec[2]


def test_optimizer_uses_is_oos_split(small_ohlcv):
    opt = Optimizer("trend_following", small_ohlcv, "1h",
                    OptimizationConfig(n_trials=3, min_trades=1), costs=CostConfig())
    assert len(opt.is_df) > 0 and len(opt.oos_df) > 0
    assert opt.is_df.index.max() <= opt.oos_df.index.min()
