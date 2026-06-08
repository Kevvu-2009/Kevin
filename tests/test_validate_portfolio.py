"""Portfolio validation CLI: pools trades across symbols and runs the gates."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from quantbot.cli import build_parser
from quantbot.data.synthetic import generate_ohlcv


def _write_csv(tmp_path, name, seed):
    df = generate_ohlcv(n=2500, timeframe="4h", seed=seed)
    p = tmp_path / name
    df.to_csv(p)
    return str(p)


def _run(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = args.func(args)
    return code, json.loads(buf.getvalue())


def test_portfolio_pools_trades_across_symbols(tmp_path):
    a = _write_csv(tmp_path, "A_4h.csv", seed=1)
    b = _write_csv(tmp_path, "B_4h.csv", seed=2)

    # Per-symbol baselines (default params) to know each one's OOS trade count.
    counts = []
    for data in (a, b):
        _, single = _run(["validate", "--strategy", "regime_adaptive",
                           "--data", data, "--timeframe", "4h"])
        counts.append(single["oos_metrics"]["n_trades"])

    code, out = _run(["validate-portfolio", "--strategy", "regime_adaptive",
                      "--timeframe", "4h", "--data", a, "--data", b])

    assert out["n_symbols"] == 2
    assert len(out["per_symbol"]) == 2
    # Pooled OOS trade count == sum of per-symbol OOS counts.
    assert out["portfolio_oos_metrics"]["n_trades"] == sum(counts)
    # Same gate machinery is applied to the combined result.
    assert set(out["gates"]["checks"]) >= {
        "oos_positive", "sharpe", "profit_factor", "max_drawdown", "min_trades",
    }
    assert "monte_carlo" in out
    assert code in (0, 2)  # pass or fail, but it must complete cleanly


def test_params_file_paired_by_position(tmp_path):
    a = _write_csv(tmp_path, "A_4h.csv", seed=3)
    b = _write_csv(tmp_path, "B_4h.csv", seed=4)
    # An optimize-style result file (best_params) and a bare-dict file.
    pa = tmp_path / "pa.json"
    pa.write_text(json.dumps({"best_params": {"trend_ema_fast": 21}}))
    pb = tmp_path / "pb.json"
    pb.write_text(json.dumps({"trend_ema_fast": 30}))

    code, out = _run([
        "validate-portfolio", "--strategy", "regime_adaptive", "--timeframe", "4h",
        "--data", a, "--params-file", str(pa),
        "--data", b, "--params-file", str(pb),
    ])
    assert out["n_symbols"] == 2
    assert code in (0, 2)
