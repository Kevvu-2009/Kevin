# Research Workflow — Edge Discovery to Deployment

This document is the operating procedure for finding, validating, and
deploying an edge. The pipeline is built so that **the easy path is the
honest path**: every shortcut (testing on the future, cherry-picking
parameters, ignoring costs, multiple-testing) is structurally blocked.

---

## 0. Principles encoded in the tooling

| Risk | Structural control |
|------|--------------------|
| Look-ahead bias | Signals are *positions decided at bar close*; the engine fills at the **next bar's open**. Higher-timeframe features join on bar *completion* time. Swing/pivot levels appear only after their confirmation bars. |
| Data leakage (ML) | Labels are forward returns; training uses walk-forward refits with a label-horizon gap; cross-validation is purged + embargoed (`models/cv.py`). Warm-up bars are flat, never backfilled. |
| Overfitting | Tiny declared parameter grids (≤ ~30 combos); IS/OOS split + walk-forward refits; parameter-plateau gate (median grid Sharpe must retain ≥ 30% of best); OOS/IS Sharpe ratio gate. |
| Multiple testing | Every candidate's **deflated Sharpe ratio** is charged the *entire sweep's* trial count (Bailey & López de Prado 2014). Testing 200 ideas raises the bar for all of them. |
| Unrealistic execution | Fees + slippage + half-spread charged per unit turnover; next-open fills; a **+1-bar-lag stress** gate kills anything that needs perfect timing. |
| Survivorship of lucky paths | Block-bootstrap Monte Carlo: the 5th-percentile path's drawdown must stay acceptable. |
| Regime luck | OOS performance is broken down by 6 market regimes (trend up/down × high/low vol, range × vol); one catastrophic regime fails the candidate. |

---

## 1. Calibrate the harness (offline, once per change to validation logic)

```bash
python scripts/run_edge_discovery.py --calibrate
```

* **Null test** — martingale data (zero drift, GARCH vol): acceptance is a
  false positive. Requirement: ≤ 5% acceptance rate.
* **Power test** — synthetic data with planted trend regimes: the pipeline
  must select trend/momentum-family candidates. Requirement: ≥ 1 selection.

If either fails, fix the harness before trusting any real-data result.
Reports land in `reports/research_calibration/{null,power}/`.

## 2. Collect data

```bash
# Incremental: re-running only fetches new bars.
python -m quantbot.cli cache-data \
    --symbols "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT" \
    --timeframe 1h --exchange binance --since 2021-01-01
```

Use ≥ 2.5 years of 1h bars (≈ 22k+) so the OOS window spans multiple
regimes. Supported sources: `binance`, `bybit`, `kraken`, `coinbase` (ccxt)
and `hyperliquid` (native). Quality validation (gaps, duplicates, OHLC
sanity, anomalies) runs on every update.

## 3. Run discovery

```bash
cp config/discovery.example.yaml config/discovery.yaml   # edit universe/gates
python -m quantbot.cli discover --config config/discovery.yaml
```

What happens, per candidate (signal × symbol(s)):

1. Parameter selection on the **first 70%** (IS) over the signal's small grid.
2. Frozen-parameter evaluation on the **last 30%** (OOS) — touched once.
3. Walk-forward: 4 rolling re-fit/re-test windows.
4. Block-bootstrap Monte Carlo on OOS returns.
5. Parameter-plateau analysis over the IS grid.
6. Regime breakdown of OOS returns.
7. +1-bar execution-lag stress.
8. Deflated Sharpe vs the whole sweep's trial count.
9. **All gates must pass**; survivors ranked by the composite robustness
   score (consistency/plateau/tails/statistical-confidence ≈ 70% of weight,
   raw return ≈ 30%).

Outputs in `reports/research/`:

* `leaderboard.csv` — every candidate, every metric, pass/fail + reasons
* `report.md` / `report.html` — ranked dossiers: thesis, persistence
  argument, risks, all validation numbers
* `summary.json` — machine-readable selection

**If the report says NO ROBUST EDGE FOUND, that is the result.** Do not
lower the gates. More data, more symbols, or new signal families are the
only legitimate responses.

## 4. Re-verify survivors on the event-driven engine

The vector engine screens; the event engine verifies with full order
mechanics (ATR stops, latency, per-trade sizing):

```bash
python -m quantbot.cli validate --strategy <mapped-strategy> \
    --data data_cache/binance/BTC-USDT_1h.parquet --timeframe 1h
```

The deployable strategy registry (`quantbot.strategies`) mirrors the main
research families (trend, breakout, mean-reversion, regime-adaptive). A
research signal is deployable when its family's strategy passes the
event-engine gates too.

## 5. Paper trade

```bash
QUANTBOT_MODE=paper python -m quantbot.cli run --strategy <name> \
    --symbol BTC/USDT --data data_cache/binance/BTC-USDT_1h.parquet --timeframe 1h
python -m quantbot.cli dashboard   # http://localhost:8000
```

Run paper for ≥ 4 weeks or ≥ 30 trades, whichever is later. Compare the
realised fill quality and turnover to the backtest's cost assumptions; if
realised costs exceed modelled costs, re-run discovery with the true costs.

## 6. Go live (Hyperliquid)

Only after: calibration PASS → discovery selection → event-engine gates →
paper validation. See `docs/RUNBOOK.md` for the live checklist, leverage
configuration, kill-switch behaviour, and the emergency procedures.

## 7. Monitor for edge decay

Re-run discovery monthly with `data.refresh: true`. A previously selected
edge that drops below the gates gets retired — the leaderboard diff is the
decay monitor. Live Sharpe persistently below the walk-forward Sharpe by
more than ~40% is an early decay warning (see RUNBOOK §monitoring).
