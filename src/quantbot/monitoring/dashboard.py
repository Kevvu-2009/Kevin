"""FastAPI monitoring dashboard.

Exposes a JSON API and a single-page Plotly dashboard showing:
  open positions, daily/weekly PnL, equity curve, drawdown, active strategies,
  and live risk metrics.

Data is read from PostgreSQL (``equity_curve``, ``positions``, ``risk_events``)
when reachable; otherwise the endpoints degrade gracefully to whatever an
attached live engine exposes (or empty data), so the dashboard never 500s in a
fresh environment.

Run:  uvicorn quantbot.monitoring.dashboard:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from typing import Any

from quantbot.logging_setup import get_logger

log = get_logger("monitoring.dashboard")


def _load_equity_curve(venue: str = "paper") -> dict[str, list]:
    try:
        from sqlalchemy import text

        from quantbot.data.db import get_engine

        with get_engine().connect() as conn:
            rows = conn.execute(
                text("SELECT ts, equity, drawdown FROM equity_curve WHERE venue=:v ORDER BY ts ASC"),
                {"v": venue},
            ).fetchall()
        return {
            "ts": [str(r[0]) for r in rows],
            "equity": [float(r[1]) for r in rows],
            "drawdown": [float(r[2]) for r in rows],
        }
    except Exception as e:  # pragma: no cover
        log.warning("equity_curve_unavailable", error=str(e))
        return {"ts": [], "equity": [], "drawdown": []}


def _load_positions(venue: str = "paper") -> list[dict]:
    try:
        from sqlalchemy import text

        from quantbot.data.db import get_engine

        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT symbol, qty, avg_price, stop_price, strategy_name, realized_pnl "
                    "FROM positions WHERE venue=:v AND closed_at IS NULL"
                ),
                {"v": venue},
            ).fetchall()
        return [
            {
                "symbol": r[0], "qty": float(r[1]), "avg_price": float(r[2]),
                "stop_price": float(r[3]) if r[3] is not None else None,
                "strategy": r[4], "realized_pnl": float(r[5]),
            }
            for r in rows
        ]
    except Exception:  # pragma: no cover
        return []


def build_summary(venue: str = "paper", engine: Any = None) -> dict:
    """Build the dashboard summary payload."""
    eq = _load_equity_curve(venue)
    positions = _load_positions(venue)

    # Prefer a live engine's in-memory numbers if attached.
    if engine is not None:
        equity = engine.equity
        rs = engine.risk.state
        daily = engine.risk.daily_pnl_pct()
        weekly = engine.risk.weekly_pnl_pct()
        dd = engine.risk.current_drawdown()
        positions = [
            {"symbol": s, "qty": p.qty, "avg_price": p.entry_price,
             "stop_price": p.stop_price, "strategy": p.strategy_name}
            for s, p in engine.positions.items()
        ]
        kill = rs.kill_switch_active
        strategies = sorted({p["strategy"] for p in positions}) or list(
            getattr(engine, "strategies", {}).keys()
        )
    else:
        equity = eq["equity"][-1] if eq["equity"] else 0.0
        daily = weekly = 0.0
        dd = eq["drawdown"][-1] if eq["drawdown"] else 0.0
        kill = False
        strategies = sorted({p["strategy"] for p in positions if p.get("strategy")})

    return {
        "equity": equity,
        "daily_pnl_pct": daily,
        "weekly_pnl_pct": weekly,
        "drawdown": dd,
        "kill_switch_active": kill,
        "open_positions": positions,
        "active_strategies": strategies,
        "equity_curve": eq,
    }


def create_app(venue: str = "paper", engine: Any = None):
    """Create the FastAPI app (lazy import of fastapi)."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="QuantBot Dashboard", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/summary")
    def summary() -> JSONResponse:
        return JSONResponse(build_summary(venue, engine))

    @app.get("/api/positions")
    def positions() -> JSONResponse:
        return JSONResponse(build_summary(venue, engine)["open_positions"])

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    return app


_INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>QuantBot Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
  <style>
    body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#0e1117;color:#e6e6e6}
    header{padding:16px 24px;background:#161b22;border-bottom:1px solid #30363d}
    h1{font-size:18px;margin:0}
    .cards{display:flex;gap:16px;flex-wrap:wrap;padding:16px 24px}
    .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;min-width:160px}
    .card .label{font-size:12px;color:#8b949e}
    .card .value{font-size:22px;font-weight:600;margin-top:6px}
    .pos{padding:0 24px}
    table{width:100%;border-collapse:collapse;background:#161b22;border-radius:10px;overflow:hidden}
    th,td{padding:8px 12px;border-bottom:1px solid #30363d;text-align:left;font-size:13px}
    .kill{color:#ff6b6b;font-weight:700}
    #equity{padding:16px 24px}
    .neg{color:#ff6b6b}.pos-v{color:#3fb950}
  </style>
</head>
<body>
  <header><h1>QuantBot — Live Monitoring</h1></header>
  <div class="cards" id="cards"></div>
  <div id="equity"></div>
  <div class="pos"><h3>Open Positions</h3><table id="postable">
    <thead><tr><th>Symbol</th><th>Qty</th><th>Avg Price</th><th>Stop</th><th>Strategy</th></tr></thead>
    <tbody></tbody></table></div>
<script>
async function refresh(){
  const s = await (await fetch('/api/summary')).json();
  const pct = x => (x*100).toFixed(2)+'%';
  const cls = x => x>=0?'pos-v':'neg';
  document.getElementById('cards').innerHTML = `
    <div class="card"><div class="label">Equity</div><div class="value">$${s.equity.toFixed(2)}</div></div>
    <div class="card"><div class="label">Daily PnL</div><div class="value ${cls(s.daily_pnl_pct)}">${pct(s.daily_pnl_pct)}</div></div>
    <div class="card"><div class="label">Weekly PnL</div><div class="value ${cls(s.weekly_pnl_pct)}">${pct(s.weekly_pnl_pct)}</div></div>
    <div class="card"><div class="label">Drawdown</div><div class="value neg">${pct(s.drawdown)}</div></div>
    <div class="card"><div class="label">Open Positions</div><div class="value">${s.open_positions.length}</div></div>
    <div class="card"><div class="label">Kill Switch</div><div class="value ${s.kill_switch_active?'kill':''}">${s.kill_switch_active?'TRIPPED':'armed'}</div></div>
    <div class="card"><div class="label">Active Strategies</div><div class="value">${s.active_strategies.join(', ')||'—'}</div></div>`;
  const ec = s.equity_curve;
  Plotly.newPlot('equity',[
    {x:ec.ts,y:ec.equity,name:'Equity',type:'scatter'},
    {x:ec.ts,y:ec.drawdown,name:'Drawdown',yaxis:'y2',fill:'tozeroy',line:{color:'crimson'}}
  ],{template:'plotly_dark',paper_bgcolor:'#0e1117',plot_bgcolor:'#0e1117',font:{color:'#e6e6e6'},
     title:'Equity & Drawdown',yaxis2:{overlaying:'y',side:'right',title:'DD'},height:420});
  const tb = document.querySelector('#postable tbody');
  tb.innerHTML = s.open_positions.map(p=>`<tr><td>${p.symbol}</td><td>${p.qty.toFixed(4)}</td>
    <td>${p.avg_price.toFixed(2)}</td><td>${p.stop_price?p.stop_price.toFixed(2):'—'}</td>
    <td>${p.strategy||''}</td></tr>`).join('');
}
refresh(); setInterval(refresh, 5000);
</script>
</body>
</html>
"""


# Module-level app for `uvicorn quantbot.monitoring.dashboard:app`.
def _default_app():  # pragma: no cover - import-time convenience
    try:
        return create_app()
    except Exception:
        return None


app = _default_app()
