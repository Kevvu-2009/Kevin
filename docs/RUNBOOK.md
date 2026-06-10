# Operations Runbook

Operational procedures for running QuantBot safely in paper and live modes.

---

## 1. Daily operations

### Start of day
1. Confirm services are healthy:
   ```bash
   docker compose -f docker/docker-compose.yml ps
   curl -s localhost:8000/health
   ```
2. Refresh data and re-validate any strategy near a gate boundary:
   ```bash
   python -m quantbot.cli download --symbol BTC/USDT --timeframe 4h --store
   python -m quantbot.cli validate --strategy <name> --data <file> --timeframe 4h
   ```
3. Check the dashboard: equity, drawdown, daily/weekly PnL, kill-switch state.

### During the session
- The engine processes each closed bar: signal → risk gate → sizing → order.
- Monitor `risk_events` and the structured logs (`category=risk|order|fill`).

### End of day
- Review trade blotter and equity curve.
- Snapshot/verify `engine_state` persistence (Redis key `quantbot:engine_state`).

---

## 2. Promoting a strategy to deployment

Promotion starts upstream, in edge discovery (see
[`RESEARCH_WORKFLOW.md`](RESEARCH_WORKFLOW.md)): the candidate's family must
have survived the discovery gauntlet on current data first.

```bash
python -m quantbot.cli discover --config config/discovery.yaml   # edge must survive here first
```

A strategy is deployable **only** after it ALSO clears every event-engine gate
(`quantbot.validation.gates`):

```bash
python -m quantbot.cli optimize --strategy <name> --data <file> --timeframe <tf> --trials 100 --out reports/opt.json
python -m quantbot.cli validate --strategy <name> --data <file> --timeframe <tf> --params '<best_params_json>'
```

`validate` exits non-zero if any gate fails. On pass, record the approved
params in `approved_strategies` (or your deployment config) and only then run
the engine with those params.

**Never** hand-tune parameters straight into live. Re-run the full validation
pipeline on fresh data.

---

## 3. Going live (paper → live, Hyperliquid)

> Default is `paper`. Treat the switch to `live` as a change-controlled action.

1. **Paper on live data** (mandatory stage — PaperBroker fills, real
   Hyperliquid market data, no credentials needed):
   ```bash
   cp config/live.example.yaml config/live.yaml      # mode: paper
   python -m quantbot.cli run-live --config config/live.yaml
   ```
   Run ≥ 4 weeks or ≥ 30 trades; compare realised turnover/fill quality to
   the backtest's cost assumptions.
2. Create a Hyperliquid **API wallet (agent)** at https://app.hyperliquid.xyz/API
   (testnet: https://app.hyperliquid-testnet.xyz/API). The agent key signs
   orders but **cannot withdraw**. Put in `.env`:
   `HYPERLIQUID_SECRET_KEY` (agent key) and `HYPERLIQUID_ACCOUNT_ADDRESS`
   (MAIN wallet address). Smoke-test:
   ```bash
   PYTHONPATH=src python scripts/hyperliquid_smoke_test.py
   ```
3. Rehearse on **testnet first**: `venue.testnet: true` + `mode: live` +
   `QUANTBOT_MODE=live`, with testnet faucet funds.
4. Mainnet: set `venue.testnet: false`, keep `leverage: 1`, the **minimum**
   `RISK_PER_TRADE` (0.5%) and a reduced position cap. The runner refuses to
   start live without a discovery validation report (`reports/research/summary.json`).
5. Watch the first several trades end-to-end (signal → order → fill →
   position → protective stop visible on-exchange).
6. Scale risk only after live fills match paper expectations (slippage/fees).

---

## 4. Incident response

### Kill switch tripped (drawdown ≥ 20% from peak)
- The engine **flattens** and **blocks new entries** automatically.
- Investigate: regime shift? data outage? venue issue? a single bad strategy?
- Re-arming is **manual only**:
  ```python
  engine.risk.reset_kill_switch()   # operator action; resets peak to current equity
  ```
- Do not re-arm without a root-cause and (ideally) re-validation.

### Daily / weekly loss limit hit
- New entries are blocked until the UTC day / ISO week rolls over.
- Existing positions continue to be managed (stops/exits still fire).

### Venue/API outage
- `OrderManager` retries with exponential backoff (1s, 2s, 4s, 8s) then marks
  the order `rejected` and logs `order_failed`.
- The downloader retries fetches similarly. If persistent, halt new entries and
  rely on resting stops; consider manual flatten if data is stale.

### Data quality failure
- `validate_ohlcv` marks a dataset `passed=False` on OHLC violations / NaNs.
- Do **not** trade or backtest on a failed dataset. Re-download; `clean_ohlcv`
  can remove duplicates/NaNs but anomalies should be reviewed.

### Crash / restart
- State is persisted to Redis (file fallback). On restart, load `EngineState`,
  reconcile open positions against the venue (`get_positions`) before resuming.

---

## 5. Monitoring & alerting

- Dashboard endpoints: `/` (UI), `/api/summary`, `/api/positions`, `/health`.
- Logs are structured JSON (`LOG_JSON=true`) — ship to your log stack and alert
  on `category=risk`, `event=order_failed`, `event=kill_switch`.
- Suggested alerts: drawdown > 12% (early warning), daily PnL < −2%, any
  rejected order, data gap detected.

---

## 6. Routine maintenance
- Re-optimize/re-validate strategies on a fixed cadence (e.g. monthly) and after
  major regime shifts; retire strategies whose live OOS performance decays.
- Back up Postgres (`pg_dump`) and the Redis AOF volume.
- Keep `requirements.txt` pinned; test upgrades in paper before live.
