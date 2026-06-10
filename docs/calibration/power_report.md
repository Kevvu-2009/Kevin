# Calibration — POWER (planted trend) data

- Universe: TREND1, TREND2, TREND3, TREND4 @ 1h
- Candidates validated: 119 (962 parameter evaluations charged to DSR)
- Survivors: **2** | Runtime: 158.5s

> Total planned parameter evaluations (trial count for DSR): 962

## Selected edges (ranked by robustness)

### #1 — `mtf_trend` on TREND4

- **Family:** trend  |  **Timeframe:** 1h  |  **Robustness score:** 90.24/100
- **Best params (fit on IS only):** `{'htf_rule': '1D', 'htf_fast': 10, 'htf_slow': 30, 'ltf_fast': 20, 'ltf_slow': 50}`
- **OOS:** Sharpe 5.83 | CAGR +3828.4% | PF 9.27 | win 52% | maxDD -16.2% | 27 trades | exposure 68%
- **Walk-forward:** Sharpe 4.70, 100% windows positive
- **Monte Carlo (block bootstrap):** p05 maxDD -27.4%, P(loss) 0%
- **Parameter sensitivity:** grid retention 0.88 (100% of grid profitable)
- **Deflated Sharpe:** P(true SR>0) = 1.00 after 962 trials | **+1-bar-lag Sharpe:** 5.56
- **Worst regime:** trend_down_highvol (Sharpe 0.84, DD -12.8%)
- **Why it should work:** Trade lower-timeframe trend resumption only in the direction of the higher-timeframe trend: the HTF filter removes the counter-trend half of whipsaws.
- **Why it may persist:** Multi-horizon agreement proxies for alignment of slow and fast capital.
- **What kills it:** HTF turns are caught late; doubles the parameter surface.

### #2 — `ensemble_vote` on TREND3

- **Family:** hybrid  |  **Timeframe:** 1h  |  **Robustness score:** 79.28/100
- **Best params (fit on IS only):** `{'min_agree': 0.34}`
- **OOS:** Sharpe 4.01 | CAGR +673.7% | PF 3.96 | win 36% | maxDD -19.2% | 44 trades | exposure 83%
- **Walk-forward:** Sharpe 3.14, 50% windows positive
- **Monte Carlo (block bootstrap):** p05 maxDD -30.9%, P(loss) 0%
- **Parameter sensitivity:** grid retention 0.87 (100% of grid profitable)
- **Deflated Sharpe:** P(true SR>0) = 0.97 after 962 trials | **+1-bar-lag Sharpe:** 3.94
- **Worst regime:** trend_up_highvol (Sharpe -0.94, DD -12.9%)
- **Why it should work:** Equal-weight vote of four structurally different directional signals (EMA trend, Donchian breakout, TSMOM, squeeze breakout).  Positions scale with agreement; disagreement nets to flat.  Errors of the components are imperfectly correlated, so the vote's Sharpe exceeds the average component's.
- **Why it may persist:** As durable as the weakest surviving component; rebalanced by construction.
- **What kills it:** Components share trend exposure, so diversification is partial; all four can be wrong together at violent reversals.

## Full leaderboard

| signal | symbols | passed | robustness_score | oos_sharpe | oos_total_return | oos_max_dd | oos_profit_factor | oos_trades | wf_positive_windows | deflated_prob |
|---|---|---|---|---|---|---|---|---|---|---|
| mtf_trend | TREND4 | True | 90.24 | 5.83 | +351.8% | -16.2% | 9.27 | 27 | 1.00 | 1.00 |
| ensemble_vote | TREND3 | True | 79.28 | 4.01 | +131.8% | -19.2% | 3.96 | 44 | 0.50 | 0.97 |
| ensemble_vote | TREND4 | False | 88.14 | 3.31 | +104.7% | -23.1% | 2.66 | 50 | 1.00 | 0.94 |
| trend_pullback | TREND4 | False | 85.8 | 4.12 | +231.6% | -28.8% | 4.64 | 14 | 1.00 | 0.99 |
| weighted_composite | TREND4 | False | 84.89 | 3.26 | +140.8% | -35.6% | 2.90 | 56 | 1.00 | 0.98 |
| ema_cross | TREND4 | False | 83.12 | 3.37 | +160.7% | -36.8% | 3.59 | 14 | 1.00 | 0.95 |
| weighted_composite | TREND3 | False | 80.41 | 3.90 | +194.8% | -25.6% | 5.40 | 29 | 0.75 | 0.97 |
| ema_cross | TREND3 | False | 78.61 | 4.40 | +277.2% | -22.0% | 7.34 | 11 | 0.75 | 0.98 |
| mtf_trend | TREND2 | False | 78.59 | 3.03 | +112.5% | -27.2% | 2.60 | 27 | 0.75 | 0.88 |
| donchian_breakout | TREND4 | False | 78.51 | 3.29 | +110.7% | -26.1% | 2.10 | 47 | 0.75 | 0.80 |
| bollinger_reversion | TREND2 | False | 76.16 | 3.38 | +180.4% | -30.6% | 3.05 | 63 | 1.00 | 0.89 |
| mtf_trend | TREND3 | False | 76.04 | 4.17 | +200.7% | -26.8% | 3.99 | 29 | 0.75 | 0.95 |
| squeeze_breakout | TREND3 | False | 75.69 | 4.66 | +138.0% | -10.6% | 3.87 | 28 | 0.75 | 0.99 |
| tsmom | TREND4 | False | 73.93 | 4.79 | +305.0% | -45.0% | 8.98 | 32 | 0.75 | 0.88 |
| trend_pullback | TREND3 | False | 72.58 | 4.19 | +241.4% | -24.9% | 4.08 | 22 | 0.50 | 0.99 |
| xsec_momentum | TREND1+TREND2+TREND3+TREND4 | False | 71.51 | 2.12 | +39.7% | -19.7% | 1.69 | 88 | 1.00 | 0.42 |
| regime_gated_trend | TREND4 | False | 71.49 | 3.60 | +168.3% | -49.2% | 2.45 | 75 | 1.00 | 0.73 |
| sma_cross | TREND4 | False | 70.98 | 3.27 | +152.7% | -27.0% | 2.72 | 31 | 0.50 | 0.87 |
| relative_strength | TREND4 | False | 69.19 | 2.96 | +73.3% | -19.9% | 1.96 | 111 | 0.75 | 0.84 |
| tsmom | TREND2 | False | 68.64 | 3.49 | +181.2% | -26.6% | 13.14 | 18 | 0.75 | 0.66 |
| bollinger_reversion | TREND4 | False | 66.04 | 3.79 | +198.2% | -44.6% | 2.74 | 59 | 0.50 | 0.88 |
| break_of_structure | TREND4 | False | 65.92 | 2.82 | +117.9% | -41.0% | 1.90 | 45 | 0.75 | 0.53 |
| sma_cross | TREND3 | False | 64.43 | 3.26 | +158.2% | -35.6% | 3.04 | 25 | 0.50 | 0.77 |
| squeeze_breakout | TREND4 | False | 63.81 | 1.88 | +41.6% | -26.2% | 1.67 | 29 | 1.00 | 0.26 |
| regime_gated_reversion | TREND1 | False | 63.01 | 2.20 | +21.6% | -8.8% | 2.09 | 35 | 0.75 | 0.34 |
| vol_exhaustion | TREND3 | False | 61.48 | 2.30 | +26.2% | -12.7% | 2.65 | 12 | 0.50 | 0.62 |
| support_resistance | TREND1 | False | 61.31 | 3.00 | +137.8% | -50.2% | 1.75 | 101 | 0.50 | 0.92 |
| tsmom | TREND3 | False | 55.45 | 2.82 | +108.8% | -31.6% | 2.20 | 95 | 0.50 | 0.28 |
| squeeze_breakout | TREND2 | False | 54.82 | 1.56 | +36.1% | -26.1% | 1.54 | 32 | 1.00 | 0.28 |
| vol_regime_momentum | TREND4 | False | 54.02 | 2.24 | +57.2% | -41.2% | 1.44 | 176 | 0.50 | 0.74 |
| relative_value | TREND1+TREND2 | False | 52.79 | 1.59 | +20.8% | -21.7% | 5.28 | 14 | 0.75 | 0.34 |
| liquidity_sweep | TREND1 | False | 52.17 | 2.18 | +91.5% | -39.9% | 1.55 | 94 | 0.50 | 0.66 |
| orderflow_proxy | TREND2 | False | 51.04 | 1.92 | +54.4% | -27.4% | 1.50 | 69 | 0.50 | 0.21 |
| relative_strength | TREND3 | False | 50.66 | 1.96 | +47.8% | -28.7% | 1.90 | 76 | 0.50 | 0.35 |
| breakout_volume | TREND4 | False | 49.34 | 0.65 | +2.1% | -3.7% | inf | 1 | 0.50 | 0.34 |
| ensemble_vote | TREND2 | False | 48.0 | 0.58 | +7.1% | -28.2% | 1.23 | 53 | 0.75 | 0.50 |
| regime_gated_trend | TREND3 | False | 47.2 | 2.20 | +70.5% | -32.9% | 1.63 | 113 | 0.50 | 0.34 |
| trend_acceleration | TREND2 | False | 44.68 | 1.18 | +15.9% | -22.0% | 1.37 | 110 | 0.75 | 0.37 |
| sma_cross | TREND2 | False | 43.27 | 1.15 | +29.0% | -39.2% | 1.35 | 40 | 0.50 | 0.41 |
| vol_exhaustion | TREND1 | False | 43.24 | 1.45 | +11.6% | -11.6% | 2.54 | 6 | 0.25 | 0.27 |
| vol_expansion | TREND2 | False | 43.12 | 0.94 | +1.7% | -2.6% | 1.94 | 5 | 0.50 | 0.28 |
| ema_cross | TREND2 | False | 42.43 | 0.91 | +18.4% | -41.9% | 1.30 | 39 | 0.50 | 0.49 |
| breakout_volume | TREND3 | False | 41.53 | 0.73 | +9.6% | -28.0% | 1.33 | 27 | 0.50 | 0.31 |
| regime_gated_trend | TREND2 | False | 39.98 | 0.61 | +7.0% | -42.6% | 1.18 | 109 | 0.75 | 0.35 |
| regime_switch | TREND3 | False | 39.87 | 1.63 | +42.6% | -38.8% | 1.37 | 146 | 0.50 | 0.38 |
| donchian_breakout | TREND3 | False | 39.54 | 1.31 | +32.9% | -40.6% | 1.70 | 19 | 0.25 | 0.37 |
| orderflow_proxy | TREND1 | False | 38.04 | 0.95 | +16.5% | -29.8% | 1.38 | 36 | 0.75 | 0.20 |
| coint_pair | TREND1+TREND2 | False | 34.49 | 0.89 | +12.4% | -21.9% | 1.35 | 108 | 0.50 | 0.30 |
| donchian_breakout | TREND2 | False | 34.46 | 0.90 | +18.0% | -31.2% | 1.33 | 29 | 0.75 | 0.16 |
| zscore_reversion | TREND1 | False | 33.87 | 1.12 | +20.2% | -23.7% | 1.48 | 49 | 0.50 | 0.21 |
| trend_acceleration | TREND4 | False | 33.72 | 0.11 | -1.6% | -30.4% | 1.14 | 184 | 0.50 | 0.33 |
| trend_pullback | TREND2 | False | 32.84 | -0.43 | -25.6% | -55.0% | 0.94 | 29 | 0.75 | 0.29 |
| zscore_reversion | TREND3 | False | 32.71 | 1.30 | +19.8% | -17.5% | 1.45 | 65 | 0.25 | 0.37 |
| momentum_persistence | TREND2 | False | 28.76 | 0.48 | +4.5% | -23.8% | 1.25 | 93 | 0.50 | 0.06 |
| weighted_composite | TREND2 | False | 28.43 | -0.41 | -22.6% | -49.3% | 0.97 | 56 | 0.50 | 0.33 |
| vol_expansion | TREND3 | False | 26.48 | -0.06 | -0.6% | -4.8% | 1.03 | 13 | 0.50 | 0.09 |
| rsi_reversion | TREND1 | False | 23.92 | 0.26 | +1.4% | -16.2% | 1.24 | 7 | 0.50 | 0.06 |
| regime_switch | TREND4 | False | 23.71 | 0.29 | -2.1% | -53.9% | 1.11 | 194 | 0.50 | 0.28 |
| vol_exhaustion | TREND2 | False | 22.22 | -0.88 | -6.9% | -9.0% | 0.41 | 7 | 0.50 | 0.02 |
| break_of_structure | TREND3 | False | 21.77 | 0.46 | +1.9% | -41.6% | 1.22 | 45 | 0.50 | 0.08 |
| trend_pullback | TREND1 | False | 21.74 | -0.77 | -37.9% | -69.0% | 0.66 | 32 | 0.25 | 0.25 |
| break_of_structure | TREND2 | False | 21.62 | -0.05 | -14.7% | -52.8% | 1.01 | 79 | 0.50 | 0.11 |
| momentum_persistence | TREND4 | False | 21.51 | -0.65 | -5.4% | -16.0% | 0.92 | 38 | 0.25 | 0.01 |
| mtf_trend | TREND1 | False | 18.88 | -0.85 | -28.8% | -54.4% | 0.78 | 41 | 0.25 | 0.13 |
| regime_gated_reversion | TREND2 | False | 18.83 | -1.90 | -7.1% | -7.1% | 0.47 | 13 | 0.25 | 0.00 |
| atr_breakout | TREND4 | False | 18.63 | 0.00 | -8.5% | -43.2% | 1.10 | 58 | 0.50 | 0.06 |
| regime_switch | TREND1 | False | 18.52 | 0.02 | -10.4% | -48.0% | 1.02 | 239 | 0.25 | 0.09 |
| weighted_composite | TREND1 | False | 18.4 | -1.75 | -52.2% | -71.9% | 0.52 | 79 | 0.25 | 0.04 |
| momentum_persistence | TREND3 | False | 17.75 | -0.04 | -1.6% | -15.5% | 1.14 | 61 | 0.25 | 0.09 |
| coint_pair | TREND1+TREND3 | False | 16.89 | -0.42 | -11.2% | -28.5% | 0.91 | 86 | 0.50 | 0.05 |
| ema_cross | TREND1 | False | 16.88 | -1.52 | -53.6% | -76.1% | 0.48 | 25 | 0.25 | 0.01 |
| vol_expansion | TREND1 | False | 15.61 | -0.88 | -3.5% | -6.4% | 0.44 | 8 | 0.00 | 0.04 |
| support_resistance | TREND4 | False | 15.26 | -0.31 | -17.4% | -45.5% | 0.98 | 113 | 0.50 | 0.13 |
| vol_exhaustion | TREND4 | False | 15.25 | -0.63 | -7.0% | -19.9% | 0.87 | 11 | 0.25 | 0.14 |
| breakout_volume | TREND2 | False | 14.91 | 0.23 | -0.8% | -38.7% | 1.09 | 45 | 0.50 | 0.02 |
| relative_strength | TREND2 | False | 14.79 | -0.27 | -11.9% | -39.3% | 0.98 | 81 | 0.50 | 0.15 |
| corr_breakdown | TREND1+TREND3 | False | 14.76 | -1.05 | -21.9% | -32.6% | 0.85 | 178 | 0.50 | 0.01 |
| volume_momentum | TREND2 | False | 13.95 | -1.30 | -32.0% | -41.5% | 1.00 | 455 | 0.50 | 0.06 |
| bollinger_reversion | TREND1 | False | 13.15 | -1.35 | -50.4% | -57.0% | 0.68 | 99 | 0.25 | 0.00 |
| rsi_reversion | TREND3 | False | 12.87 | -2.53 | -34.9% | -43.6% | 0.49 | 27 | 0.50 | 0.00 |
| trend_acceleration | TREND3 | False | 12.79 | -0.72 | -10.0% | -21.1% | 0.99 | 110 | 0.25 | 0.02 |
| momentum_persistence | TREND1 | False | 12.47 | -1.74 | -19.1% | -26.4% | 0.63 | 47 | 0.25 | 0.00 |
| ensemble_vote | TREND1 | False | 12.15 | -2.95 | -55.3% | -69.1% | 0.41 | 78 | 0.00 | 0.00 |
| corr_breakdown | TREND1+TREND2 | False | 11.65 | -1.05 | -14.9% | -26.2% | 0.69 | 38 | 0.25 | 0.01 |
| vol_expansion | TREND4 | False | 11.23 | -0.62 | -6.4% | -17.3% | 1.04 | 78 | 0.00 | 0.02 |
| rsi_reversion | TREND2 | False | 11.1 | -0.12 | -4.0% | -20.5% | 1.01 | 19 | 0.25 | 0.01 |
| tsmom | TREND1 | False | 10.9 | -1.68 | -51.3% | -69.1% | 0.60 | 157 | 0.00 | 0.01 |
| regime_gated_trend | TREND1 | False | 10.84 | -1.25 | -41.7% | -63.6% | 0.80 | 185 | 0.25 | 0.01 |
| squeeze_breakout | TREND1 | False | 10.81 | -1.08 | -23.7% | -39.2% | 0.53 | 16 | 0.25 | 0.01 |
| bollinger_reversion | TREND3 | False | 10.17 | -2.31 | -59.6% | -75.4% | 0.62 | 99 | 0.50 | 0.01 |
| volume_momentum | TREND4 | False | 9.89 | -1.25 | -29.7% | -46.1% | 1.01 | 448 | 0.25 | 0.04 |
| vol_regime_momentum | TREND3 | False | 9.62 | 0.05 | -4.6% | -31.2% | 1.09 | 167 | 0.25 | 0.00 |
| regime_gated_reversion | TREND4 | False | 9.31 | -3.58 | -35.3% | -42.7% | 0.55 | 66 | 0.25 | 0.00 |
| atr_breakout | TREND3 | False | 9.27 | -0.83 | -15.2% | -35.0% | 0.87 | 57 | 0.25 | 0.02 |
| regime_gated_reversion | TREND3 | False | 9.16 | -1.33 | -14.2% | -19.8% | 0.88 | 81 | 0.00 | 0.01 |
| atr_breakout | TREND1 | False | 8.93 | -0.54 | -13.7% | -34.1% | 0.94 | 63 | 0.25 | 0.01 |
| relative_strength | TREND1 | False | 8.45 | -2.83 | -50.7% | -67.4% | 0.60 | 123 | 0.25 | 0.00 |
| break_of_structure | TREND1 | False | 8.36 | -3.95 | -81.8% | -86.5% | 0.35 | 63 | 0.25 | 0.00 |
| orderflow_proxy | TREND4 | False | 8.34 | -0.52 | -13.6% | -33.7% | 0.95 | 35 | 0.25 | 0.02 |
| relative_value | TREND1+TREND3 | False | 8.01 | -5.11 | -71.3% | -72.3% | 0.08 | 10 | 0.25 | 0.00 |
| breakout_volume | TREND1 | False | 7.87 | -3.20 | -50.3% | -57.6% | 0.37 | 32 | 0.25 | 0.00 |
| rsi_reversion | TREND4 | False | 7.36 | -3.34 | -52.0% | -53.4% | 0.64 | 114 | 0.25 | 0.00 |
| support_resistance | TREND3 | False | 7.17 | -1.44 | -45.5% | -70.0% | 0.83 | 252 | 0.25 | 0.01 |
| zscore_reversion | TREND4 | False | 6.99 | -3.41 | -56.8% | -59.6% | 0.65 | 111 | 0.25 | 0.00 |
| trend_acceleration | TREND1 | False | 6.85 | -1.50 | -26.1% | -37.5% | 0.87 | 151 | 0.00 | 0.04 |
| liquidity_sweep | TREND3 | False | 6.84 | -2.24 | -58.5% | -65.3% | 0.70 | 160 | 0.25 | 0.00 |
| regime_switch | TREND2 | False | 6.75 | -2.60 | -59.8% | -66.2% | 0.73 | 153 | 0.25 | 0.01 |
| liquidity_sweep | TREND4 | False | 6.62 | -2.51 | -60.0% | -64.1% | 0.77 | 176 | 0.25 | 0.01 |
| vol_regime_momentum | TREND2 | False | 6.5 | -2.81 | -54.0% | -59.3% | 0.79 | 199 | 0.25 | 0.00 |
| atr_breakout | TREND2 | False | 5.84 | -2.23 | -49.6% | -64.3% | 0.60 | 50 | 0.00 | 0.00 |
| support_resistance | TREND2 | False | 5.28 | -2.32 | -60.9% | -62.0% | 0.78 | 217 | 0.25 | 0.01 |
| donchian_breakout | TREND1 | False | 4.37 | -3.17 | -67.2% | -79.0% | 0.31 | 24 | 0.00 | 0.00 |
| vol_regime_momentum | TREND1 | False | 3.88 | -1.48 | -39.4% | -57.0% | 0.84 | 205 | 0.00 | 0.00 |
| volume_momentum | TREND3 | False | 3.62 | -2.90 | -53.8% | -62.9% | 0.86 | 429 | 0.00 | 0.01 |
| orderflow_proxy | TREND3 | False | 3.1 | -1.45 | -34.6% | -45.0% | 0.78 | 62 | 0.00 | 0.00 |
| volume_momentum | TREND1 | False | 2.2 | -3.26 | -62.5% | -75.8% | 0.84 | 478 | 0.00 | 0.00 |
| sma_cross | TREND1 | False | 1.72 | -5.04 | -88.0% | -92.2% | 0.22 | 81 | 0.00 | 0.00 |
| zscore_reversion | TREND2 | False | 1.13 | -3.43 | -51.0% | -53.6% | 0.38 | 41 | 0.00 | 0.00 |
| liquidity_sweep | TREND2 | False | 0.01 | -3.09 | -70.6% | -77.2% | 0.69 | 177 | 0.00 | 0.00 |

## Rejected candidates — reasons

- `atr_breakout` [TREND1]: OOS return -13.7% ≤ 0; OOS Sharpe -0.54 < 1.0; OOS PF 0.94 < 1.15; OOS maxDD 34.1% > 25%; only 25% WF windows positive; MC p05 drawdown 60.2% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.22 — edge dies with delay
- `atr_breakout` [TREND2]: OOS return -49.6% ≤ 0; OOS Sharpe -2.23 < 1.0; OOS PF 0.60 < 1.15; OOS maxDD 64.3% > 25%; OOS/IS Sharpe -2.55 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 80.5% > 35%; deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.63 — edge dies with delay; worst regime DD 41.7% > 35%
- `atr_breakout` [TREND3]: OOS return -15.2% ≤ 0; OOS Sharpe -0.83 < 1.0; OOS PF 0.87 < 1.15; OOS maxDD 35.0% > 25%; OOS/IS Sharpe -13.83 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 49.8% > 35%; param retention -0.39 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.14 — edge dies with delay
- `atr_breakout` [TREND4]: OOS return -8.5% ≤ 0; OOS Sharpe 0.00 < 1.0; OOS PF 1.10 < 1.15; OOS maxDD 43.2% > 25%; OOS/IS Sharpe 0.01 < 0.4 (overfit); MC p05 drawdown 69.7% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.06 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 36.2% > 35%
- `bollinger_reversion` [TREND1]: OOS return -50.4% ≤ 0; OOS Sharpe -1.35 < 1.0; OOS PF 0.68 < 1.15; OOS maxDD 57.0% > 25%; OOS/IS Sharpe -0.59 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 82.7% > 35%; deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.67 — edge dies with delay; worst regime DD 36.6% > 35%
- `bollinger_reversion` [TREND2]: OOS maxDD 30.6% > 25%; MC p05 drawdown 52.3% > 35%
- `bollinger_reversion` [TREND3]: OOS return -59.6% ≤ 0; OOS Sharpe -2.31 < 1.0; OOS PF 0.62 < 1.15; OOS maxDD 75.4% > 25%; OOS/IS Sharpe -7.87 < 0.4 (overfit); MC p05 drawdown 85.4% > 35%; param retention -0.48 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.68 — edge dies with delay; worst regime DD 60.0% > 35%
- `bollinger_reversion` [TREND4]: OOS maxDD 44.6% > 25%; MC p05 drawdown 46.9% > 35%; worst regime DD 51.4% > 35%
- `break_of_structure` [TREND1]: OOS return -81.8% ≤ 0; OOS Sharpe -3.95 < 1.0; OOS PF 0.35 < 1.15; OOS maxDD 86.5% > 25%; OOS/IS Sharpe -4.64 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 94.8% > 35%; param retention 0.28 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -3.98 — edge dies with delay; worst regime DD 60.3% > 35%
- `break_of_structure` [TREND2]: OOS return -14.7% ≤ 0; OOS Sharpe -0.05 < 1.0; OOS PF 1.01 < 1.15; OOS maxDD 52.8% > 25%; OOS/IS Sharpe -0.06 < 0.4 (overfit); MC p05 drawdown 75.0% > 35%; deflated P(SR>0) 0.11 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.60 — edge dies with delay; worst regime DD 50.5% > 35%
- `break_of_structure` [TREND3]: OOS Sharpe 0.46 < 1.0; OOS maxDD 41.6% > 25%; OOS/IS Sharpe 0.28 < 0.4 (overfit); MC p05 drawdown 71.0% > 35%; param retention 0.04 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.08 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 43.1% > 35%
- `break_of_structure` [TREND4]: OOS maxDD 41.0% > 25%; MC p05 drawdown 53.5% > 35%; deflated P(SR>0) 0.53 < 0.8 (not distinguishable from luck over 962 trials)
- `breakout_volume` [TREND1]: OOS return -50.3% ≤ 0; OOS Sharpe -3.20 < 1.0; OOS PF 0.37 < 1.15; OOS maxDD 57.6% > 25%; OOS/IS Sharpe -13.14 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 72.2% > 35%; param retention -0.19 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.82 — edge dies with delay
- `breakout_volume` [TREND2]: OOS return -0.8% ≤ 0; OOS Sharpe 0.23 < 1.0; OOS PF 1.09 < 1.15; OOS maxDD 38.7% > 25%; OOS/IS Sharpe 0.24 < 0.4 (overfit); MC p05 drawdown 56.1% > 35%; param retention -0.21 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.16 — edge dies with delay
- `breakout_volume` [TREND3]: OOS Sharpe 0.73 < 1.0; OOS maxDD 28.0% > 25%; OOS/IS Sharpe 0.37 < 0.4 (overfit); MC p05 drawdown 41.5% > 35%; deflated P(SR>0) 0.31 < 0.8 (not distinguishable from luck over 962 trials)
- `breakout_volume` [TREND4]: OOS Sharpe 0.65 < 1.0; 1 OOS trades < 25; deflated P(SR>0) 0.34 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.09 — edge dies with delay
- `coint_pair` [TREND1+TREND2]: OOS Sharpe 0.89 < 1.0; MC p05 drawdown 39.4% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.30 < 0.8 (not distinguishable from luck over 962 trials)
- `coint_pair` [TREND1+TREND3]: OOS return -11.2% ≤ 0; OOS Sharpe -0.42 < 1.0; OOS PF 0.91 < 1.15; OOS maxDD 28.5% > 25%; OOS/IS Sharpe -0.41 < 0.4 (overfit); MC p05 drawdown 50.8% > 35%; param retention 0.07 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.05 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.19 — edge dies with delay
- `corr_breakdown` [TREND1+TREND2]: OOS return -14.9% ≤ 0; OOS Sharpe -1.05 < 1.0; OOS PF 0.69 < 1.15; OOS maxDD 26.2% > 25%; OOS/IS Sharpe -4.97 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 45.1% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.88 — edge dies with delay
- `corr_breakdown` [TREND1+TREND3]: OOS return -21.9% ≤ 0; OOS Sharpe -1.05 < 1.0; OOS PF 0.85 < 1.15; OOS maxDD 32.6% > 25%; MC p05 drawdown 54.8% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.55 — edge dies with delay
- `donchian_breakout` [TREND1]: OOS return -67.2% ≤ 0; OOS Sharpe -3.17 < 1.0; OOS PF 0.31 < 1.15; OOS maxDD 79.0% > 25%; 24 OOS trades < 25; OOS/IS Sharpe -2.47 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 88.2% > 35%; deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -3.03 — edge dies with delay; worst regime DD 55.7% > 35%
- `donchian_breakout` [TREND2]: OOS Sharpe 0.90 < 1.0; OOS maxDD 31.2% > 25%; MC p05 drawdown 62.5% > 35%; param retention 0.21 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.16 < 0.8 (not distinguishable from luck over 962 trials)
- `donchian_breakout` [TREND3]: OOS maxDD 40.6% > 25%; 19 OOS trades < 25; only 25% WF windows positive; MC p05 drawdown 60.3% > 35%; deflated P(SR>0) 0.37 < 0.8 (not distinguishable from luck over 962 trials)
- `donchian_breakout` [TREND4]: OOS maxDD 26.1% > 25%; MC p05 drawdown 39.7% > 35%; deflated P(SR>0) 0.80 < 0.8 (not distinguishable from luck over 962 trials)
- `ema_cross` [TREND1]: OOS return -53.6% ≤ 0; OOS Sharpe -1.52 < 1.0; OOS PF 0.48 < 1.15; OOS maxDD 76.1% > 25%; OOS/IS Sharpe -0.47 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 87.6% > 35%; deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.92 — edge dies with delay; worst regime DD 40.9% > 35%
- `ema_cross` [TREND2]: OOS Sharpe 0.91 < 1.0; OOS maxDD 41.9% > 25%; OOS/IS Sharpe 0.38 < 0.4 (overfit); MC p05 drawdown 69.1% > 35%; deflated P(SR>0) 0.49 < 0.8 (not distinguishable from luck over 962 trials)
- `ema_cross` [TREND3]: 11 OOS trades < 25; MC p05 drawdown 39.1% > 35%
- `ema_cross` [TREND4]: OOS maxDD 36.8% > 25%; 14 OOS trades < 25; MC p05 drawdown 48.3% > 35%
- `ensemble_vote` [TREND1]: OOS return -55.3% ≤ 0; OOS Sharpe -2.95 < 1.0; OOS PF 0.41 < 1.15; OOS maxDD 69.1% > 25%; OOS/IS Sharpe -2.07 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 80.0% > 35%; deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.84 — edge dies with delay
- `ensemble_vote` [TREND2]: OOS Sharpe 0.58 < 1.0; OOS maxDD 28.2% > 25%; MC p05 drawdown 52.1% > 35%; deflated P(SR>0) 0.50 < 0.8 (not distinguishable from luck over 962 trials)
- `ensemble_vote` [TREND4]: MC p05 drawdown 36.1% > 35%
- `liquidity_sweep` [TREND1]: OOS maxDD 39.9% > 25%; MC p05 drawdown 56.1% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.66 < 0.8 (not distinguishable from luck over 962 trials)
- `liquidity_sweep` [TREND2]: OOS return -70.6% ≤ 0; OOS Sharpe -3.09 < 1.0; OOS PF 0.69 < 1.15; OOS maxDD 77.2% > 25%; OOS/IS Sharpe -63.41 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 90.0% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.55 — edge dies with delay; worst regime DD 66.7% > 35%
- `liquidity_sweep` [TREND3]: OOS return -58.5% ≤ 0; OOS Sharpe -2.24 < 1.0; OOS PF 0.70 < 1.15; OOS maxDD 65.3% > 25%; OOS/IS Sharpe -3.92 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 84.6% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.43 — edge dies with delay; worst regime DD 38.5% > 35%
- `liquidity_sweep` [TREND4]: OOS return -60.0% ≤ 0; OOS Sharpe -2.51 < 1.0; OOS PF 0.77 < 1.15; OOS maxDD 64.1% > 25%; only 25% WF windows positive; MC p05 drawdown 85.4% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.08 — edge dies with delay; worst regime DD 40.4% > 35%
- `momentum_persistence` [TREND1]: OOS return -19.1% ≤ 0; OOS Sharpe -1.74 < 1.0; OOS PF 0.63 < 1.15; OOS maxDD 26.4% > 25%; OOS/IS Sharpe -17.02 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 41.3% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.35 — edge dies with delay
- `momentum_persistence` [TREND2]: OOS Sharpe 0.48 < 1.0; MC p05 drawdown 37.8% > 35%; param retention -0.73 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.06 < 0.8 (not distinguishable from luck over 962 trials)
- `momentum_persistence` [TREND3]: OOS return -1.6% ≤ 0; OOS Sharpe -0.04 < 1.0; OOS PF 1.14 < 1.15; OOS/IS Sharpe -0.08 < 0.4 (overfit); only 25% WF windows positive; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.09 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.66 — edge dies with delay
- `momentum_persistence` [TREND4]: OOS return -5.4% ≤ 0; OOS Sharpe -0.65 < 1.0; OOS PF 0.92 < 1.15; OOS/IS Sharpe -5.60 < 0.4 (overfit); only 25% WF windows positive; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials)
- `mtf_trend` [TREND1]: OOS return -28.8% ≤ 0; OOS Sharpe -0.85 < 1.0; OOS PF 0.78 < 1.15; OOS maxDD 54.4% > 25%; OOS/IS Sharpe -0.43 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 74.0% > 35%; deflated P(SR>0) 0.13 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.98 — edge dies with delay; worst regime DD 38.3% > 35%
- `mtf_trend` [TREND2]: OOS maxDD 27.2% > 25%; MC p05 drawdown 42.3% > 35%
- `mtf_trend` [TREND3]: OOS maxDD 26.8% > 25%; MC p05 drawdown 35.4% > 35%; param retention 0.28 < 0.3 (performance is a parameter spike)
- `orderflow_proxy` [TREND1]: OOS Sharpe 0.95 < 1.0; OOS maxDD 29.8% > 25%; MC p05 drawdown 46.4% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.20 < 0.8 (not distinguishable from luck over 962 trials)
- `orderflow_proxy` [TREND2]: OOS maxDD 27.4% > 25%; MC p05 drawdown 52.9% > 35%; deflated P(SR>0) 0.21 < 0.8 (not distinguishable from luck over 962 trials)
- `orderflow_proxy` [TREND3]: OOS return -34.6% ≤ 0; OOS Sharpe -1.45 < 1.0; OOS PF 0.78 < 1.15; OOS maxDD 45.0% > 25%; OOS/IS Sharpe -3.26 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 71.4% > 35%; param retention -0.16 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.21 — edge dies with delay
- `orderflow_proxy` [TREND4]: OOS return -13.6% ≤ 0; OOS Sharpe -0.52 < 1.0; OOS PF 0.95 < 1.15; OOS maxDD 33.7% > 25%; OOS/IS Sharpe -0.30 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 59.7% > 35%; param retention -0.23 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.23 — edge dies with delay
- `regime_gated_reversion` [TREND1]: param retention -0.52 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.34 < 0.8 (not distinguishable from luck over 962 trials)
- `regime_gated_reversion` [TREND2]: OOS return -7.1% ≤ 0; OOS Sharpe -1.90 < 1.0; OOS PF 0.47 < 1.15; 13 OOS trades < 25; OOS/IS Sharpe -5.89 < 0.4 (overfit); only 25% WF windows positive; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.81 — edge dies with delay
- `regime_gated_reversion` [TREND3]: OOS return -14.2% ≤ 0; OOS Sharpe -1.33 < 1.0; OOS PF 0.88 < 1.15; only 0% WF windows positive; MC p05 drawdown 37.7% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.74 — edge dies with delay
- `regime_gated_reversion` [TREND4]: OOS return -35.3% ≤ 0; OOS Sharpe -3.58 < 1.0; OOS PF 0.55 < 1.15; OOS maxDD 42.7% > 25%; only 25% WF windows positive; MC p05 drawdown 54.6% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.05 — edge dies with delay
- `regime_gated_trend` [TREND1]: OOS return -41.7% ≤ 0; OOS Sharpe -1.25 < 1.0; OOS PF 0.80 < 1.15; OOS maxDD 63.6% > 25%; OOS/IS Sharpe -0.53 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 82.3% > 35%; deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.19 — edge dies with delay; worst regime DD 40.4% > 35%
- `regime_gated_trend` [TREND2]: OOS Sharpe 0.61 < 1.0; OOS maxDD 42.6% > 25%; MC p05 drawdown 70.3% > 35%; deflated P(SR>0) 0.35 < 0.8 (not distinguishable from luck over 962 trials)
- `regime_gated_trend` [TREND3]: OOS maxDD 32.9% > 25%; MC p05 drawdown 54.2% > 35%; param retention 0.03 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.34 < 0.8 (not distinguishable from luck over 962 trials)
- `regime_gated_trend` [TREND4]: OOS maxDD 49.2% > 25%; MC p05 drawdown 44.1% > 35%; param retention 0.01 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.73 < 0.8 (not distinguishable from luck over 962 trials)
- `regime_switch` [TREND1]: OOS return -10.4% ≤ 0; OOS Sharpe 0.02 < 1.0; OOS PF 1.02 < 1.15; OOS maxDD 48.0% > 25%; OOS/IS Sharpe 0.01 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 70.2% > 35%; deflated P(SR>0) 0.09 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 41.9% > 35%
- `regime_switch` [TREND2]: OOS return -59.8% ≤ 0; OOS Sharpe -2.60 < 1.0; OOS PF 0.73 < 1.15; OOS maxDD 66.2% > 25%; OOS/IS Sharpe -7.56 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 85.8% > 35%; param retention -0.16 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.96 — edge dies with delay; worst regime DD 39.9% > 35%
- `regime_switch` [TREND3]: OOS maxDD 38.8% > 25%; MC p05 drawdown 54.4% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.38 < 0.8 (not distinguishable from luck over 962 trials)
- `regime_switch` [TREND4]: OOS return -2.1% ≤ 0; OOS Sharpe 0.29 < 1.0; OOS PF 1.11 < 1.15; OOS maxDD 53.9% > 25%; MC p05 drawdown 67.7% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.28 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 36.4% > 35%
- `relative_strength` [TREND1]: OOS return -50.7% ≤ 0; OOS Sharpe -2.83 < 1.0; OOS PF 0.60 < 1.15; OOS maxDD 67.4% > 25%; OOS/IS Sharpe -15.09 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 77.3% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.94 — edge dies with delay
- `relative_strength` [TREND2]: OOS return -11.9% ≤ 0; OOS Sharpe -0.27 < 1.0; OOS PF 0.98 < 1.15; OOS maxDD 39.3% > 25%; OOS/IS Sharpe -0.71 < 0.4 (overfit); MC p05 drawdown 62.3% > 35%; param retention -0.58 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.15 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.66 — edge dies with delay
- `relative_strength` [TREND3]: OOS maxDD 28.7% > 25%; MC p05 drawdown 40.9% > 35%; param retention 0.07 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.35 < 0.8 (not distinguishable from luck over 962 trials)
- `relative_strength` [TREND4]: param retention -1.00 < 0.3 (performance is a parameter spike)
- `relative_value` [TREND1+TREND2]: 14 OOS trades < 25; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.34 < 0.8 (not distinguishable from luck over 962 trials)
- `relative_value` [TREND1+TREND3]: OOS return -71.3% ≤ 0; OOS Sharpe -5.11 < 1.0; OOS PF 0.08 < 1.15; OOS maxDD 72.3% > 25%; 10 OOS trades < 25; OOS/IS Sharpe -22.72 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 83.9% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -5.11 — edge dies with delay
- `rsi_reversion` [TREND1]: OOS Sharpe 0.26 < 1.0; 7 OOS trades < 25; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.06 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.07 — edge dies with delay
- `rsi_reversion` [TREND2]: OOS return -4.0% ≤ 0; OOS Sharpe -0.12 < 1.0; OOS PF 1.01 < 1.15; 19 OOS trades < 25; OOS/IS Sharpe -0.16 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 44.0% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.24 — edge dies with delay
- `rsi_reversion` [TREND3]: OOS return -34.9% ≤ 0; OOS Sharpe -2.53 < 1.0; OOS PF 0.49 < 1.15; OOS maxDD 43.6% > 25%; OOS/IS Sharpe -1.81 < 0.4 (overfit); MC p05 drawdown 60.6% > 35%; param retention -0.08 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -3.07 — edge dies with delay
- `rsi_reversion` [TREND4]: OOS return -52.0% ≤ 0; OOS Sharpe -3.34 < 1.0; OOS PF 0.64 < 1.15; OOS maxDD 53.4% > 25%; only 25% WF windows positive; MC p05 drawdown 74.1% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.97 — edge dies with delay; worst regime DD 35.3% > 35%
- `sma_cross` [TREND1]: OOS return -88.0% ≤ 0; OOS Sharpe -5.04 < 1.0; OOS PF 0.22 < 1.15; OOS maxDD 92.2% > 25%; OOS/IS Sharpe -3.57 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 96.4% > 35%; param retention 0.14 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -3.90 — edge dies with delay; worst regime DD 58.8% > 35%
- `sma_cross` [TREND2]: OOS maxDD 39.2% > 25%; MC p05 drawdown 67.1% > 35%; deflated P(SR>0) 0.41 < 0.8 (not distinguishable from luck over 962 trials)
- `sma_cross` [TREND3]: OOS maxDD 35.6% > 25%; MC p05 drawdown 49.5% > 35%; deflated P(SR>0) 0.77 < 0.8 (not distinguishable from luck over 962 trials)
- `sma_cross` [TREND4]: OOS maxDD 27.0% > 25%; MC p05 drawdown 48.3% > 35%
- `squeeze_breakout` [TREND1]: OOS return -23.7% ≤ 0; OOS Sharpe -1.08 < 1.0; OOS PF 0.53 < 1.15; OOS maxDD 39.2% > 25%; 16 OOS trades < 25; OOS/IS Sharpe -0.92 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 58.3% > 35%; param retention 0.11 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.10 — edge dies with delay
- `squeeze_breakout` [TREND2]: OOS maxDD 26.1% > 25%; MC p05 drawdown 46.0% > 35%; deflated P(SR>0) 0.28 < 0.8 (not distinguishable from luck over 962 trials)
- `squeeze_breakout` [TREND3]: param retention -0.18 < 0.3 (performance is a parameter spike)
- `squeeze_breakout` [TREND4]: OOS maxDD 26.2% > 25%; MC p05 drawdown 45.8% > 35%; deflated P(SR>0) 0.26 < 0.8 (not distinguishable from luck over 962 trials)
- `support_resistance` [TREND1]: OOS maxDD 50.2% > 25%; MC p05 drawdown 48.0% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike)
- `support_resistance` [TREND2]: OOS return -60.9% ≤ 0; OOS Sharpe -2.32 < 1.0; OOS PF 0.78 < 1.15; OOS maxDD 62.0% > 25%; only 25% WF windows positive; MC p05 drawdown 86.9% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.25 — edge dies with delay; worst regime DD 49.3% > 35%
- `support_resistance` [TREND3]: OOS return -45.5% ≤ 0; OOS Sharpe -1.44 < 1.0; OOS PF 0.83 < 1.15; OOS maxDD 70.0% > 25%; only 25% WF windows positive; MC p05 drawdown 83.4% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.22 — edge dies with delay; worst regime DD 37.5% > 35%
- `support_resistance` [TREND4]: OOS return -17.4% ≤ 0; OOS Sharpe -0.31 < 1.0; OOS PF 0.98 < 1.15; OOS maxDD 45.5% > 25%; MC p05 drawdown 71.5% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.13 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.48 — edge dies with delay
- `trend_acceleration` [TREND1]: OOS return -26.1% ≤ 0; OOS Sharpe -1.50 < 1.0; OOS PF 0.87 < 1.15; OOS maxDD 37.5% > 25%; OOS/IS Sharpe -2.29 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 56.7% > 35%; param retention 0.09 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.04 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.73 — edge dies with delay
- `trend_acceleration` [TREND2]: MC p05 drawdown 37.0% > 35%; param retention -0.11 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.37 < 0.8 (not distinguishable from luck over 962 trials)
- `trend_acceleration` [TREND3]: OOS return -10.0% ≤ 0; OOS Sharpe -0.72 < 1.0; OOS PF 0.99 < 1.15; only 25% WF windows positive; MC p05 drawdown 37.0% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.73 — edge dies with delay
- `trend_acceleration` [TREND4]: OOS return -1.6% ≤ 0; OOS Sharpe 0.11 < 1.0; OOS PF 1.14 < 1.15; OOS maxDD 30.4% > 25%; OOS/IS Sharpe 0.12 < 0.4 (overfit); MC p05 drawdown 46.1% > 35%; deflated P(SR>0) 0.33 < 0.8 (not distinguishable from luck over 962 trials)
- `trend_pullback` [TREND1]: OOS return -37.9% ≤ 0; OOS Sharpe -0.77 < 1.0; OOS PF 0.66 < 1.15; OOS maxDD 69.0% > 25%; OOS/IS Sharpe -0.30 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 83.4% > 35%; deflated P(SR>0) 0.25 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.26 — edge dies with delay; worst regime DD 38.9% > 35%
- `trend_pullback` [TREND2]: OOS return -25.6% ≤ 0; OOS Sharpe -0.43 < 1.0; OOS PF 0.94 < 1.15; OOS maxDD 55.0% > 25%; OOS/IS Sharpe -0.17 < 0.4 (overfit); MC p05 drawdown 79.9% > 35%; deflated P(SR>0) 0.29 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.28 — edge dies with delay; worst regime DD 39.5% > 35%
- `trend_pullback` [TREND3]: 22 OOS trades < 25; MC p05 drawdown 40.2% > 35%
- `trend_pullback` [TREND4]: OOS maxDD 28.8% > 25%; 14 OOS trades < 25; MC p05 drawdown 44.0% > 35%
- `tsmom` [TREND1]: OOS return -51.3% ≤ 0; OOS Sharpe -1.68 < 1.0; OOS PF 0.60 < 1.15; OOS maxDD 69.1% > 25%; OOS/IS Sharpe -0.82 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 85.6% > 35%; deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.60 — edge dies with delay; worst regime DD 40.4% > 35%
- `tsmom` [TREND2]: OOS maxDD 26.6% > 25%; 18 OOS trades < 25; MC p05 drawdown 51.6% > 35%; deflated P(SR>0) 0.66 < 0.8 (not distinguishable from luck over 962 trials)
- `tsmom` [TREND3]: OOS maxDD 31.6% > 25%; MC p05 drawdown 51.1% > 35%; deflated P(SR>0) 0.28 < 0.8 (not distinguishable from luck over 962 trials)
- `tsmom` [TREND4]: OOS maxDD 45.0% > 25%; MC p05 drawdown 41.3% > 35%
- `vol_exhaustion` [TREND1]: 6 OOS trades < 25; only 25% WF windows positive; param retention -0.85 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.27 < 0.8 (not distinguishable from luck over 962 trials)
- `vol_exhaustion` [TREND2]: OOS return -6.9% ≤ 0; OOS Sharpe -0.88 < 1.0; OOS PF 0.41 < 1.15; 7 OOS trades < 25; OOS/IS Sharpe -1.74 < 0.4 (overfit); param retention -0.97 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.37 — edge dies with delay
- `vol_exhaustion` [TREND3]: 12 OOS trades < 25; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.62 < 0.8 (not distinguishable from luck over 962 trials)
- `vol_exhaustion` [TREND4]: OOS return -7.0% ≤ 0; OOS Sharpe -0.63 < 1.0; OOS PF 0.87 < 1.15; 11 OOS trades < 25; only 25% WF windows positive; MC p05 drawdown 37.5% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.14 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.25 — edge dies with delay
- `vol_expansion` [TREND1]: OOS return -3.5% ≤ 0; OOS Sharpe -0.88 < 1.0; OOS PF 0.44 < 1.15; 8 OOS trades < 25; OOS/IS Sharpe -1.31 < 0.4 (overfit); only 0% WF windows positive; param retention -0.31 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.04 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.60 — edge dies with delay
- `vol_expansion` [TREND2]: OOS Sharpe 0.94 < 1.0; 5 OOS trades < 25; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.28 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.75 — edge dies with delay
- `vol_expansion` [TREND3]: OOS return -0.6% ≤ 0; OOS Sharpe -0.06 < 1.0; OOS PF 1.03 < 1.15; 13 OOS trades < 25; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.09 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.62 — edge dies with delay
- `vol_expansion` [TREND4]: OOS return -6.4% ≤ 0; OOS Sharpe -0.62 < 1.0; OOS PF 1.04 < 1.15; OOS/IS Sharpe -0.94 < 0.4 (overfit); only 0% WF windows positive; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.06 — edge dies with delay
- `vol_regime_momentum` [TREND1]: OOS return -39.4% ≤ 0; OOS Sharpe -1.48 < 1.0; OOS PF 0.84 < 1.15; OOS maxDD 57.0% > 25%; OOS/IS Sharpe -0.88 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 72.7% > 35%; param retention 0.06 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.08 — edge dies with delay
- `vol_regime_momentum` [TREND2]: OOS return -54.0% ≤ 0; OOS Sharpe -2.81 < 1.0; OOS PF 0.79 < 1.15; OOS maxDD 59.3% > 25%; OOS/IS Sharpe -3.81 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 80.1% > 35%; param retention -0.35 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.52 — edge dies with delay; worst regime DD 40.9% > 35%
- `vol_regime_momentum` [TREND3]: OOS return -4.6% ≤ 0; OOS Sharpe 0.05 < 1.0; OOS PF 1.09 < 1.15; OOS maxDD 31.2% > 25%; OOS/IS Sharpe 0.02 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 54.8% > 35%; param retention -0.24 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.03 — edge dies with delay
- `vol_regime_momentum` [TREND4]: OOS maxDD 41.2% > 25%; MC p05 drawdown 39.0% > 35%; param retention 0.01 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.74 < 0.8 (not distinguishable from luck over 962 trials)
- `volume_momentum` [TREND1]: OOS return -62.5% ≤ 0; OOS Sharpe -3.26 < 1.0; OOS PF 0.84 < 1.15; OOS maxDD 75.8% > 25%; only 0% WF windows positive; MC p05 drawdown 84.4% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.79 — edge dies with delay; worst regime DD 36.2% > 35%
- `volume_momentum` [TREND2]: OOS return -32.0% ≤ 0; OOS Sharpe -1.30 < 1.0; OOS PF 1.00 < 1.15; OOS maxDD 41.5% > 25%; MC p05 drawdown 69.5% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.06 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.14 — edge dies with delay
- `volume_momentum` [TREND3]: OOS return -53.8% ≤ 0; OOS Sharpe -2.90 < 1.0; OOS PF 0.86 < 1.15; OOS maxDD 62.9% > 25%; only 0% WF windows positive; MC p05 drawdown 79.6% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.07 — edge dies with delay
- `volume_momentum` [TREND4]: OOS return -29.7% ≤ 0; OOS Sharpe -1.25 < 1.0; OOS PF 1.01 < 1.15; OOS maxDD 46.1% > 25%; OOS/IS Sharpe -15.73 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 66.8% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.04 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.37 — edge dies with delay
- `weighted_composite` [TREND1]: OOS return -52.2% ≤ 0; OOS Sharpe -1.75 < 1.0; OOS PF 0.52 < 1.15; OOS maxDD 71.9% > 25%; OOS/IS Sharpe -0.68 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 85.5% > 35%; deflated P(SR>0) 0.04 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.68 — edge dies with delay
- `weighted_composite` [TREND2]: OOS return -22.6% ≤ 0; OOS Sharpe -0.41 < 1.0; OOS PF 0.97 < 1.15; OOS maxDD 49.3% > 25%; OOS/IS Sharpe -0.28 < 0.4 (overfit); MC p05 drawdown 75.9% > 35%; deflated P(SR>0) 0.33 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.31 — edge dies with delay; worst regime DD 36.9% > 35%
- `weighted_composite` [TREND3]: OOS maxDD 25.6% > 25%; MC p05 drawdown 40.4% > 35%
- `weighted_composite` [TREND4]: OOS maxDD 35.6% > 25%; MC p05 drawdown 47.9% > 35%
- `xsec_momentum` [TREND1+TREND2+TREND3+TREND4]: deflated P(SR>0) 0.42 < 0.8 (not distinguishable from luck over 962 trials)
- `zscore_reversion` [TREND1]: MC p05 drawdown 46.8% > 35%; param retention -0.89 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.21 < 0.8 (not distinguishable from luck over 962 trials)
- `zscore_reversion` [TREND2]: OOS return -51.0% ≤ 0; OOS Sharpe -3.43 < 1.0; OOS PF 0.38 < 1.15; OOS maxDD 53.6% > 25%; only 0% WF windows positive; MC p05 drawdown 74.8% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -3.71 — edge dies with delay; worst regime DD 43.0% > 35%
- `zscore_reversion` [TREND3]: only 25% WF windows positive; MC p05 drawdown 36.3% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.37 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.33 — edge dies with delay
- `zscore_reversion` [TREND4]: OOS return -56.8% ≤ 0; OOS Sharpe -3.41 < 1.0; OOS PF 0.65 < 1.15; OOS maxDD 59.6% > 25%; only 25% WF windows positive; MC p05 drawdown 79.5% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -4.39 — edge dies with delay; worst regime DD 37.8% > 35%
