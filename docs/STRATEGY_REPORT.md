# Strategy Research Report

This report explains the design rationale, edge, failure modes, risk profile,
and deployment guidance for each strategy in QuantBot, plus the validation
philosophy that governs whether any of them is allowed to trade real capital.

The target operating point is a **1–14 day holding period** — slower than
intraday scalping, faster than position trading — on liquid crypto majors
(BTC, ETH, SOL) and selected liquid altcoins, primarily on the **4h** and **1d**
timeframes (with 1h available for faster swing variants).

---

## 0. Validation philosophy (read this first)

Historical profit is the *least* trustworthy signal in this business. The system
is therefore built to **reject** far more than it approves:

- **70/30 chronological IS/OOS.** Parameters are chosen on the first 70%; the
  last 30% is untouched until the final check. Time series are never shuffled.
- **Walk-forward.** Parameters fitted only on the past are applied to the
  immediately following unseen block, repeatedly. The stitched test curve is the
  honest performance proxy.
- **Monte Carlo.** Trade-return bootstrap (and block bootstrap of bar returns)
  produces a *distribution* of outcomes. We care about the 5th-percentile path,
  not the lucky one.
- **Parameter sensitivity.** We require a *plateau*, not a peak — small parameter
  changes must produce small, smooth metric changes. Sharp peaks are overfitting.
- **Composite optimization objective.** The optimizer maximises Sharpe + CAGR,
  penalises drawdown, **and penalises the IS↔OOS Sharpe gap**, so it prefers
  parameters that generalise.
- **Hard gates.** Deploy only if (OOS) Sharpe ≥ 1.2, profit factor ≥ 1.3,
  max drawdown ≤ 20%, OOS return > 0, ≥ 30 OOS trades, OOS/IS Sharpe ≥ 0.5.

> In the bundled offline demo on synthetic data, the optimized trend strategy is
> **correctly REJECTED** (too few OOS trades / Sharpe below 1.2). That is the
> system working as designed: the gate is the product, not a formality.

---

## 1. Trend Following (EMA 50/200 + ATR stop)

**Edge / why it works.** Crypto majors exhibit strong, persistent, fat-tailed
trends driven by adoption cycles, liquidity flows and reflexive momentum. A
fast/slow EMA stack keeps the book aligned with the dominant regime and lets
winners run; the ATR (Chandelier-style) stop converts the inevitable trend
breaks into small, bounded losses. The payoff distribution is positively skewed:
**low win rate, high average win** — a few large trends pay for many small
chops.

**Signals.** Long when EMA50 > EMA200 (entry on the crossover bar); exit on the
reverse cross or when price closes through a `close − atr_mult·ATR` trailing
stop that only ratchets upward.

**Failure modes.**
- *Whipsaw in ranges* — repeated small losses when EMA50/200 oscillate around
  each other. Mitigated by the trailing stop and by the regime-adaptive overlay.
- *Lag at turns* — gives back open profit before the reversal exit triggers.
- *Gap-through stops* in violent liquidations (slippage modelled, but tail gaps
  can exceed it).

**Risk characteristics.** Long stretches of small drawdown punctuated by sharp
recoveries; the equity curve is "staircase" shaped. Expect a sub-50% win rate
and reliance on a handful of outsized trades — psychologically hard, which is
exactly why it's automated.

**Best market conditions.** Sustained directional regimes, post-breakout bull or
bear legs, high trend strength (ADX elevated). Worst in tight, choppy ranges.

**Deployment recommendation.** Core allocation on 4h/1d majors. Pair with the
regime overlay to suppress range-bound chop. Conservative `atr_mult` (3–4).

---

## 2. Momentum Breakout (Donchian + ATR trailing + volume filter)

**Edge / why it works.** Ranges resolve into trends, and the resolution is
front-run by real participation. Buying a close above the prior N-bar high
captures the start of expansion; the **volume filter** (volume > k·MA) rejects
thin-book fake-outs that wick through the level without conviction. The ATR
trailing stop rides the move and exits on a close below a shorter Donchian floor.

**Signals.** Long when `close > prior-bar Donchian(channel) high` **and**
`volume > vol_mult · volume_MA`; exit on close below the prior `exit_channel`
low or the ATR trailing stop. Channel reference is the *prior* bar (no
same-bar look-ahead).

**Failure modes.**
- *False breakouts* — the dominant failure; partially filtered by volume, but
  no filter is perfect, so per-trade risk must be small.
- *Late entries* — buying the high means the stop distance can be wide; sizing
  is risk-based to keep dollar risk constant.
- *Illiquid alts* — volume spikes are easier to fake; restrict to liquid
  symbols.

**Risk characteristics.** Similar skew to trend following but more, shorter
trades and a higher turnover (more fee/slippage drag — which is why the
backtester charges both). Drawdowns come from clusters of failed breakouts in
choppy tape.

**Best market conditions.** Volatility *expansion* out of consolidation;
regime transitions; news/catalyst-driven repricings. Worst in low-volatility
drift where breakouts immediately mean-revert.

**Deployment recommendation.** Satellite allocation, shorter channels (20–30)
on 1h/4h for faster swings. Keep `vol_mult` ≥ 1.2 and per-trade risk at the low
end (0.5%). Monitor fee drag.

---

## 3. Mean Reversion (RSI + Bollinger Bands)

**Edge / why it works.** Inside range regimes, crypto overshoots on fear/greed
and snaps back to a local mean. Requiring **both** RSI oversold **and** a close
below the lower Bollinger band demands a genuine statistical extreme, not a mild
dip. Exits target reversion to the band middle (the mean) or RSI normalising —
this is a **high win rate, low average win** profile, the mirror image of trend
following.

**Signals.** Long when RSI < `rsi_buy` and `close < lower band`; exit when
`close ≥ mid band` or RSI > `rsi_sell`; hard ATR stop guards against a range
that becomes a downtrend.

**Failure modes.**
- *Trend regimes* — the killer: "oversold" gets more oversold; catching a
  falling knife produces large losses that erase many small wins. The ATR stop
  caps each, and the regime overlay disables MR when ADX is high.
- *Vol regime shift* — bands widen/narrow; fixed `bb_std` can mistime entries.
- *Negative skew* — by construction, so position size must be conservative and
  the stop strict.

**Risk characteristics.** Smooth equity in ranges with occasional sharp
drawdowns at regime changes. High win rate can lull operators into oversizing —
**don't**; the tail is the risk.

**Best market conditions.** Sideways, range-bound, low-trend, moderate
volatility. Explicitly *not* for strong trends.

**Deployment recommendation.** Only via the regime overlay (range regime) or on
assets/timeframes empirically range-bound. Strict ATR stop (≤ 2.5×), low risk
per trade, and a volatility ceiling to avoid sizing into chaos.

---

## 4. Regime-Adaptive (ADX/volatility switch: Trend ⇄ Mean Reversion)

**Edge / why it works.** No single edge works in all regimes — trend strategies
bleed in ranges and mean-reversion blows up in trends. This strategy classifies
the regime each bar (ADX for trend strength) and **delegates** to the
appropriate sub-strategy: Trend Following when ADX ≥ threshold, Mean Reversion
otherwise. A realized-volatility ceiling globally suppresses new entries when the
market is too chaotic to size safely. The result is a smoother blended equity
curve with shallower drawdowns than either component alone.

**Signals.** Per bar: pick the active regime's entry/exit/stop; additionally
exit on a regime flip; suppress entries when annualised realized vol exceeds
`vol_ceiling`.

**Failure modes.**
- *Whipsaw at the regime boundary* — ADX oscillating around the threshold causes
  strategy flip-flop; mitigated with hysteresis (raise threshold / add buffer)
  and the regime-flip exit.
- *Classifier lag* — ADX is smoothed and lags fast regime changes.
- *Compounded parameter surface* — more knobs ⇒ more overfitting risk, so the
  optimizer's IS↔OOS-gap penalty and the sensitivity gate matter most here.

**Risk characteristics.** The most balanced of the four: lower volatility and
drawdown, more consistent across regimes, at the cost of some upside capture
versus pure trend in a raging bull.

**Best market conditions.** The default choice when the forward regime is
unknown — i.e. most of the time. It is the recommended primary deployment
candidate **subject to passing the gates**.

**Deployment recommendation.** Primary allocation on 4h majors. Tune ADX
threshold for plateau robustness (18–32 range), keep the vol ceiling active, and
re-validate monthly.

---

## 5. Portfolio construction & risk

- **Position sizing.** Fixed-fractional by default: size so a stop-out costs
  ~`risk_per_trade` (0.5–1%, clamped) of equity, capped at 1× (no leverage).
  Volatility-adjusted sizing (ATR-based) is available for vol-targeting / risk
  parity across symbols.
- **Concurrency.** ≤ 5 simultaneous positions to bound correlated exposure
  (crypto is highly correlated — diversification is weaker than it looks).
- **Loss limits.** 3% daily / 8% weekly circuit breakers halt new entries; the
  20% peak-to-trough **kill switch** flattens and stops all trading until manual
  re-arm.
- **Costs.** Backtests charge taker fees (5 bps), slippage (5 bps), and impose
  next-bar execution latency. Turnover-heavy strategies are penalised honestly.

## 6. Expected performance envelope (qualitative)

| Strategy | Win rate | Skew | Turnover | Shines in | Suffers in |
|----------|----------|------|----------|-----------|-----------|
| Trend Following | Low (~35–45%) | Positive | Low | Strong trends | Choppy ranges |
| Momentum Breakout | Low–Mid | Positive | Mid–High | Vol expansion | Low-vol drift |
| Mean Reversion | High (~55–65%) | Negative | Mid | Ranges | Trends |
| Regime-Adaptive | Mixed | Mild positive | Mid | Unknown/mixed | Boundary whipsaw |

## 7. Deployment recommendation (summary)

1. **Run the full pipeline per symbol/timeframe**: optimize (IS) →
   walk-forward → Monte Carlo → sensitivity → gates.
2. **Deploy only gate-passers**, starting in **paper**, then live at minimum
   risk per trade.
3. **Prefer Regime-Adaptive** as the core when it passes; use Trend Following as
   the trend core and Breakout/Mean-Reversion as satellites in their regimes.
4. **Diversify across symbols and timeframes**, but respect the 5-position cap
   and remember crypto correlation spikes in stress.
5. **Re-validate on a cadence** and retire decaying strategies. The gates are
   re-applied to live OOS performance, not just to history.

*These are systematic rules and historical/forward studies, not financial
advice. Past performance does not guarantee future results.*
