"""Research-report generation: leaderboard CSV, markdown summary, HTML dossier.

The report's job is decision support: which edges survived, *why* we believe
them (economic rationale + every robustness number), and which were rejected
for what reason.  Rejections are first-class content — they are the evidence
the process has teeth.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

from quantbot.research.discovery import DiscoveryResult
from quantbot.research.signals import SIGNAL_REGISTRY
from quantbot.research.validation import CandidateValidation


def _fmt_pct(x: float) -> str:
    return f"{x:+.1%}" if pd.notna(x) else "n/a"


def _md_table(df: pd.DataFrame) -> str:
    """Minimal GitHub-markdown table (avoids the tabulate dependency)."""
    cols = list(df.columns)
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    rows = ["| " + " | ".join(str(v) for v in rec) + " |" for rec in df.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


def _candidate_md(cv: CandidateValidation, rank: int | None = None) -> str:
    cls = SIGNAL_REGISTRY.get(cv.signal_name)
    head = f"### {'#%d — ' % rank if rank else ''}`{cv.signal_name}` on {'+'.join(cv.symbols)}"
    lines = [head, ""]
    lines.append(f"- **Family:** {cv.family}  |  **Timeframe:** {cv.timeframe}  |  "
                 f"**Robustness score:** {cv.robustness_score}/100")
    lines.append(f"- **Best params (fit on IS only):** `{cv.best_params}`")
    o = cv.oos_stats
    lines.append(
        f"- **OOS:** Sharpe {o.get('sharpe', 0):.2f} | CAGR {_fmt_pct(o.get('cagr', 0))} | "
        f"PF {o.get('profit_factor', 0):.2f} | win {o.get('win_rate', 0):.0%} | "
        f"maxDD {_fmt_pct(o.get('max_drawdown', 0))} | {o.get('n_trades', 0)} trades | "
        f"exposure {o.get('exposure', 0):.0%}"
    )
    lines.append(
        f"- **Walk-forward:** Sharpe {cv.walk_forward.get('sharpe', 0):.2f}, "
        f"{cv.walk_forward.get('positive_window_frac', 0):.0%} windows positive"
    )
    mc = cv.monte_carlo
    lines.append(
        f"- **Monte Carlo (block bootstrap):** p05 maxDD {_fmt_pct(mc.get('max_dd_p05', 0))}, "
        f"P(loss) {mc.get('prob_loss', 1):.0%}"
    )
    lines.append(
        f"- **Parameter sensitivity:** grid retention {cv.sensitivity.get('retention', 0):.2f} "
        f"({cv.sensitivity.get('positive_frac', 0):.0%} of grid profitable)"
    )
    lines.append(
        f"- **Deflated Sharpe:** P(true SR>0) = {cv.deflated_prob:.2f} after {cv.n_trials} trials | "
        f"**+1-bar-lag Sharpe:** {cv.lag_stress.get('sharpe', 0):.2f}"
    )
    if cv.regimes.get("per_regime"):
        worst = min(cv.regimes["per_regime"].items(), key=lambda kv: kv[1]["sharpe"])
        lines.append(f"- **Worst regime:** {worst[0]} (Sharpe {worst[1]['sharpe']:.2f}, "
                     f"DD {_fmt_pct(worst[1]['max_drawdown'])})")
    if cls is not None:
        lines.append(f"- **Why it should work:** {cls.thesis}")
        lines.append(f"- **Why it may persist:** {cls.persistence}")
        lines.append(f"- **What kills it:** {cls.risks}")
    if not cv.gates.passed:
        lines.append(f"- **REJECTED:** {'; '.join(cv.gates.reasons)}")
    lines.append("")
    return "\n".join(lines)


def render_markdown(result: DiscoveryResult, title: str = "Edge Discovery Report") -> str:
    lines = [f"# {title}", ""]
    lines.append(f"- Universe: {', '.join(result.universe)} @ {result.timeframe}")
    lines.append(f"- Candidates validated: {len(result.candidates)} "
                 f"({result.n_trials} parameter evaluations charged to DSR)")
    lines.append(f"- Survivors: **{len(result.selected)}** | Runtime: {result.runtime_s}s")
    lines.append("")
    for note in result.notes:
        lines.append(f"> {note}")
    lines.append("")

    if result.selected:
        lines.append("## Selected edges (ranked by robustness)")
        lines.append("")
        for i, cv in enumerate(result.selected, 1):
            lines.append(_candidate_md(cv, rank=i))
    else:
        lines.append("## No robust edge found")
        lines.append("")
        lines.append(
            "No candidate cleared every gate. The correct action is to widen "
            "the data (more history, more symbols), not the gates."
        )
        lines.append("")

    lines.append("## Full leaderboard")
    lines.append("")
    if len(result.leaderboard):
        cols = [
            "signal", "symbols", "passed", "robustness_score", "oos_sharpe",
            "oos_total_return", "oos_max_dd", "oos_profit_factor", "oos_trades",
            "wf_positive_windows", "deflated_prob",
        ]
        df = result.leaderboard[cols].copy()
        df["oos_total_return"] = df["oos_total_return"].map(lambda v: f"{v:+.1%}")
        df["oos_max_dd"] = df["oos_max_dd"].map(lambda v: f"{v:+.1%}")
        for c in ("oos_sharpe", "oos_profit_factor", "deflated_prob", "wf_positive_windows"):
            df[c] = df[c].map(lambda v: f"{v:.2f}")
        lines.append(_md_table(df))
    lines.append("")

    lines.append("## Rejected candidates — reasons")
    lines.append("")
    rejected = [cv for cv in result.candidates if not cv.gates.passed]
    for cv in rejected:
        lines.append(f"- `{cv.signal_name}` [{'+'.join(cv.symbols)}]: "
                     f"{'; '.join(cv.gates.reasons) or 'failed'}")
    lines.append("")
    return "\n".join(lines)


def render_html(
    result: DiscoveryResult,
    title: str = "Edge Discovery Report",
    equity_curves: dict[str, pd.Series] | None = None,
) -> str:
    from quantbot.reporting.charts import drawdown_svg, equity_svg

    md_body = html.escape(render_markdown(result, title))
    charts = []
    for label, eq in (equity_curves or {}).items():
        charts.append(f"<h3>{html.escape(label)}</h3>")
        charts.append(equity_svg(eq, title=f"{label} — OOS equity"))
        charts.append(drawdown_svg(eq, title=f"{label} — drawdown"))
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:ui-monospace,Menlo,monospace;max-width:980px;"
        "margin:24px auto;padding:0 16px;color:#222}pre{white-space:pre-wrap;"
        "background:#f6f6f6;padding:16px;border-radius:6px}</style></head>"
        f"<body><h1>{html.escape(title)}</h1>{''.join(charts)}"
        f"<pre>{md_body}</pre></body></html>"
    )


def write_research_report(
    result: DiscoveryResult,
    out_dir: str | Path,
    title: str = "Edge Discovery Report",
    equity_curves: dict[str, pd.Series] | None = None,
) -> dict[str, Path]:
    """Write leaderboard.csv, report.md, report.html, summary.json.

    Returns the paths written.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    csv_path = out / "leaderboard.csv"
    result.leaderboard.to_csv(csv_path, index=False)
    paths["leaderboard_csv"] = csv_path

    md_path = out / "report.md"
    md_path.write_text(render_markdown(result, title), encoding="utf-8")
    paths["report_md"] = md_path

    html_path = out / "report.html"
    html_path.write_text(render_html(result, title, equity_curves), encoding="utf-8")
    paths["report_html"] = html_path

    summary = {
        "universe": list(result.universe),
        "timeframe": result.timeframe,
        "n_candidates": len(result.candidates),
        "n_trials": result.n_trials,
        "n_selected": len(result.selected),
        "found_edge": result.found_edge,
        "selected": [
            {
                "signal": cv.signal_name,
                "symbols": list(cv.symbols),
                "params": cv.best_params,
                "robustness_score": cv.robustness_score,
                "oos_sharpe": cv.oos_stats.get("sharpe"),
                "deflated_prob": cv.deflated_prob,
            }
            for cv in result.selected
        ],
        "notes": result.notes,
    }
    json_path = out / "summary.json"
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    paths["summary_json"] = json_path
    return paths
