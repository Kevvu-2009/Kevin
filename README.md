# QuantBot — Systematic Crypto Day/Swing Trading System

A production-oriented, **fully rule-based** crypto trading system targeting a
**1–14 day holding period** (between day trading and swing trading). It
develops, backtests, validates, and deploys strategies automatically, and only
promotes strategies that clear strict profitability and risk gates.

> **No discretion.** Every entry, exit, stop, size, and kill-switch is a rule.
> The same indicator/strategy code path is used in backtest, paper, and live so
> there is no train/serve skew.

---

## Highlights

| Area | What's implemented |
|------|--------------------|
| **Data layer** | CCXT OHLCV download (paginated, retrying), PostgreSQL storage (idempotent upsert), data-quality validation (gaps/dupes/OHLC sanity/NaN/anomalies) |
| **Research** | Plug-and-play `Strategy` framework + 4 strategies: Trend Following, Momentum Breakout, Mean Reversion, Regime-Adaptive |
| **Backtesting** | Event-driven engine with **fees, slippage, latency (next-bar fills)**, trailing ATR stops, risk-based sizing; full metric set (CAGR, Sharpe, Sortino, Calmar, MaxDD, win rate, profit factor, avg trade, expectancy) |
| **Validation** | 70/30 IS/OOS, walk-forward, Monte Carlo, parameter sensitivity, hard acceptance gates |
| **Optimization** | Bayesian (Optuna TPE) with random-search fallback; composite objective that penalises drawdown and the IS↔OOS gap to fight overfitting |
| **Risk** | Fixed-fractional & volatility-adjusted sizing (0.5–1%/trade), 5-position cap, 3% daily / 8% weekly loss limits, 20% drawdown kill switch |
| **Execution** | Venue-agnostic engine, order manager with retries + idempotency, paper broker, state persistence |
| **Integrations** | **Hyperliquid (spot + perps — recommended for OHLCV strategies, key-based API)**, Polymarket (CLOB, prediction markets), Bullpen (scaffold); env-var credentials |
| **Monitoring** | FastAPI + Plotly dashboard: positions, daily/weekly PnL, equity curve, drawdown, active strategies, risk metrics |
| **Ops** | Dockerfile, docker-compose (Postgres+Redis+dashboard+engine), structured logging, runbook |

## Acceptance gates (a strategy deploys only if **all** pass)

- Positive **out-of-sample** total return
- **Sharpe ≥ 1.2** (OOS)
- **Profit factor ≥ 1.3** (OOS)
- **Max drawdown ≤ 20%** (worst of IS/OOS)
- ≥ 30 OOS trades (significance)
- OOS/IS Sharpe ratio ≥ 0.5 (overfit detector)
- Non-catastrophic across regimes

See [`docs/STRATEGY_REPORT.md`](docs/STRATEGY_REPORT.md) for the rationale,
failure modes, and deployment recommendations.

---

## Quick start (offline demo — no API keys, no DB)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # or: pip install numpy pandas scipy for the core only
pip install -e .

# Run the full pipeline on synthetic data: backtest all strategies,
# optimize, validate, and print the gate verdict.
PYTHONPATH=src python scripts/run_example_backtest.py
```

Artifacts (per-strategy metrics, optimization results, validation summary) are
written to `reports/`.

### Run the test suite

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src pytest -q
```

### CLI

```bash
# Download + store OHLCV (needs DB / network)
python -m quantbot.cli download --symbol BTC/USDT --timeframe 4h --since 2022-01-01 --store

# Backtest with an HTML report
python -m quantbot.cli backtest --strategy momentum_breakout --data BTC_4h.parquet \
    --timeframe 4h --report reports/breakout.html

# Optimize (Bayesian) then validate against the gates
python -m quantbot.cli optimize --strategy trend_following --data BTC_4h.parquet --timeframe 4h --trials 100
python -m quantbot.cli validate --strategy trend_following --data BTC_4h.parquet --timeframe 4h

# Paper-trade (bar replay) and launch the dashboard
python -m quantbot.cli run --strategy trend_following --symbol BTC/USDT --data BTC_4h.parquet --timeframe 4h
python -m quantbot.cli dashboard --port 8000
```

### Docker

```bash
cp .env.example .env          # fill in credentials/limits
docker compose -f docker/docker-compose.yml --env-file .env up -d
# dashboard -> http://localhost:8000
```

---

## Project layout

```
src/quantbot/
├── config.py            # env-driven settings, risk + cost configs
├── logging_setup.py     # structured logging (structlog + stdlib shim)
├── cli.py               # init-db / download / backtest / optimize / validate / run / dashboard
├── data/                # downloader, db, repository, quality, synthetic
├── strategies/          # base, registry, indicators + 4 strategies
├── backtest/            # engine (fees/slippage/latency), metrics, report
├── validation/          # splits, walk_forward, monte_carlo, sensitivity, gates
├── optimization/        # Bayesian optimizer (+ random fallback)
├── risk/                # position_sizing, portfolio controls / kill switch
├── execution/           # live engine, order_manager, paper_broker, state
├── integrations/        # base venue interface, bullpen, polymarket
└── monitoring/          # FastAPI + Plotly dashboard
sql/schema.sql           # PostgreSQL schema
docker/                  # Dockerfile + docker-compose
tests/                   # unit tests (analytics run offline)
scripts/run_example_backtest.py
docs/                    # INSTALLATION, RUNBOOK, STRATEGY_REPORT
```

## Design notes / safety

- **Heavy deps are lazy.** Core analytics import only numpy/pandas/scipy, so the
  test suite and the demo run anywhere; CCXT, SQLAlchemy, Optuna, FastAPI, the
  Polymarket SDK, etc. are imported only where used.
- **No look-ahead.** Signals are formed at bar close and filled on the next bar;
  Donchian/Bollinger references use the prior bar.
- **Credentials only via env.** Nothing is committed. See `.env.example`.
- **Paper-first.** Default `QUANTBOT_MODE=paper`. Going live is an explicit,
  documented switch (see the runbook).

> ⚠️ Trading crypto is risky. Backtested/forward results do not guarantee future
> performance. Use the paper mode and small size first. This is software, not
> financial advice.
