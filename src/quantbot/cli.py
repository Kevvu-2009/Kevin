"""QuantBot command-line interface.

Subcommands:
    init-db       apply the SQL schema
    download      fetch historical OHLCV and store it
    backtest      run a single backtest and print/report metrics
    optimize      Bayesian parameter search (IS) with OOS validation
    validate      full validation pipeline + acceptance gates
    research      end-to-end: optimize -> validate -> approve/reject
    run           start the live/paper trading engine (replay or live loop)
    dashboard     launch the FastAPI monitoring dashboard

Designed so the analytics subcommands work offline against parquet/CSV, while
``download``/``run``/``dashboard`` use the configured DB/venues.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quantbot.config import get_settings
from quantbot.logging_setup import configure_logging, get_logger

log = get_logger("cli")


def _load_frame(path: str):
    import pandas as pd

    p = Path(path)
    if p.suffix in (".parquet", ".pq"):
        try:
            df = pd.read_parquet(p)
        except ImportError as exc:
            raise SystemExit(
                f"Reading {p} needs a parquet engine (pip install pyarrow). "
                "Alternatively re-download with a .csv output, which needs no extra deps."
            ) from exc
    else:
        df = pd.read_csv(p)
    # Normalise timestamp index.
    for col in ("ts", "timestamp", "time", "date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True)
            df = df.set_index(col)
            break
    df.columns = [c.lower() for c in df.columns]
    return df.sort_index()


def _resolve_params(args) -> dict:
    """Strategy params from --params (inline JSON) or --params-file (a path).

    The file may be a bare param dict, or an optimizer result (as written by
    ``optimize --out ...``), in which case its ``best_params`` are used. This
    lets you feed tuned params straight back in without pasting JSON in the shell.
    """
    if getattr(args, "params", None):
        return json.loads(args.params)
    pf = getattr(args, "params_file", None)
    if pf:
        data = json.loads(Path(pf).read_text())
        if isinstance(data, dict) and "best_params" in data:
            return data["best_params"] or {}
        return data or {}
    return {}


# --------------------------------------------------------------------- commands
def cmd_init_db(args) -> int:
    from quantbot.data.db import init_schema

    init_schema(args.schema)
    print(f"Schema applied from {args.schema}")
    return 0


def cmd_download(args) -> int:
    from quantbot.data.downloader import fetch_ohlcv
    from quantbot.data.quality import validate_ohlcv
    from quantbot.data.repository import save_quality_run, upsert_ohlcv

    s = get_settings()
    df = fetch_ohlcv(args.symbol, args.timeframe, since=args.since,
                     exchange_id=args.exchange or s.data_exchange)
    rep = validate_ohlcv(df, args.timeframe)
    print(f"Downloaded {len(df)} candles | quality passed={rep.passed} gaps={rep.n_gaps}")
    if args.store:
        n = upsert_ohlcv(df, args.exchange or s.data_exchange, args.symbol, args.timeframe)
        save_quality_run(rep, args.exchange or s.data_exchange, args.symbol)
        print(f"Stored {n} rows")
    elif args.out:
        out = args.out
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        if Path(out).suffix in (".parquet", ".pq"):
            try:
                df.to_parquet(out)
            except ImportError:
                # No parquet engine (pyarrow/fastparquet) installed; CSV needs
                # no extra deps and round-trips fine through _load_frame.
                out = str(Path(out).with_suffix(".csv"))
                df.to_csv(out)
                print("(parquet engine not installed; wrote CSV instead)")
        else:
            df.to_csv(out)
        print(f"Wrote {out}")
    return 0


def cmd_backtest(args) -> int:
    from quantbot.backtest.engine import BacktestEngine
    from quantbot.backtest.report import html_report, metrics_table
    from quantbot.strategies.registry import get_strategy

    s = get_settings()
    df = _load_frame(args.data)
    params = _resolve_params(args)
    strat = get_strategy(args.strategy, **params)
    engine = BacktestEngine(costs=s.costs, risk_per_trade=s.risk.risk_per_trade)
    res = engine.run(strat, df, args.timeframe)
    print(metrics_table(res))
    if args.report:
        path = html_report(res, args.report, title=f"{args.strategy} {args.timeframe}")
        print(f"Report: {path}")
    return 0


def cmd_optimize(args) -> int:
    from quantbot.optimization.optimizer import OptimizationConfig, Optimizer

    s = get_settings()
    df = _load_frame(args.data)
    opt = Optimizer(args.strategy, df, args.timeframe,
                    OptimizationConfig(n_trials=args.trials), costs=s.costs)
    res = opt.optimize()
    print(json.dumps(res.to_dict(), indent=2, default=str))
    if args.out:
        Path(args.out).write_text(json.dumps(res.to_dict(), indent=2, default=str))
    return 0


def cmd_validate(args) -> int:
    from quantbot.backtest.engine import BacktestEngine
    from quantbot.strategies.registry import get_strategy
    from quantbot.validation import evaluate_gates, is_oos_split, monte_carlo_equity

    s = get_settings()
    df = _load_frame(args.data)
    params = _resolve_params(args)
    is_df, oos_df = is_oos_split(df, 0.70)
    eng = BacktestEngine(costs=s.costs, risk_per_trade=s.risk.risk_per_trade)
    is_res = eng.run(get_strategy(args.strategy, **params), is_df, args.timeframe)
    oos_res = eng.run(get_strategy(args.strategy, **params), oos_df, args.timeframe)
    gates = evaluate_gates(is_res.metrics, oos_res.metrics)
    mc = monte_carlo_equity(oos_res.trades["return"].to_numpy() if len(oos_res.trades) else [])
    out = {
        "is_metrics": is_res.stats,
        "oos_metrics": oos_res.stats,
        "gates": gates.to_dict(),
        "monte_carlo": mc.to_dict(),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0 if gates.passed else 2


def cmd_run(args) -> int:
    from quantbot.execution.engine import LiveEngine
    from quantbot.execution.paper_broker import PaperBroker
    from quantbot.strategies.registry import get_strategy

    s = get_settings()
    df = _load_frame(args.data)
    strat = get_strategy(args.strategy, **_resolve_params(args))
    broker = PaperBroker(starting_cash=args.equity, costs=s.costs)
    engine = LiveEngine(broker, {args.symbol: strat}, settings=s, starting_equity=args.equity)

    # Bar-by-bar replay (paper).  In live mode this loop is driven by the venue
    # market-data stream instead of a historical frame.
    warm = max(60, args.warmup)
    for i in range(warm, len(df)):
        engine.on_bar(args.symbol, df.iloc[: i + 1])
    print(f"Final equity: {engine.equity:.2f} | open positions: {len(engine.positions)}")
    return 0


def cmd_dashboard(args) -> int:
    import uvicorn

    from quantbot.monitoring.dashboard import create_app

    uvicorn.run(create_app(venue=args.venue), host=args.host, port=args.port)
    return 0


# ----------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("quantbot", description="Systematic crypto trading system")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("init-db"); d.add_argument("--schema", default="sql/schema.sql")
    d.set_defaults(func=cmd_init_db)

    d = sub.add_parser("download")
    d.add_argument("--symbol", required=True)
    d.add_argument("--timeframe", default="1h")
    d.add_argument("--since", default=None)
    d.add_argument("--exchange", default=None)
    d.add_argument("--store", action="store_true")
    d.add_argument("--out", default=None)
    d.set_defaults(func=cmd_download)

    d = sub.add_parser("backtest")
    d.add_argument("--strategy", required=True)
    d.add_argument("--data", required=True)
    d.add_argument("--timeframe", default="1h")
    d.add_argument("--params", default=None, help="JSON param dict")
    d.add_argument("--params-file", default=None,
                   help="Path to a JSON param dict or an optimize --out result")
    d.add_argument("--report", default=None, help="HTML report path")
    d.set_defaults(func=cmd_backtest)

    d = sub.add_parser("optimize")
    d.add_argument("--strategy", required=True)
    d.add_argument("--data", required=True)
    d.add_argument("--timeframe", default="1h")
    d.add_argument("--trials", type=int, default=60)
    d.add_argument("--out", default=None)
    d.set_defaults(func=cmd_optimize)

    d = sub.add_parser("validate")
    d.add_argument("--strategy", required=True)
    d.add_argument("--data", required=True)
    d.add_argument("--timeframe", default="1h")
    d.add_argument("--params", default=None)
    d.add_argument("--params-file", default=None,
                   help="Path to a JSON param dict or an optimize --out result")
    d.set_defaults(func=cmd_validate)

    d = sub.add_parser("run")
    d.add_argument("--strategy", required=True)
    d.add_argument("--symbol", required=True)
    d.add_argument("--data", required=True)
    d.add_argument("--timeframe", default="1h")
    d.add_argument("--params", default=None)
    d.add_argument("--params-file", default=None,
                   help="Path to a JSON param dict or an optimize --out result")
    d.add_argument("--equity", type=float, default=10_000.0)
    d.add_argument("--warmup", type=int, default=200)
    d.set_defaults(func=cmd_run)

    d = sub.add_parser("dashboard")
    d.add_argument("--host", default="0.0.0.0")
    d.add_argument("--port", type=int, default=8000)
    d.add_argument("--venue", default="paper")
    d.set_defaults(func=cmd_dashboard)
    return p


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
