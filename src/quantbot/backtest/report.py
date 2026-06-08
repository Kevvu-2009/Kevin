"""Backtest reporting — text summary + interactive Plotly HTML report."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quantbot.backtest.engine import BacktestResult
from quantbot.backtest.metrics import drawdown_series


def metrics_table(result: BacktestResult) -> str:
    m = result.stats
    rows = [
        ("CAGR", f"{m['cagr']:.2%}"),
        ("Total Return", f"{m['total_return']:.2%}"),
        ("Sharpe", f"{m['sharpe']:.2f}"),
        ("Sortino", f"{m['sortino']:.2f}"),
        ("Calmar", f"{m['calmar']:.2f}"),
        ("Max Drawdown", f"{m['max_drawdown']:.2%}"),
        ("Volatility (ann.)", f"{m['volatility']:.2%}"),
        ("Win Rate", f"{m['win_rate']:.2%}"),
        ("Profit Factor", f"{m['profit_factor']:.2f}"),
        ("Avg Trade", f"{m['avg_trade']:.2f}"),
        ("Expectancy", f"{m['expectancy']:.2f}"),
        ("# Trades", f"{m['n_trades']}"),
    ]
    width = max(len(k) for k, _ in rows)
    return "\n".join(f"{k.ljust(width)} : {v}" for k, v in rows)


def to_json(result: BacktestResult, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timeframe": result.timeframe,
        "metrics": result.stats,
        "n_trades": int(len(result.trades)),
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def html_report(result: BacktestResult, path: str | Path, title: str = "Backtest") -> Path:
    """Render an interactive HTML report.  Requires plotly (lazy import)."""
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    dd = drawdown_series(result.equity)
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
        subplot_titles=("Equity Curve", "Drawdown"), vertical_spacing=0.08,
    )
    fig.add_trace(
        go.Scatter(x=result.equity.index, y=result.equity.values, name="Equity"),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=dd.index, y=dd.values, name="Drawdown", fill="tozeroy",
                   line=dict(color="crimson")),
        row=2, col=1,
    )
    m = result.stats
    subtitle = (
        f"CAGR {m['cagr']:.1%} | Sharpe {m['sharpe']:.2f} | "
        f"MaxDD {m['max_drawdown']:.1%} | PF {m['profit_factor']:.2f} | "
        f"Trades {m['n_trades']}"
    )
    fig.update_layout(title=f"{title}<br><sub>{subtitle}</sub>", template="plotly_dark", height=720)
    fig.write_html(str(path), include_plotlyjs="cdn")
    return path


def trades_to_csv(result: BacktestResult, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result.trades.to_csv(path, index=False)
    return path
