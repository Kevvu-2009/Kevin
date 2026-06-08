# Installation Guide

## 1. Prerequisites

- Python **3.11+** (3.12 recommended; the Docker image uses 3.12)
- PostgreSQL 14+ and Redis 6+ (only for storage / live mode — the demo and tests
  need neither)
- Docker + Docker Compose (optional, for the containerised stack)

## 2. Local install

```bash
git clone <your-fork> quantbot && cd quantbot
python -m venv .venv && source .venv/bin/activate

# Full stack:
pip install -r requirements.txt
pip install -e .

# OR core-only (analytics, backtest, validation, tests):
pip install numpy pandas scipy pytest
```

Verify:

```bash
PYTHONPATH=src pytest -q
PYTHONPATH=src python scripts/run_example_backtest.py
```

## 3. Configuration

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Purpose |
|----------|---------|
| `QUANTBOT_MODE` | `paper` (default) or `live` |
| `POSTGRES_*` / `DATABASE_URL` | database connection |
| `REDIS_*` / `REDIS_URL` | cache / state store |
| `DATA_EXCHANGE` | CCXT exchange id for OHLCV download (e.g. `binance`) |
| `RISK_PER_TRADE` | 0.005–0.01 (clamped) |
| `MAX_CONCURRENT_POSITIONS`, `DAILY_LOSS_LIMIT`, `WEEKLY_LOSS_LIMIT`, `KILL_SWITCH_DRAWDOWN` | risk limits |
| `BULLPEN_*` | Bullpen API credentials/URLs |
| `HYPERLIQUID_*` | Hyperliquid API-wallet key + main account address (live venue) |

**Never commit `.env`.** It is git-ignored.

## 4. Database schema

```bash
# Apply the schema to an existing Postgres
python -m quantbot.cli init-db --schema sql/schema.sql
# (Docker Compose applies it automatically on first boot.)
```

## 5. Download market data

```bash
python -m quantbot.cli download --symbol BTC/USDT --timeframe 4h --since 2022-01-01 --store
python -m quantbot.cli download --symbol BTC/USDT --timeframe 1h --out artifacts/BTC_1h.parquet
```

Supported timeframes: `5m, 15m, 1h, 4h, 1d`. Default universe (configurable):
BTC, ETH, SOL, BNB, XRP, ADA vs USDT.

## 6. Docker

```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d        # db + redis + dashboard
docker compose -f docker/docker-compose.yml --profile trade up -d engine # add the engine
```

Dashboard: <http://localhost:8000>.

## Troubleshooting

- **`ModuleNotFoundError: quantbot`** — run with `PYTHONPATH=src` or `pip install -e .`.
- **Optuna not installed** — the optimizer transparently falls back to seeded
  random search (`backend=random`).
- **`psycopg2` build errors** — install `libpq-dev` (Debian/Ubuntu) or use the
  Docker image.
- **No data for symbol** — confirm the symbol exists on `DATA_EXCHANGE`
  (e.g. `BTC/USDT`, not `BTCUSDT`).
