# Research Findings — Current State of Edge Validation

**Date:** 2026-06-10 · **Status:** harness calibrated and verified; **no
real-market edge claim is made yet** (see §3).

This document is the single source of truth for what the research pipeline
has and has not established. It is written the way an internal IC memo would
be: claims are separated from priors, and the absence of evidence is stated
outright.

---

## 1. What was established: the discovery harness is trustworthy

Before believing anything a research pipeline says about markets, the
pipeline itself must pass two tests on data where the truth is known by
construction. Both were run end-to-end (full sweep: 119 candidates per run,
962 parameter evaluations charged to the deflated-Sharpe trial count;
~12,000 hourly bars per series; realistic costs of 4 bps fee + 3 bps
slippage + 1 bp half-spread per side, next-open fills).

### 1.1 Null test — false-positive control ✅ PASS

Four independent **martingale** series (zero drift, GARCH-clustered
volatility — realistic-looking but unmonetisable by construction).

> **Result: 0 of 119 candidates accepted (0.0% false-positive rate).**

This is the important part: by chance alone, individual candidates reached
OOS Sharpe as high as **3.15** and walk-forward consistency of 100% on this
random data. Every one was rejected — by the deflated-Sharpe gate
(insufficient probability the Sharpe is distinguishable from luck across 962
trials), the parameter-plateau gate, the Monte-Carlo tail gate, or the
trade-count floor. A pipeline without these gates would have "discovered"
a dozen edges in noise. Full evidence: [`calibration/null_report.md`](calibration/null_report.md).

### 1.2 Power test — sensitivity control ✅ PASS

Four regime-switching series with **planted trend structure** (alternating
drift/range segments — a known, real inefficiency by construction).

> **Result: 2 of 119 candidates accepted, both from the trend/hybrid
> families** — `mtf_trend` (robustness 90/100, OOS Sharpe 5.83, DSR 1.00,
> 88% parameter retention, +1-bar-lag Sharpe 5.56) and `ensemble_vote`
> (robustness 79/100, DSR 0.97).

The pipeline found exactly the family of edge that was planted, and nothing
else — mean-reversion, stat-arb, structure and volatility candidates on the
same data were all correctly rejected. Full evidence:
[`calibration/power_report.md`](calibration/power_report.md).

**Conclusion:** the gauntlet (IS/OOS → walk-forward → Monte Carlo →
parameter plateau → regime breakdown → lag stress → deflated Sharpe) has
both **specificity** (rejects luck) and **power** (finds real structure).
These two properties are what make a future "edge found" report meaningful.

## 2. What the signal library covers

34 candidates across 9 families, every one carrying an explicit economic
thesis, persistence argument and failure mode (quoted automatically in every
report): trend (6), momentum (5, incl. cross-sectional), mean-reversion (4),
volatility (4), market structure (4, causal swing/sweep/flow constructions),
regime-conditioned (3), statistical arbitrage (3, with Engle-Granger
pair pre-screening), machine learning (2, walk-forward-only by construction),
hybrid combinations (3).

## 3. What is NOT established: a validated real-market edge

**No candidate has yet been validated on real exchange data, because this
build environment has no network route to any exchange API** (Binance,
Bybit, Kraken, Coinbase and Hyperliquid all unreachable; verified at build
time). Synthetic-data results — including the power-test selections above —
say *nothing* about real markets; they validate the instrument, not the
specimen.

Therefore, as of this writing: **the system ships with zero deployable edge
claims, and live trading must remain disabled** (the live runner enforces
this: it refuses `mode: live` until a discovery report exists).

### Run the real-data discovery (one command each)

```bash
# 1. Data (≥ 2.5 years of 1h bars recommended; incremental on re-run)
python -m quantbot.cli cache-data \
    --symbols "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,ADA/USDT" \
    --timeframe 1h --exchange binance --since 2021-01-01

# 2. Full sweep + gauntlet + ranked report
cp config/discovery.example.yaml config/discovery.yaml
python -m quantbot.cli discover --config config/discovery.yaml
```

Read `reports/research/report.md`. Two outcomes are possible and both are
valid results:

* **Survivors listed** → proceed to event-engine re-verification and paper
  trading per [`RESEARCH_WORKFLOW.md`](RESEARCH_WORKFLOW.md) §4–5.
* **"NO ROBUST EDGE FOUND"** → that is the finding. Do not weaken gates.
  Legitimate next moves: longer history, more symbols, different timeframe,
  or new signal families — never threshold shopping.

## 4. Priors (literature + structure), explicitly NOT findings

For planning only — these are reasons to *prioritise compute*, not beliefs
to confirm:

* **Time-series momentum / trend** has the strongest cross-asset,
  century-scale evidence (Moskowitz-Ooi-Pedersen 2012; Hurst et al. 2017)
  and crypto's retail, reflexive flow is its natural habitat. Most likely
  family to survive the gauntlet on majors at 4h–1d horizons.
* **Mean reversion** at 1h-and-faster horizons is real but fee-fragile at
  taker costs; expect candidates to die on the cost/lag gates unless maker
  execution is modelled.
* **Cross-sectional momentum** needs a wider universe (≥ 8–10 liquid names)
  than the default config to overcome idiosyncratic blowup risk.
* **Cointegration stat-arb** on crypto majors is regime-fragile (one
  dominant factor; relationships break on narrative rotation). The
  correlation-breakdown stop is load-bearing; expect few survivors.
* **ML classifiers** add value mainly as *regime gates* on robust simple
  rules, not as standalone alpha; their honest (walk-forward-only)
  construction here means weak models show up as flat, not as fake winners.

## 5. Known modelling gaps (flagged, not hidden)

* **Perp funding is not modelled.** Strategies holding persistent one-sided
  perp exposure overstate returns by the average funding drag (historically
  ~±5–15 bps/day on majors in trending periods). Treat long-exposure-heavy
  survivors with an extra haircut until funding-aware backtests are added.
* Slippage is a constant-bps model; real breakout entries pay more than the
  average. The +1-bar-lag stress partially compensates.
* The trade-bootstrap assumes per-trade independence; the block bootstrap
  on bar returns is the binding tail check.

## 6. Reproduce everything in this document

```bash
PYTHONPATH=src python scripts/run_edge_discovery.py --calibrate
# verdict + reports/research_calibration/{null,power}/
PYTHONPATH=src pytest -q          # 200+ tests incl. causality & leakage suites
```
