"""QuantBot command-line interface.

Subcommands:
    init-db       apply the SQL schema
    download      fetch historical OHLCV and store it
    cache-data    download/incrementally update the local OHLCV cache
    discover      edge-discovery sweep: all signal families × universe,
                  full validation gauntlet, ranked leaderboard + reports
    backtest      run a single backtest and print/report metrics
    optimize      Bayesian parameter search (IS) with OOS validation
    validate      full validation pipeline + acceptance gates
    run           bar-replay paper trading from a historical file
    run-live      venue-driven loop: paper fills on live Hyperliquid data,
                  or live orders (validation report + dual switches required)
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


def _params_from_file(pf: str | None) -> dict:
    """Read a JSON param dict, or an optimize --out result (use its best_params)."""
    if not pf:
        return {}
    data = json.loads(Path(pf).read_text())
    if isinstance(data, dict) and "best_params" in data:
        return data["best_params"] or {}
    return data or {}


def _resolve_params(args) -> dict:
    """Strategy params from --params (inline JSON) or --params-file (a path).

    The file may be a bare param dict, or an optimizer result (as written by
    ``optimize --out ...``), in which case its ``best_params`` are used. This
    lets you feed tuned params straight back in without pasting JSON in the shell.
    """
    if getattr(args, "params", None):
        return json.loads(args.params)
    return _params_from_file(getattr(args, "params_file", None))


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
        Path(args.out).write_text(json.dumps(res.to_dict(), indent=2, default=str), encoding="utf-8")
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


def cmd_validate_portfolio(args) -> int:
    """Validate one strategy across several symbols as an equal-weight portfolio.

    Each ``--data`` file is paired (by position) with a ``--params-file``.  Each
    symbol is split 70/30 IS/OOS and backtested independently; we then build an
    equal-weight (1/N) portfolio return stream, pool the trades, and run the
    *same* acceptance gates + Monte Carlo on the combined result.  Diversifying
    across symbols lifts the trade count and usually the Sharpe (the streams are
    not perfectly correlated), which is the principled way to evaluate a
    strategy that trades too rarely on any single instrument.
    """
    import numpy as np
    import pandas as pd

    from quantbot.backtest.engine import BacktestEngine
    from quantbot.backtest.metrics import compute_metrics
    from quantbot.strategies.registry import get_strategy
    from quantbot.validation import evaluate_gates, is_oos_split, monte_carlo_equity

    s = get_settings()
    datas = args.data
    pfiles = list(args.params_file or [])
    pfiles += [None] * (len(datas) - len(pfiles))  # pad → defaults

    eng = BacktestEngine(costs=s.costs, risk_per_trade=s.risk.risk_per_trade)
    is_rets, oos_rets = [], []
    is_pnl: list[float] = []
    oos_pnl: list[float] = []
    oos_trade_rets: list[float] = []
    per_symbol = []

    for j, (data_path, pfile) in enumerate(zip(datas, pfiles)):
        df = _load_frame(data_path)
        params = _params_from_file(pfile)
        is_df, oos_df = is_oos_split(df, 0.70)
        is_res = eng.run(get_strategy(args.strategy, **params), is_df, args.timeframe)
        oos_res = eng.run(get_strategy(args.strategy, **params), oos_df, args.timeframe)
        is_rets.append(is_res.returns.rename(j))
        oos_rets.append(oos_res.returns.rename(j))
        if len(is_res.trades):
            is_pnl += is_res.trades["pnl"].tolist()
        if len(oos_res.trades):
            oos_pnl += oos_res.trades["pnl"].tolist()
            oos_trade_rets += oos_res.trades["return"].tolist()
        per_symbol.append({
            "data": data_path,
            "oos_sharpe": round(oos_res.metrics.sharpe, 3),
            "oos_profit_factor": round(oos_res.metrics.profit_factor, 3),
            "oos_return": round(oos_res.metrics.total_return, 4),
            "oos_trades": oos_res.metrics.n_trades,
        })

    def _portfolio_equity(rets: list[pd.Series]) -> pd.Series:
        # Equal-weight (1/N) average of per-symbol bar returns on the union index;
        # a bar where a symbol has no data counts as flat (0) for that sleeve.
        aligned = pd.concat(rets, axis=1).sort_index().fillna(0.0)
        port_ret = aligned.mean(axis=1)
        return (1.0 + port_ret).cumprod() * eng.initial_cash

    is_metrics = compute_metrics(_portfolio_equity(is_rets), args.timeframe, np.array(is_pnl))
    oos_metrics = compute_metrics(_portfolio_equity(oos_rets), args.timeframe, np.array(oos_pnl))
    gates = evaluate_gates(is_metrics, oos_metrics)
    mc = monte_carlo_equity(np.array(oos_trade_rets) if oos_trade_rets else [])
    out = {
        "n_symbols": len(datas),
        "per_symbol": per_symbol,
        "portfolio_is_metrics": is_metrics.to_dict(),
        "portfolio_oos_metrics": oos_metrics.to_dict(),
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


def cmd_run_live(args) -> int:
    """Venue-driven trading loop (paper fills on live data, or live orders)."""
    from quantbot.execution.live_runner import run_from_config

    return run_from_config(args.config)


def cmd_cache_data(args) -> int:
    from quantbot.data.cache import DataCache

    cache = DataCache(args.cache_dir)
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    panel = cache.update_universe(symbols, args.timeframe, args.exchange, args.since)
    for sym, df in panel.items():
        print(f"{sym:14s} {len(df):7d} bars  {df.index[0]} → {df.index[-1]}")
    missing = set(symbols) - set(panel)
    if missing:
        print(f"FAILED: {sorted(missing)}")
        return 1
    return 0


def cmd_discover(args) -> int:
    """Run the edge-discovery sweep from a YAML config (or CLI flags)."""
    from quantbot.config_files import discovery_config_from_yaml
    from quantbot.data.cache import DataCache, load_panel
    from quantbot.reporting.research_report import write_research_report
    from quantbot.research.discovery import DiscoveryConfig, run_discovery

    if args.config:
        cfg, raw = discovery_config_from_yaml(args.config)
        data_cfg = raw.get("data", {})
        out_dir = raw.get("output", {}).get("dir", "reports/research")
        symbols = data_cfg.get("symbols", [])
        exchange = data_cfg.get("exchange", "binance")
        cache_dir = data_cfg.get("cache_dir", "data_cache")
        since = data_cfg.get("since")
        refresh = bool(data_cfg.get("refresh", True))
    else:
        cfg = DiscoveryConfig(timeframe=args.timeframe)
        symbols = [s.strip() for s in (args.symbols or "").split(",") if s.strip()]
        exchange, cache_dir, since, refresh = args.exchange, args.cache_dir, args.since, not args.offline
        out_dir = args.out

    if not symbols:
        raise SystemExit("no symbols configured (use --config or --symbols)")

    cache = DataCache(cache_dir)
    if refresh:
        panel = cache.update_universe(symbols, cfg.timeframe, exchange, since)
    else:
        panel = load_panel(cache, symbols, cfg.timeframe, exchange)
    if not panel:
        raise SystemExit(
            "no data available — run `quantbot cache-data` first or enable data.refresh"
        )

    result = run_discovery(panel, cfg)
    paths = write_research_report(result, out_dir)
    print(f"\nValidated {len(result.candidates)} candidates "
          f"({result.n_trials} trials) in {result.runtime_s}s")
    if result.found_edge:
        print(f"Selected {len(result.selected)} robust edge(s):")
        for cv in result.selected:
            print(f"  {cv.robustness_score:6.1f}  {cv.signal_name:24s} "
                  f"[{'+'.join(cv.symbols)}]  OOS Sharpe {cv.oos_stats['sharpe']:.2f}  "
                  f"DSR {cv.deflated_prob:.2f}")
    else:
        print("NO ROBUST EDGE FOUND — no candidate cleared every gate. "
              "Do not deploy; widen data, not gates.")
    for k, v in paths.items():
        print(f"  {k}: {v}")
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

    d = sub.add_parser("validate-portfolio",
                       help="Validate a strategy across several symbols (equal-weight)")
    d.add_argument("--strategy", required=True)
    d.add_argument("--data", action="append", required=True,
                   help="Repeat per symbol; paired by position with --params-file")
    d.add_argument("--params-file", action="append", default=None,
                   help="Repeat per symbol (optimize --out result or param dict)")
    d.add_argument("--timeframe", default="1h")
    d.set_defaults(func=cmd_validate_portfolio)

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

    d = sub.add_parser("run-live",
                       help="Venue-driven loop: paper fills on live Hyperliquid data, "
                            "or live orders (requires validation + both live switches)")
    d.add_argument("--config", required=True, help="YAML config (config/live.example.yaml)")
    d.set_defaults(func=cmd_run_live)

    d = sub.add_parser("cache-data",
                       help="Download/incrementally update the local OHLCV cache")
    d.add_argument("--symbols", required=True, help="comma-separated, e.g. BTC/USDT,ETH/USDT")
    d.add_argument("--timeframe", default="1h")
    d.add_argument("--exchange", default="binance")
    d.add_argument("--since", default=None)
    d.add_argument("--cache-dir", default="data_cache")
    d.set_defaults(func=cmd_cache_data)

    d = sub.add_parser("discover",
                       help="Run the full edge-discovery sweep + validation gauntlet")
    d.add_argument("--config", default=None, help="YAML config (config/discovery.example.yaml)")
    d.add_argument("--symbols", default=None, help="comma-separated (if no --config)")
    d.add_argument("--timeframe", default="1h")
    d.add_argument("--exchange", default="binance")
    d.add_argument("--since", default=None)
    d.add_argument("--cache-dir", default="data_cache")
    d.add_argument("--offline", action="store_true", help="use cache only, no downloads")
    d.add_argument("--out", default="reports/research")
    d.set_defaults(func=cmd_discover)
    return p


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
