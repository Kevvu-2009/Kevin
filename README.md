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
| **Data layer** | Multi-exchange OHLCV via CCXT (binance/bybit/kraken/coinbase) + native Hyperliquid; **local cache with incremental updates**; PostgreSQL storage; data-quality validation (gaps/dupes/OHLC sanity/NaN/anomalies) |
| **Edge discovery** | **34 research signals across 9 families** (trend, momentum, mean-reversion, volatility, market structure, regime, statistical arbitrage, ML, hybrid), each with a documented thesis / persistence argument / failure modes; vectorized cost-aware screening engine; ranked robustness leaderboard |
| **Validation gauntlet** | IS/OOS split, walk-forward re-fitting, block-bootstrap Monte Carlo, parameter-plateau analysis, regime breakdown, +1-bar execution-lag stress, **deflated Sharpe ratio** charged with the full sweep's trial count; hard accept/reject gates; null/power **calibration harness** |
| **Feature/ML layer** | Causal feature library (37 features: returns/vol/trend/flow/session/multi-timeframe), **purged & embargoed K-fold CV**, walk-forward model refits (logistic/RF/HistGB/XGBoost-optional/ensemble), probability-thresholded signals |
| **Backtesting** | Event-driven engine with **fees, slippage, latency (next-bar fills)**, trailing ATR stops, risk-based sizing; full metric set (CAGR, Sharpe, Sortino, Calmar, MaxDD, win rate, profit factor, expectancy, exposure, recovery factor) |
| **Optimization** | Bayesian (Optuna TPE) with random-search fallback; composite objective that penalises drawdown and the IS↔OOS gap to fight overfitting |
| **Risk** | Fixed-fractional & volatility-adjusted sizing (0.5–1%/trade), 5-position cap, 3% daily / 8% weekly loss limits, 20% drawdown kill switch |
| **Execution** | Venue-agnostic engine, order manager with retries + idempotency, paper broker, state persistence |
| **Hyperliquid** | Spot + perps; market/limit/**stop-loss & take-profit trigger orders**, reduce-only, leverage control, **rate limiting + auto-reconnect with backoff**, testnet mode, env-var credentials |
| **Monitoring** | FastAPI + Plotly dashboard: positions, daily/weekly PnL, equity curve, drawdown, active strategies, risk metrics |
| **Ops** | Dockerfile, docker-compose (Postgres+Redis+dashboard+engine), structured logging, runbook, research workflow docs |

## Acceptance gates (a strategy deploys only if **all** pass)

- Positive **out-of-sample** total return
- **Sharpe ≥ 1.2** (OOS)
- **Profit factor ≥ 1.3** (OOS)
- **Max drawdown ≤ 20%** (worst of IS/OOS)
- ≥ 30 OOS trades (significance)
- OOS/IS Sharpe ratio ≥ 0.5 (overfit detector)
- Non-catastrophic across regimes

See [`docs/STRATEGY_REPORT.md`](docs/STRATEGY_REPORT.md) for the rationale,
failure modes, and deployment recommendations, and
[`docs/RESEARCH_FINDINGS.md`](docs/RESEARCH_FINDINGS.md) for the current
state of edge validation (what is and is **not** yet proven).

---

## Edge discovery (the core workflow)

The system does not assume any strategy is profitable. It sweeps 34 candidate
signals across 9 families, validates each with the full gauntlet (IS/OOS,
walk-forward, Monte Carlo, parameter plateau, regime breakdown, lag stress,
deflated Sharpe vs the whole sweep's trial count), and selects only candidates
that clear **every** gate:

```bash
# 1. Prove the harness: must reject martingale data, must find planted trends.
python scripts/run_edge_discovery.py --calibrate

# 2. Build the data cache (incremental; re-runs only fetch new bars).
python -m quantbot.cli cache-data --symbols "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT" \
    --timeframe 1h --exchange binance --since 2021-01-01

# 3. Run discovery and read the verdict.
cp config/discovery.example.yaml config/discovery.yaml
python -m quantbot.cli discover --config config/discovery.yaml
# -> reports/research/{leaderboard.csv, report.md, report.html, summary.json}
```

If no candidate survives, the report says **NO ROBUST EDGE FOUND** — that is a
result, not a failure. See [`docs/RESEARCH_WORKFLOW.md`](docs/RESEARCH_WORKFLOW.md)
for the full operating procedure from discovery through paper trading to live.

---

## Quick start (offline demo — no API keys, no DB)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # or: pip install numpy pandas scipy scikit-learn for the core
pip install -e .

# Calibrate the discovery harness on synthetic data (null + power tests).
PYTHONPATH=src python scripts/run_edge_discovery.py --calibrate

# Event-engine demo: backtest all deployable strategies, optimize, validate.
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
# Incrementally cache OHLCV locally (multi-exchange, no DB needed)
python -m quantbot.cli cache-data --symbols "BTC/USDT,ETH/USDT" --timeframe 1h \
    --exchange binance --since 2021-01-01

# Edge discovery: sweep all signal families, validate, rank, report
python -m quantbot.cli discover --config config/discovery.yaml
python -m quantbot.cli discover --symbols "BTC/USDT,ETH/USDT" --offline   # cache-only

# Download + store OHLCV in PostgreSQL (needs DB / network)
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
├── config_files.py      # YAML config loading (discovery / live)
├── logging_setup.py     # structured logging (structlog + stdlib shim)
├── cli.py               # init-db/download/cache-data/discover/backtest/optimize/validate/run/dashboard
├── data/                # downloader (ccxt), cache (incremental), db, repository, quality, synthetic
├── features/            # causal feature library + label construction (incl. triple-barrier)
├── research/            # EDGE DISCOVERY: vector engine, 34 signals in 9 families,
│   ├── signals/         #   validation gauntlet (WF/MC/sensitivity/DSR/regimes/lag),
│   └── ...              #   discovery orchestrator, regime detection
├── models/              # purged+embargoed CV, model zoo, walk-forward ML pipeline
├── strategies/          # deployable event-engine strategies (base, registry, indicators)
├── backtest/            # event-driven engine (fees/slippage/latency), metrics, report
├── validation/          # event-engine validation: splits, walk_forward, monte_carlo, gates
├── optimization/        # Bayesian optimizer (+ random fallback)
├── risk/                # position_sizing, portfolio controls / kill switch
├── execution/           # live engine, order_manager, paper_broker, state
├── integrations/        # venue interface; hyperliquid (orders/triggers/leverage/rate-limit)
├── reporting/           # SVG charts, research report writer (md/html/csv/json)
└── monitoring/          # FastAPI + Plotly dashboard
config/                  # discovery.example.yaml, live.example.yaml
sql/schema.sql           # PostgreSQL schema
docker/                  # Dockerfile + docker-compose
tests/                   # unit + integration tests (all run offline)
scripts/                 # run_edge_discovery.py, run_example_backtest.py, smoke tests
docs/                    # INSTALLATION, RUNBOOK, RESEARCH_WORKFLOW, RESEARCH_FINDINGS, STRATEGY_REPORT
```

Mapping to the canonical research-stack layout: `/data → quantbot/data`,
`/research → quantbot/research`, `/backtesting → quantbot/backtest` (+
`quantbot/research/vector_engine.py`), `/strategies → quantbot/strategies` (+
`research/signals`), `/features → quantbot/features`, `/models →
quantbot/models`, `/execution → quantbot/execution` (+ `integrations`),
`/risk → quantbot/risk`, `/database → quantbot/data/db.py` + `sql/`, `/api →
quantbot/monitoring`, `/reporting → quantbot/reporting`, `/config → config/`
+ `quantbot/config.py`, `/tests → tests/`.

## Design notes / safety

- **Heavy deps are lazy.** Core analytics import only numpy/pandas/scipy, so the
  test suite and the demo run anywhere; CCXT, SQLAlchemy, Optuna, FastAPI, the
  Hyperliquid SDK, etc. are imported only where used.
- **No look-ahead.** Signals are formed at bar close and filled on the next bar;
  Donchian/Bollinger references use the prior bar.
- **Credentials only via env.** Nothing is committed. See `.env.example`.
- **Paper-first.** Default `QUANTBOT_MODE=paper`. Going live is an explicit,
  documented switch (see the runbook).

> ⚠️ Trading crypto is risky. Backtested/forward results do not guarantee future
> performance. Use the paper mode and small size first. This is software, not
> financial advice.
