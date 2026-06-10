"""Dependency-free SVG charts for equity curves and drawdowns."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _polyline(xs: np.ndarray, ys: np.ndarray, w: int, h: int, pad: int) -> str:
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    if x1 == x0:
        x1 = x0 + 1
    if y1 == y0:
        y1 = y0 + 1
    px = pad + (xs - x0) / (x1 - x0) * (w - 2 * pad)
    py = h - pad - (ys - y0) / (y1 - y0) * (h - 2 * pad)
    return " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(px, py))


def _downsample(series: pd.Series, max_points: int = 1200) -> pd.Series:
    if len(series) <= max_points:
        return series
    step = len(series) // max_points
    return series.iloc[::step]


def equity_svg(
    equity: pd.Series, width: int = 860, height: int = 280, title: str = "Equity curve"
) -> str:
    eq = _downsample(equity.dropna())
    if len(eq) < 2:
        return f"<svg width='{width}' height='{height}'><text x='10' y='20'>no data</text></svg>"
    xs = np.arange(len(eq), dtype=float)
    ys = eq.to_numpy(dtype=float)
    pts = _polyline(xs, ys, width, height, 36)
    final = ys[-1] / ys[0] - 1.0
    color = "#2e7d32" if final >= 0 else "#c62828"
    return (
        f"<svg width='{width}' height='{height}' xmlns='http://www.w3.org/2000/svg' "
        f"style='background:#fafafa;border:1px solid #ddd'>"
        f"<text x='12' y='20' font-family='monospace' font-size='13'>{title} "
        f"(total {final:+.1%})</text>"
        f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='1.5'/>"
        f"<text x='12' y='{height - 8}' font-family='monospace' font-size='10' fill='#666'>"
        f"{eq.index[0]} → {eq.index[-1]}</text></svg>"
    )


def drawdown_svg(
    equity: pd.Series, width: int = 860, height: int = 180, title: str = "Drawdown"
) -> str:
    eq = _downsample(equity.dropna())
    if len(eq) < 2:
        return f"<svg width='{width}' height='{height}'><text x='10' y='20'>no data</text></svg>"
    dd = (eq / eq.cummax() - 1.0).to_numpy(dtype=float)
    xs = np.arange(len(dd), dtype=float)
    pad = 30
    # Fill polygon down from zero.
    pts = _polyline(xs, dd, width, height, pad)
    worst = dd.min()
    return (
        f"<svg width='{width}' height='{height}' xmlns='http://www.w3.org/2000/svg' "
        f"style='background:#fafafa;border:1px solid #ddd'>"
        f"<text x='12' y='18' font-family='monospace' font-size='13'>{title} "
        f"(max {worst:.1%})</text>"
        f"<polyline points='{pts}' fill='none' stroke='#c62828' stroke-width='1.2'/>"
        f"</svg>"
    )
