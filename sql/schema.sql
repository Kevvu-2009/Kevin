-- ============================================================================
-- QuantBot PostgreSQL schema
-- ----------------------------------------------------------------------------
-- Conventions:
--   * all timestamps are UTC (timestamptz)
--   * OHLCV uses NUMERIC for price/qty to avoid float drift
--   * (exchange, symbol, timeframe, ts) is the natural key for candles
-- ============================================================================

CREATE TABLE IF NOT EXISTS instruments (
    id           BIGSERIAL PRIMARY KEY,
    exchange     TEXT        NOT NULL,
    symbol       TEXT        NOT NULL,          -- e.g. 'BTC/USDT'
    base         TEXT        NOT NULL,
    quote        TEXT        NOT NULL,
    active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (exchange, symbol)
);

-- ---------------------------------------------------------------------------
-- Historical OHLCV.  Partition-friendly; one row per candle.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ohlcv (
    exchange   TEXT        NOT NULL,
    symbol     TEXT        NOT NULL,
    timeframe  TEXT        NOT NULL,            -- 5m,15m,1h,4h,1d
    ts         TIMESTAMPTZ NOT NULL,            -- candle open time, UTC
    open       NUMERIC(38, 12) NOT NULL,
    high       NUMERIC(38, 12) NOT NULL,
    low        NUMERIC(38, 12) NOT NULL,
    close      NUMERIC(38, 12) NOT NULL,
    volume     NUMERIC(38, 12) NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (exchange, symbol, timeframe, ts)
);
CREATE INDEX IF NOT EXISTS idx_ohlcv_lookup ON ohlcv (symbol, timeframe, ts);

-- Records the outcome of each data-quality validation run.
CREATE TABLE IF NOT EXISTS data_quality_runs (
    id          BIGSERIAL PRIMARY KEY,
    exchange    TEXT        NOT NULL,
    symbol      TEXT        NOT NULL,
    timeframe   TEXT        NOT NULL,
    range_start TIMESTAMPTZ,
    range_end   TIMESTAMPTZ,
    n_candles   INTEGER     NOT NULL DEFAULT 0,
    n_gaps      INTEGER     NOT NULL DEFAULT 0,
    n_duplicates INTEGER    NOT NULL DEFAULT 0,
    n_anomalies INTEGER     NOT NULL DEFAULT 0,
    passed      BOOLEAN     NOT NULL,
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Strategy research / optimization bookkeeping
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS strategies (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,           -- registry key
    version     TEXT NOT NULL DEFAULT '1',
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS optimization_runs (
    id            BIGSERIAL PRIMARY KEY,
    strategy_name TEXT        NOT NULL,
    symbol        TEXT        NOT NULL,
    timeframe     TEXT        NOT NULL,
    objective     TEXT        NOT NULL,         -- e.g. 'sharpe'
    n_trials      INTEGER     NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS optimization_trials (
    id         BIGSERIAL PRIMARY KEY,
    run_id     BIGINT      NOT NULL REFERENCES optimization_runs(id) ON DELETE CASCADE,
    trial_no   INTEGER     NOT NULL,
    params     JSONB       NOT NULL,
    metrics    JSONB       NOT NULL,            -- full metric set
    objective_value DOUBLE PRECISION,
    is_oos_valid BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_trials_run ON optimization_trials (run_id, objective_value DESC);

-- Strategies that have passed all validation gates and may be deployed.
CREATE TABLE IF NOT EXISTS approved_strategies (
    id            BIGSERIAL PRIMARY KEY,
    strategy_name TEXT        NOT NULL,
    symbol        TEXT        NOT NULL,
    timeframe     TEXT        NOT NULL,
    params        JSONB       NOT NULL,
    is_metrics    JSONB       NOT NULL,
    oos_metrics   JSONB       NOT NULL,
    wf_metrics    JSONB,
    mc_metrics    JSONB,
    approved      BOOLEAN     NOT NULL DEFAULT FALSE,
    approved_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (strategy_name, symbol, timeframe)
);

-- ---------------------------------------------------------------------------
-- Live / paper trading state
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounts (
    id          BIGSERIAL PRIMARY KEY,
    venue       TEXT        NOT NULL,           -- bullpen | polymarket | paper
    mode        TEXT        NOT NULL,           -- paper | live
    equity      NUMERIC(38, 12) NOT NULL DEFAULT 0,
    peak_equity NUMERIC(38, 12) NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (venue, mode)
);

CREATE TABLE IF NOT EXISTS orders (
    id            BIGSERIAL PRIMARY KEY,
    client_id     TEXT        NOT NULL UNIQUE,    -- idempotency key
    venue         TEXT        NOT NULL,
    strategy_name TEXT,
    symbol        TEXT        NOT NULL,
    side          TEXT        NOT NULL,           -- buy | sell
    type          TEXT        NOT NULL,           -- market | limit
    qty           NUMERIC(38, 12) NOT NULL,
    limit_price   NUMERIC(38, 12),
    status        TEXT        NOT NULL,           -- new|submitted|filled|partial|cancelled|rejected
    venue_order_id TEXT,
    reason        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders (symbol, created_at DESC);

CREATE TABLE IF NOT EXISTS fills (
    id          BIGSERIAL PRIMARY KEY,
    order_id    BIGINT      REFERENCES orders(id) ON DELETE SET NULL,
    venue       TEXT        NOT NULL,
    symbol      TEXT        NOT NULL,
    side        TEXT        NOT NULL,
    qty         NUMERIC(38, 12) NOT NULL,
    price       NUMERIC(38, 12) NOT NULL,
    fee         NUMERIC(38, 12) NOT NULL DEFAULT 0,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS positions (
    id            BIGSERIAL PRIMARY KEY,
    venue         TEXT        NOT NULL,
    strategy_name TEXT,
    symbol        TEXT        NOT NULL,
    qty           NUMERIC(38, 12) NOT NULL,       -- signed; >0 long, <0 short
    avg_price     NUMERIC(38, 12) NOT NULL,
    stop_price    NUMERIC(38, 12),
    take_profit   NUMERIC(38, 12),
    opened_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at     TIMESTAMPTZ,
    realized_pnl  NUMERIC(38, 12) NOT NULL DEFAULT 0,
    UNIQUE (venue, symbol, strategy_name, opened_at)
);
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions (venue, symbol) WHERE closed_at IS NULL;

-- Equity snapshots powering the dashboard equity curve / drawdown.
CREATE TABLE IF NOT EXISTS equity_curve (
    id        BIGSERIAL PRIMARY KEY,
    venue     TEXT        NOT NULL,
    ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    equity    NUMERIC(38, 12) NOT NULL,
    drawdown  DOUBLE PRECISION NOT NULL DEFAULT 0,
    UNIQUE (venue, ts)
);

-- Risk / kill-switch events for audit.
CREATE TABLE IF NOT EXISTS risk_events (
    id         BIGSERIAL PRIMARY KEY,
    venue      TEXT,
    kind       TEXT        NOT NULL,             -- daily_limit|weekly_limit|kill_switch|max_positions
    severity   TEXT        NOT NULL DEFAULT 'warning',
    message    TEXT        NOT NULL,
    payload    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only structured event log (signals, decisions, errors).
CREATE TABLE IF NOT EXISTS event_log (
    id         BIGSERIAL PRIMARY KEY,
    level      TEXT        NOT NULL,
    category   TEXT        NOT NULL,             -- signal|order|fill|error|risk|strategy
    message    TEXT        NOT NULL,
    context    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_eventlog_cat ON event_log (category, created_at DESC);
