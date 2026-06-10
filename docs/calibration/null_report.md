# Calibration — NULL (martingale) data

- Universe: NULL1, NULL2, NULL3, NULL4 @ 1h
- Candidates validated: 119 (962 parameter evaluations charged to DSR)
- Survivors: **0** | Runtime: 159.5s

> Total planned parameter evaluations (trial count for DSR): 962
> NO ROBUST EDGE FOUND: no candidate cleared every validation gate on this data. This is a valid (and common) outcome — do not lower the gates to force a deployment.

## No robust edge found

No candidate cleared every gate. The correct action is to widen the data (more history, more symbols), not the gates.

## Full leaderboard

| signal | symbols | passed | robustness_score | oos_sharpe | oos_total_return | oos_max_dd | oos_profit_factor | oos_trades | wf_positive_windows | deflated_prob |
|---|---|---|---|---|---|---|---|---|---|---|
| ensemble_vote | NULL4 | False | 76.38 | 2.07 | +46.5% | -21.2% | 1.97 | 53 | 0.75 | 0.87 |
| mtf_trend | NULL1 | False | 68.71 | 3.05 | +121.9% | -27.8% | 2.53 | 43 | 0.75 | 0.87 |
| tsmom | NULL2 | False | 68.57 | 2.21 | +87.9% | -34.5% | 2.09 | 92 | 1.00 | 0.60 |
| weighted_composite | NULL2 | False | 67.02 | 1.77 | +59.9% | -38.5% | 2.27 | 40 | 1.00 | 0.64 |
| ensemble_vote | NULL1 | False | 66.69 | 2.08 | +60.5% | -16.6% | 2.31 | 43 | 1.00 | 0.85 |
| squeeze_breakout | NULL4 | False | 66.69 | 2.13 | +56.8% | -32.6% | 1.97 | 27 | 0.75 | 0.75 |
| ema_cross | NULL1 | False | 66.43 | 3.15 | +177.9% | -30.3% | 7.84 | 9 | 0.75 | 0.82 |
| mtf_trend | NULL4 | False | 62.46 | 1.69 | +48.0% | -28.1% | 1.55 | 54 | 0.75 | 0.64 |
| orderflow_proxy | NULL2 | False | 61.64 | 1.98 | +54.2% | -26.3% | 1.52 | 99 | 0.75 | 0.67 |
| vol_regime_momentum | NULL4 | False | 60.88 | 2.49 | +66.7% | -17.0% | 1.61 | 112 | 1.00 | 0.23 |
| tsmom | NULL4 | False | 60.07 | 2.09 | +80.1% | -28.5% | 2.04 | 63 | 1.00 | 0.19 |
| trend_pullback | NULL4 | False | 59.1 | 1.17 | +30.9% | -35.2% | 1.51 | 25 | 1.00 | 0.55 |
| trend_pullback | NULL1 | False | 57.96 | 1.92 | +71.4% | -38.7% | 1.80 | 34 | 0.75 | 0.84 |
| vol_expansion | NULL2 | False | 56.26 | 1.51 | +17.2% | -13.1% | 1.70 | 43 | 0.75 | 0.54 |
| tsmom | NULL1 | False | 56.06 | 2.21 | +87.3% | -43.0% | 4.07 | 21 | 0.75 | 0.52 |
| momentum_persistence | NULL1 | False | 55.07 | 1.70 | +30.9% | -12.4% | 1.62 | 105 | 0.75 | 0.31 |
| break_of_structure | NULL4 | False | 54.15 | 1.70 | +60.3% | -34.9% | 1.40 | 65 | 0.50 | 0.51 |
| squeeze_breakout | NULL1 | False | 53.74 | 1.62 | +42.7% | -33.9% | 1.60 | 31 | 1.00 | 0.49 |
| regime_switch | NULL2 | False | 52.96 | 1.98 | +64.7% | -25.0% | 1.47 | 149 | 0.75 | 0.47 |
| vol_expansion | NULL1 | False | 52.89 | 2.21 | +22.7% | -14.5% | 1.85 | 23 | 0.50 | 0.19 |
| atr_breakout | NULL4 | False | 52.37 | 1.84 | +54.7% | -31.1% | 1.57 | 44 | 0.75 | 0.21 |
| orderflow_proxy | NULL1 | False | 51.23 | 2.00 | +58.2% | -32.7% | 1.59 | 53 | 0.75 | 0.35 |
| regime_gated_trend | NULL4 | False | 50.25 | 1.65 | +46.9% | -27.6% | 1.44 | 102 | 1.00 | 0.12 |
| mtf_trend | NULL2 | False | 49.88 | 1.25 | +30.2% | -37.0% | 1.47 | 48 | 0.50 | 0.59 |
| vol_exhaustion | NULL2 | False | 49.66 | 1.21 | +16.8% | -14.0% | 3.13 | 10 | 0.50 | 0.46 |
| vol_expansion | NULL4 | False | 49.25 | 1.83 | +35.8% | -26.5% | 1.43 | 120 | 0.75 | 0.53 |
| ema_cross | NULL4 | False | 49.13 | 1.13 | +28.9% | -33.5% | 1.51 | 27 | 0.75 | 0.47 |
| donchian_breakout | NULL2 | False | 48.72 | 0.91 | +16.8% | -27.5% | 1.40 | 27 | 0.75 | 0.46 |
| ema_cross | NULL2 | False | 47.66 | 1.09 | +26.8% | -41.9% | 1.43 | 50 | 0.75 | 0.41 |
| rsi_reversion | NULL4 | False | 46.65 | 0.99 | +8.7% | -12.9% | 2.21 | 8 | 0.75 | 0.14 |
| donchian_breakout | NULL1 | False | 45.35 | 1.08 | +24.5% | -27.1% | 1.72 | 19 | 0.75 | 0.51 |
| trend_acceleration | NULL1 | False | 45.08 | 1.58 | +32.0% | -27.8% | 1.41 | 169 | 0.50 | 0.56 |
| momentum_persistence | NULL4 | False | 44.78 | 1.16 | +8.9% | -5.9% | 1.80 | 35 | 0.50 | 0.30 |
| regime_switch | NULL1 | False | 41.86 | 0.70 | +10.4% | -30.7% | 1.14 | 174 | 1.00 | 0.49 |
| vol_regime_momentum | NULL2 | False | 41.78 | 1.42 | +37.8% | -30.4% | 1.37 | 136 | 0.75 | 0.25 |
| sma_cross | NULL2 | False | 41.38 | 0.89 | +17.7% | -41.6% | 1.36 | 36 | 0.50 | 0.41 |
| relative_value | NULL1+NULL3 | False | 41.36 | 1.16 | +17.6% | -20.3% | 1.36 | 62 | 0.75 | 0.14 |
| ensemble_vote | NULL2 | False | 40.57 | 0.37 | +2.4% | -25.2% | 1.15 | 46 | 0.75 | 0.32 |
| breakout_volume | NULL1 | False | 39.59 | 1.39 | +33.1% | -35.9% | 1.49 | 41 | 0.50 | 0.44 |
| trend_pullback | NULL2 | False | 39.16 | 0.13 | -12.1% | -62.5% | 1.19 | 19 | 0.75 | 0.29 |
| breakout_volume | NULL4 | False | 37.94 | 0.99 | +20.0% | -27.6% | 1.29 | 50 | 0.50 | 0.07 |
| weighted_composite | NULL4 | False | 36.44 | 0.50 | +2.7% | -39.1% | 1.16 | 45 | 0.75 | 0.23 |
| donchian_breakout | NULL4 | False | 35.07 | 1.18 | +23.7% | -24.6% | 1.46 | 34 | 0.50 | 0.19 |
| sma_cross | NULL1 | False | 34.86 | 0.92 | +19.1% | -40.0% | 1.26 | 69 | 0.75 | 0.39 |
| break_of_structure | NULL1 | False | 34.42 | 1.05 | +25.1% | -46.7% | 1.26 | 64 | 0.50 | 0.49 |
| support_resistance | NULL1 | False | 33.37 | 1.26 | +32.3% | -45.2% | 1.27 | 87 | 0.50 | 0.24 |
| zscore_reversion | NULL3 | False | 32.92 | 0.88 | +14.6% | -23.3% | 1.31 | 49 | 0.75 | 0.12 |
| weighted_composite | NULL1 | False | 31.43 | 0.36 | +2.2% | -22.8% | 1.13 | 78 | 0.75 | 0.59 |
| regime_gated_trend | NULL2 | False | 31.2 | 0.67 | +9.5% | -35.2% | 1.20 | 85 | 0.50 | 0.17 |
| momentum_persistence | NULL3 | False | 30.44 | 0.33 | +1.2% | -7.8% | 1.39 | 11 | 0.50 | 0.02 |
| sma_cross | NULL4 | False | 30.16 | 0.65 | +7.3% | -44.1% | 1.19 | 35 | 0.50 | 0.29 |
| support_resistance | NULL3 | False | 29.95 | 0.84 | +15.6% | -43.5% | 1.13 | 216 | 0.00 | 0.35 |
| vol_exhaustion | NULL3 | False | 29.53 | -1.09 | -4.8% | -11.7% | 0.07 | 2 | 0.75 | 0.09 |
| orderflow_proxy | NULL4 | False | 29.01 | 0.58 | +6.9% | -38.5% | 1.18 | 64 | 0.50 | 0.28 |
| support_resistance | NULL4 | False | 28.8 | 0.82 | +14.6% | -43.3% | 1.14 | 167 | 0.50 | 0.35 |
| corr_breakdown | NULL1+NULL3 | False | 28.78 | 0.65 | +7.3% | -17.5% | 1.22 | 46 | 0.25 | 0.30 |
| breakout_volume | NULL2 | False | 26.88 | -0.68 | -18.6% | -31.4% | 0.82 | 29 | 0.75 | 0.03 |
| coint_pair | NULL1+NULL3 | False | 26.64 | -0.49 | -12.9% | -30.0% | 0.99 | 196 | 0.50 | 0.21 |
| rsi_reversion | NULL3 | False | 26.12 | 0.18 | +0.6% | -13.6% | 1.14 | 9 | 0.50 | 0.01 |
| relative_strength | NULL1 | False | 25.19 | 0.83 | +14.2% | -28.3% | 1.33 | 113 | 0.50 | 0.13 |
| squeeze_breakout | NULL2 | False | 24.46 | -0.12 | -11.4% | -33.3% | 0.95 | 28 | 0.75 | 0.05 |
| momentum_persistence | NULL2 | False | 22.5 | -2.97 | -10.9% | -12.9% | 0.28 | 19 | 0.50 | 0.00 |
| vol_regime_momentum | NULL1 | False | 22.38 | 0.30 | +0.1% | -29.3% | 1.11 | 153 | 0.75 | 0.02 |
| regime_switch | NULL4 | False | 22.33 | -0.21 | -17.9% | -50.7% | 0.99 | 202 | 0.75 | 0.01 |
| rsi_reversion | NULL2 | False | 21.91 | 0.13 | +0.1% | -17.7% | 1.11 | 9 | 0.25 | 0.08 |
| mtf_trend | NULL3 | False | 21.24 | -1.47 | -39.2% | -51.0% | 0.49 | 32 | 0.50 | 0.05 |
| vol_exhaustion | NULL1 | False | 20.48 | -1.71 | -22.1% | -37.7% | 0.46 | 10 | 0.50 | 0.00 |
| liquidity_sweep | NULL1 | False | 20.38 | 0.22 | -5.8% | -44.8% | 1.07 | 89 | 0.50 | 0.03 |
| regime_gated_reversion | NULL3 | False | 20.05 | -1.25 | -11.1% | -18.6% | 0.73 | 31 | 0.50 | 0.01 |
| rsi_reversion | NULL1 | False | 20.03 | -0.14 | -4.0% | -18.4% | 0.89 | 10 | 0.25 | 0.04 |
| vol_regime_momentum | NULL3 | False | 19.91 | -1.49 | -32.8% | -39.3% | 0.83 | 154 | 0.75 | 0.03 |
| atr_breakout | NULL3 | False | 19.81 | -1.08 | -35.3% | -55.8% | 0.78 | 59 | 0.50 | 0.02 |
| regime_gated_reversion | NULL2 | False | 19.43 | -0.83 | -10.4% | -18.3% | 0.82 | 34 | 0.50 | 0.11 |
| vol_exhaustion | NULL4 | False | 18.77 | -0.96 | -11.9% | -13.0% | 0.58 | 7 | 0.25 | 0.01 |
| break_of_structure | NULL3 | False | 18.41 | -0.11 | -18.8% | -50.8% | 0.89 | 46 | 0.75 | 0.05 |
| break_of_structure | NULL2 | False | 18.31 | 0.31 | -5.7% | -56.7% | 1.08 | 46 | 0.50 | 0.17 |
| trend_pullback | NULL3 | False | 18.23 | -2.16 | -62.3% | -68.2% | 0.24 | 24 | 0.25 | 0.04 |
| sma_cross | NULL3 | False | 15.82 | -0.30 | -24.6% | -38.9% | 0.91 | 67 | 0.25 | 0.10 |
| volume_momentum | NULL4 | False | 15.58 | -0.42 | -18.9% | -43.4% | 1.07 | 466 | 0.50 | 0.19 |
| volume_momentum | NULL2 | False | 15.47 | -0.61 | -22.9% | -39.1% | 1.05 | 435 | 0.25 | 0.08 |
| regime_gated_reversion | NULL1 | False | 15.21 | -0.88 | -7.8% | -15.9% | 0.83 | 28 | 0.25 | 0.01 |
| regime_gated_trend | NULL1 | False | 15.18 | -1.90 | -43.1% | -53.7% | 0.72 | 120 | 0.75 | 0.01 |
| xsec_momentum | NULL1+NULL2+NULL3+NULL4 | False | 15.12 | -1.81 | -32.0% | -42.0% | 0.82 | 184 | 0.25 | 0.02 |
| relative_strength | NULL3 | False | 14.78 | -2.02 | -39.9% | -42.1% | 0.65 | 95 | 0.50 | 0.02 |
| ensemble_vote | NULL3 | False | 14.67 | -2.24 | -45.7% | -49.9% | 0.52 | 73 | 0.50 | 0.03 |
| breakout_volume | NULL3 | False | 14.5 | -0.79 | -15.7% | -29.0% | 0.69 | 17 | 0.50 | 0.03 |
| ema_cross | NULL3 | False | 13.24 | -1.31 | -48.2% | -51.0% | 0.44 | 21 | 0.00 | 0.07 |
| orderflow_proxy | NULL3 | False | 12.72 | -0.49 | -22.7% | -43.8% | 0.94 | 87 | 0.25 | 0.06 |
| weighted_composite | NULL3 | False | 12.66 | -1.96 | -54.2% | -62.2% | 0.50 | 59 | 0.50 | 0.00 |
| regime_gated_trend | NULL3 | False | 12.61 | -1.28 | -43.1% | -58.7% | 0.79 | 174 | 0.50 | 0.07 |
| trend_acceleration | NULL2 | False | 12.33 | -0.97 | -16.6% | -23.2% | 0.93 | 128 | 0.25 | 0.09 |
| tsmom | NULL3 | False | 12.16 | -2.20 | -60.3% | -72.1% | 0.52 | 133 | 0.50 | 0.00 |
| atr_breakout | NULL1 | False | 12.14 | -2.97 | -10.5% | -12.5% | 0.00 | 2 | 0.00 | 0.00 |
| relative_strength | NULL2 | False | 11.02 | -1.97 | -41.0% | -41.9% | 0.77 | 155 | 0.00 | 0.01 |
| coint_pair | NULL1+NULL4 | False | 10.02 | -2.47 | -34.9% | -36.1% | 0.73 | 176 | 0.25 | 0.00 |
| regime_gated_reversion | NULL4 | False | 9.86 | -3.59 | -35.1% | -36.8% | 0.45 | 55 | 0.25 | 0.00 |
| corr_breakdown | NULL1+NULL4 | False | 9.53 | -2.17 | -28.4% | -36.0% | 0.66 | 52 | 0.25 | 0.00 |
| bollinger_reversion | NULL4 | False | 9.31 | -0.26 | -24.4% | -52.2% | 0.97 | 319 | 0.25 | 0.20 |
| vol_expansion | NULL3 | False | 9.21 | -3.36 | -27.3% | -30.6% | 0.40 | 44 | 0.00 | 0.00 |
| zscore_reversion | NULL4 | False | 8.68 | -1.81 | -45.4% | -58.8% | 0.62 | 40 | 0.25 | 0.03 |
| squeeze_breakout | NULL3 | False | 8.6 | -1.22 | -30.6% | -39.6% | 0.67 | 29 | 0.25 | 0.02 |
| liquidity_sweep | NULL4 | False | 8.59 | -0.34 | -26.2% | -64.6% | 0.95 | 80 | 0.25 | 0.15 |
| bollinger_reversion | NULL3 | False | 8.19 | -0.77 | -36.6% | -53.7% | 0.72 | 55 | 0.25 | 0.06 |
| atr_breakout | NULL2 | False | 7.77 | -2.30 | -50.8% | -59.0% | 0.65 | 70 | 0.25 | 0.01 |
| relative_strength | NULL4 | False | 7.36 | -1.77 | -38.5% | -44.9% | 0.75 | 107 | 0.25 | 0.02 |
| relative_value | NULL1+NULL4 | False | 7.27 | -3.62 | -51.3% | -65.0% | 0.20 | 12 | 0.25 | 0.00 |
| trend_acceleration | NULL3 | False | 7.12 | -2.30 | -44.0% | -52.7% | 0.74 | 182 | 0.25 | 0.01 |
| regime_switch | NULL3 | False | 6.89 | -1.79 | -49.8% | -60.4% | 0.79 | 236 | 0.25 | 0.09 |
| zscore_reversion | NULL1 | False | 6.56 | -1.90 | -40.9% | -45.1% | 0.62 | 46 | 0.00 | 0.01 |
| support_resistance | NULL2 | False | 5.37 | -2.01 | -58.7% | -66.9% | 0.72 | 123 | 0.25 | 0.02 |
| liquidity_sweep | NULL2 | False | 5.27 | -1.07 | -44.1% | -56.6% | 0.85 | 184 | 0.25 | 0.01 |
| bollinger_reversion | NULL1 | False | 5.06 | -3.62 | -78.8% | -84.4% | 0.43 | 65 | 0.25 | 0.00 |
| trend_acceleration | NULL4 | False | 4.13 | -1.05 | -26.9% | -41.9% | 0.93 | 202 | 0.00 | 0.05 |
| zscore_reversion | NULL2 | False | 4.06 | -1.37 | -33.4% | -45.3% | 0.56 | 27 | 0.00 | 0.04 |
| donchian_breakout | NULL3 | False | 3.38 | -0.44 | -28.3% | -49.0% | 0.87 | 51 | 0.00 | 0.13 |
| volume_momentum | NULL1 | False | 3.24 | -2.41 | -52.7% | -56.5% | 0.91 | 470 | 0.00 | 0.01 |
| liquidity_sweep | NULL3 | False | 2.74 | -0.61 | -31.7% | -41.9% | 0.83 | 78 | 0.00 | 0.09 |
| volume_momentum | NULL3 | False | 0.17 | -4.31 | -72.4% | -73.9% | 0.76 | 460 | 0.00 | 0.00 |
| bollinger_reversion | NULL2 | False | 0.16 | -2.25 | -64.7% | -76.3% | 0.60 | 77 | 0.00 | 0.01 |

## Rejected candidates — reasons

- `atr_breakout` [NULL1]: OOS return -10.5% ≤ 0; OOS Sharpe -2.97 < 1.0; OOS PF 0.00 < 1.15; 2 OOS trades < 25; OOS/IS Sharpe -5.52 < 0.4 (overfit); only 0% WF windows positive; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.23 — edge dies with delay
- `atr_breakout` [NULL2]: OOS return -50.8% ≤ 0; OOS Sharpe -2.30 < 1.0; OOS PF 0.65 < 1.15; OOS maxDD 59.0% > 25%; only 25% WF windows positive; MC p05 drawdown 77.0% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.30 — edge dies with delay
- `atr_breakout` [NULL3]: OOS return -35.3% ≤ 0; OOS Sharpe -1.08 < 1.0; OOS PF 0.78 < 1.15; OOS maxDD 55.8% > 25%; OOS/IS Sharpe -0.62 < 0.4 (overfit); MC p05 drawdown 74.4% > 35%; deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.50 — edge dies with delay
- `atr_breakout` [NULL4]: OOS maxDD 31.1% > 25%; MC p05 drawdown 50.9% > 35%; deflated P(SR>0) 0.21 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 35.3% > 35%
- `bollinger_reversion` [NULL1]: OOS return -78.8% ≤ 0; OOS Sharpe -3.62 < 1.0; OOS PF 0.43 < 1.15; OOS maxDD 84.4% > 25%; only 25% WF windows positive; MC p05 drawdown 93.2% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -3.86 — edge dies with delay; worst regime DD 62.3% > 35%
- `bollinger_reversion` [NULL2]: OOS return -64.7% ≤ 0; OOS Sharpe -2.25 < 1.0; OOS PF 0.60 < 1.15; OOS maxDD 76.3% > 25%; only 0% WF windows positive; MC p05 drawdown 88.6% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.41 — edge dies with delay; worst regime DD 54.2% > 35%
- `bollinger_reversion` [NULL3]: OOS return -36.6% ≤ 0; OOS Sharpe -0.77 < 1.0; OOS PF 0.72 < 1.15; OOS maxDD 53.7% > 25%; only 25% WF windows positive; MC p05 drawdown 81.5% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.06 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.39 — edge dies with delay; worst regime DD 35.7% > 35%
- `bollinger_reversion` [NULL4]: OOS return -24.4% ≤ 0; OOS Sharpe -0.26 < 1.0; OOS PF 0.97 < 1.15; OOS maxDD 52.2% > 25%; only 25% WF windows positive; MC p05 drawdown 80.9% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.20 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.17 — edge dies with delay; worst regime DD 42.2% > 35%
- `break_of_structure` [NULL1]: OOS maxDD 46.7% > 25%; MC p05 drawdown 75.4% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.49 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 35.7% > 35%
- `break_of_structure` [NULL2]: OOS return -5.7% ≤ 0; OOS Sharpe 0.31 < 1.0; OOS PF 1.08 < 1.15; OOS maxDD 56.7% > 25%; OOS/IS Sharpe 0.18 < 0.4 (overfit); MC p05 drawdown 73.5% > 35%; param retention 0.29 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.17 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.33 — edge dies with delay; worst regime DD 49.8% > 35%
- `break_of_structure` [NULL3]: OOS return -18.8% ≤ 0; OOS Sharpe -0.11 < 1.0; OOS PF 0.89 < 1.15; OOS maxDD 50.8% > 25%; MC p05 drawdown 76.8% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.05 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.26 — edge dies with delay
- `break_of_structure` [NULL4]: OOS maxDD 34.9% > 25%; MC p05 drawdown 66.5% > 35%; deflated P(SR>0) 0.51 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 40.9% > 35%
- `breakout_volume` [NULL1]: OOS maxDD 35.9% > 25%; MC p05 drawdown 54.7% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.44 < 0.8 (not distinguishable from luck over 962 trials)
- `breakout_volume` [NULL2]: OOS return -18.6% ≤ 0; OOS Sharpe -0.68 < 1.0; OOS PF 0.82 < 1.15; OOS maxDD 31.4% > 25%; OOS/IS Sharpe -0.39 < 0.4 (overfit); MC p05 drawdown 59.2% > 35%; deflated P(SR>0) 0.03 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.80 — edge dies with delay
- `breakout_volume` [NULL3]: OOS return -15.7% ≤ 0; OOS Sharpe -0.79 < 1.0; OOS PF 0.69 < 1.15; OOS maxDD 29.0% > 25%; 17 OOS trades < 25; OOS/IS Sharpe -1.07 < 0.4 (overfit); MC p05 drawdown 49.0% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.03 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.04 — edge dies with delay
- `breakout_volume` [NULL4]: OOS Sharpe 0.99 < 1.0; OOS maxDD 27.6% > 25%; MC p05 drawdown 57.3% > 35%; deflated P(SR>0) 0.07 < 0.8 (not distinguishable from luck over 962 trials)
- `coint_pair` [NULL1+NULL3]: OOS return -12.9% ≤ 0; OOS Sharpe -0.49 < 1.0; OOS PF 0.99 < 1.15; OOS maxDD 30.0% > 25%; OOS/IS Sharpe -0.40 < 0.4 (overfit); MC p05 drawdown 55.0% > 35%; deflated P(SR>0) 0.21 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.67 — edge dies with delay
- `coint_pair` [NULL1+NULL4]: OOS return -34.9% ≤ 0; OOS Sharpe -2.47 < 1.0; OOS PF 0.73 < 1.15; OOS maxDD 36.1% > 25%; OOS/IS Sharpe -4.66 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 63.0% > 35%; param retention -0.11 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.22 — edge dies with delay
- `corr_breakdown` [NULL1+NULL3]: OOS Sharpe 0.65 < 1.0; only 25% WF windows positive; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.30 < 0.8 (not distinguishable from luck over 962 trials)
- `corr_breakdown` [NULL1+NULL4]: OOS return -28.4% ≤ 0; OOS Sharpe -2.17 < 1.0; OOS PF 0.66 < 1.15; OOS maxDD 36.0% > 25%; OOS/IS Sharpe -1.82 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 56.1% > 35%; param retention -0.16 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.58 — edge dies with delay
- `donchian_breakout` [NULL1]: OOS maxDD 27.1% > 25%; 19 OOS trades < 25; MC p05 drawdown 62.2% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.51 < 0.8 (not distinguishable from luck over 962 trials)
- `donchian_breakout` [NULL2]: OOS Sharpe 0.91 < 1.0; OOS maxDD 27.5% > 25%; OOS/IS Sharpe 0.37 < 0.4 (overfit); MC p05 drawdown 54.5% > 35%; deflated P(SR>0) 0.46 < 0.8 (not distinguishable from luck over 962 trials)
- `donchian_breakout` [NULL3]: OOS return -28.3% ≤ 0; OOS Sharpe -0.44 < 1.0; OOS PF 0.87 < 1.15; OOS maxDD 49.0% > 25%; only 0% WF windows positive; MC p05 drawdown 77.7% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.13 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.92 — edge dies with delay; worst regime DD 40.6% > 35%
- `donchian_breakout` [NULL4]: MC p05 drawdown 49.7% > 35%; param retention -0.07 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.19 < 0.8 (not distinguishable from luck over 962 trials)
- `ema_cross` [NULL1]: OOS maxDD 30.3% > 25%; 9 OOS trades < 25; MC p05 drawdown 55.3% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike)
- `ema_cross` [NULL2]: OOS maxDD 41.9% > 25%; MC p05 drawdown 67.1% > 35%; deflated P(SR>0) 0.41 < 0.8 (not distinguishable from luck over 962 trials)
- `ema_cross` [NULL3]: OOS return -48.2% ≤ 0; OOS Sharpe -1.31 < 1.0; OOS PF 0.44 < 1.15; OOS maxDD 51.0% > 25%; 21 OOS trades < 25; OOS/IS Sharpe -1.32 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 82.1% > 35%; deflated P(SR>0) 0.07 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.23 — edge dies with delay
- `ema_cross` [NULL4]: OOS maxDD 33.5% > 25%; MC p05 drawdown 63.8% > 35%; deflated P(SR>0) 0.47 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 43.7% > 35%
- `ensemble_vote` [NULL1]: MC p05 drawdown 46.5% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike)
- `ensemble_vote` [NULL2]: OOS Sharpe 0.37 < 1.0; OOS maxDD 25.2% > 25%; OOS/IS Sharpe 0.16 < 0.4 (overfit); MC p05 drawdown 52.0% > 35%; deflated P(SR>0) 0.32 < 0.8 (not distinguishable from luck over 962 trials)
- `ensemble_vote` [NULL3]: OOS return -45.7% ≤ 0; OOS Sharpe -2.24 < 1.0; OOS PF 0.52 < 1.15; OOS maxDD 49.9% > 25%; MC p05 drawdown 70.7% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.03 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.24 — edge dies with delay
- `ensemble_vote` [NULL4]: MC p05 drawdown 37.4% > 35%
- `liquidity_sweep` [NULL1]: OOS return -5.8% ≤ 0; OOS Sharpe 0.22 < 1.0; OOS PF 1.07 < 1.15; OOS maxDD 44.8% > 25%; OOS/IS Sharpe 0.29 < 0.4 (overfit); MC p05 drawdown 73.7% > 35%; param retention -0.58 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.03 < 0.8 (not distinguishable from luck over 962 trials)
- `liquidity_sweep` [NULL2]: OOS return -44.1% ≤ 0; OOS Sharpe -1.07 < 1.0; OOS PF 0.85 < 1.15; OOS maxDD 56.6% > 25%; OOS/IS Sharpe -7.51 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 81.9% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.44 — edge dies with delay; worst regime DD 48.9% > 35%
- `liquidity_sweep` [NULL3]: OOS return -31.7% ≤ 0; OOS Sharpe -0.61 < 1.0; OOS PF 0.83 < 1.15; OOS maxDD 41.9% > 25%; OOS/IS Sharpe -1.41 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 77.6% > 35%; param retention -0.10 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.09 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.15 — edge dies with delay; worst regime DD 41.5% > 35%
- `liquidity_sweep` [NULL4]: OOS return -26.2% ≤ 0; OOS Sharpe -0.34 < 1.0; OOS PF 0.95 < 1.15; OOS maxDD 64.6% > 25%; only 25% WF windows positive; MC p05 drawdown 82.2% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.15 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.14 — edge dies with delay; worst regime DD 41.7% > 35%
- `momentum_persistence` [NULL1]: param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.31 < 0.8 (not distinguishable from luck over 962 trials)
- `momentum_persistence` [NULL2]: OOS return -10.9% ≤ 0; OOS Sharpe -2.97 < 1.0; OOS PF 0.28 < 1.15; 19 OOS trades < 25; OOS/IS Sharpe -1.96 < 0.4 (overfit); param retention -0.03 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.24 — edge dies with delay
- `momentum_persistence` [NULL3]: OOS Sharpe 0.33 < 1.0; 11 OOS trades < 25; OOS/IS Sharpe 0.34 < 0.4 (overfit); param retention -0.98 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.72 — edge dies with delay
- `momentum_persistence` [NULL4]: param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.30 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.06 — edge dies with delay
- `mtf_trend` [NULL1]: OOS maxDD 27.8% > 25%; MC p05 drawdown 45.2% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike)
- `mtf_trend` [NULL2]: OOS maxDD 37.0% > 25%; MC p05 drawdown 58.4% > 35%; deflated P(SR>0) 0.59 < 0.8 (not distinguishable from luck over 962 trials)
- `mtf_trend` [NULL3]: OOS return -39.2% ≤ 0; OOS Sharpe -1.47 < 1.0; OOS PF 0.49 < 1.15; OOS maxDD 51.0% > 25%; OOS/IS Sharpe -0.78 < 0.4 (overfit); MC p05 drawdown 72.8% > 35%; deflated P(SR>0) 0.05 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.44 — edge dies with delay; worst regime DD 38.2% > 35%
- `mtf_trend` [NULL4]: OOS maxDD 28.1% > 25%; MC p05 drawdown 52.2% > 35%; deflated P(SR>0) 0.64 < 0.8 (not distinguishable from luck over 962 trials)
- `orderflow_proxy` [NULL1]: OOS maxDD 32.7% > 25%; MC p05 drawdown 48.5% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.35 < 0.8 (not distinguishable from luck over 962 trials)
- `orderflow_proxy` [NULL2]: OOS maxDD 26.3% > 25%; MC p05 drawdown 41.4% > 35%; param retention 0.29 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.67 < 0.8 (not distinguishable from luck over 962 trials)
- `orderflow_proxy` [NULL3]: OOS return -22.7% ≤ 0; OOS Sharpe -0.49 < 1.0; OOS PF 0.94 < 1.15; OOS maxDD 43.8% > 25%; OOS/IS Sharpe -1.03 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 70.5% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.06 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 38.4% > 35%
- `orderflow_proxy` [NULL4]: OOS Sharpe 0.58 < 1.0; OOS maxDD 38.5% > 25%; MC p05 drawdown 60.1% > 35%; param retention -0.13 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.28 < 0.8 (not distinguishable from luck over 962 trials)
- `regime_gated_reversion` [NULL1]: OOS return -7.8% ≤ 0; OOS Sharpe -0.88 < 1.0; OOS PF 0.83 < 1.15; OOS/IS Sharpe -2.29 < 0.4 (overfit); only 25% WF windows positive; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.34 — edge dies with delay
- `regime_gated_reversion` [NULL2]: OOS return -10.4% ≤ 0; OOS Sharpe -0.83 < 1.0; OOS PF 0.82 < 1.15; MC p05 drawdown 36.8% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.11 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.03 — edge dies with delay
- `regime_gated_reversion` [NULL3]: OOS return -11.1% ≤ 0; OOS Sharpe -1.25 < 1.0; OOS PF 0.73 < 1.15; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.41 — edge dies with delay
- `regime_gated_reversion` [NULL4]: OOS return -35.1% ≤ 0; OOS Sharpe -3.59 < 1.0; OOS PF 0.45 < 1.15; OOS maxDD 36.8% > 25%; only 25% WF windows positive; MC p05 drawdown 53.3% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.90 — edge dies with delay
- `regime_gated_trend` [NULL1]: OOS return -43.1% ≤ 0; OOS Sharpe -1.90 < 1.0; OOS PF 0.72 < 1.15; OOS maxDD 53.7% > 25%; MC p05 drawdown 76.3% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.86 — edge dies with delay; worst regime DD 51.0% > 35%
- `regime_gated_trend` [NULL2]: OOS Sharpe 0.67 < 1.0; OOS maxDD 35.2% > 25%; OOS/IS Sharpe 0.37 < 0.4 (overfit); MC p05 drawdown 54.2% > 35%; deflated P(SR>0) 0.17 < 0.8 (not distinguishable from luck over 962 trials)
- `regime_gated_trend` [NULL3]: OOS return -43.1% ≤ 0; OOS Sharpe -1.28 < 1.0; OOS PF 0.79 < 1.15; OOS maxDD 58.7% > 25%; OOS/IS Sharpe -2.55 < 0.4 (overfit); MC p05 drawdown 76.8% > 35%; param retention -0.33 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.07 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.25 — edge dies with delay; worst regime DD 40.0% > 35%
- `regime_gated_trend` [NULL4]: OOS maxDD 27.6% > 25%; MC p05 drawdown 49.4% > 35%; deflated P(SR>0) 0.12 < 0.8 (not distinguishable from luck over 962 trials)
- `regime_switch` [NULL1]: OOS Sharpe 0.70 < 1.0; OOS PF 1.14 < 1.15; OOS maxDD 30.7% > 25%; MC p05 drawdown 68.6% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.49 < 0.8 (not distinguishable from luck over 962 trials)
- `regime_switch` [NULL2]: MC p05 drawdown 50.3% > 35%; deflated P(SR>0) 0.47 < 0.8 (not distinguishable from luck over 962 trials)
- `regime_switch` [NULL3]: OOS return -49.8% ≤ 0; OOS Sharpe -1.79 < 1.0; OOS PF 0.79 < 1.15; OOS maxDD 60.4% > 25%; only 25% WF windows positive; MC p05 drawdown 82.6% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.09 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.54 — edge dies with delay; worst regime DD 46.3% > 35%
- `regime_switch` [NULL4]: OOS return -17.9% ≤ 0; OOS Sharpe -0.21 < 1.0; OOS PF 0.99 < 1.15; OOS maxDD 50.7% > 25%; OOS/IS Sharpe -0.55 < 0.4 (overfit); MC p05 drawdown 69.3% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 36.5% > 35%
- `relative_strength` [NULL1]: OOS Sharpe 0.83 < 1.0; OOS maxDD 28.3% > 25%; MC p05 drawdown 56.3% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.13 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.38 — edge dies with delay
- `relative_strength` [NULL2]: OOS return -41.0% ≤ 0; OOS Sharpe -1.97 < 1.0; OOS PF 0.77 < 1.15; OOS maxDD 41.9% > 25%; OOS/IS Sharpe -2.27 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 70.7% > 35%; deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.67 — edge dies with delay
- `relative_strength` [NULL3]: OOS return -39.9% ≤ 0; OOS Sharpe -2.02 < 1.0; OOS PF 0.65 < 1.15; OOS maxDD 42.1% > 25%; OOS/IS Sharpe -14.44 < 0.4 (overfit); MC p05 drawdown 69.7% > 35%; param retention -0.71 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.41 — edge dies with delay
- `relative_strength` [NULL4]: OOS return -38.5% ≤ 0; OOS Sharpe -1.77 < 1.0; OOS PF 0.75 < 1.15; OOS maxDD 44.9% > 25%; OOS/IS Sharpe -2.03 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 69.3% > 35%; param retention -0.08 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.31 — edge dies with delay; worst regime DD 37.6% > 35%
- `relative_value` [NULL1+NULL3]: MC p05 drawdown 35.9% > 35%; param retention -0.02 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.14 < 0.8 (not distinguishable from luck over 962 trials)
- `relative_value` [NULL1+NULL4]: OOS return -51.3% ≤ 0; OOS Sharpe -3.62 < 1.0; OOS PF 0.20 < 1.15; OOS maxDD 65.0% > 25%; 12 OOS trades < 25; OOS/IS Sharpe -15.26 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 73.8% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -3.55 — edge dies with delay; worst regime DD 35.8% > 35%
- `rsi_reversion` [NULL1]: OOS return -4.0% ≤ 0; OOS Sharpe -0.14 < 1.0; OOS PF 0.89 < 1.15; 10 OOS trades < 25; OOS/IS Sharpe -0.09 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 36.4% > 35%; deflated P(SR>0) 0.04 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.15 — edge dies with delay
- `rsi_reversion` [NULL2]: OOS Sharpe 0.13 < 1.0; OOS PF 1.11 < 1.15; 9 OOS trades < 25; only 25% WF windows positive; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.08 < 0.8 (not distinguishable from luck over 962 trials)
- `rsi_reversion` [NULL3]: OOS Sharpe 0.18 < 1.0; OOS PF 1.14 < 1.15; 9 OOS trades < 25; OOS/IS Sharpe 0.10 < 0.4 (overfit); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.34 — edge dies with delay
- `rsi_reversion` [NULL4]: OOS Sharpe 0.99 < 1.0; 8 OOS trades < 25; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.14 < 0.8 (not distinguishable from luck over 962 trials)
- `sma_cross` [NULL1]: OOS Sharpe 0.92 < 1.0; OOS maxDD 40.0% > 25%; MC p05 drawdown 75.6% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.39 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 47.9% > 35%
- `sma_cross` [NULL2]: OOS Sharpe 0.89 < 1.0; OOS maxDD 41.6% > 25%; MC p05 drawdown 67.8% > 35%; deflated P(SR>0) 0.41 < 0.8 (not distinguishable from luck over 962 trials)
- `sma_cross` [NULL3]: OOS return -24.6% ≤ 0; OOS Sharpe -0.30 < 1.0; OOS PF 0.91 < 1.15; OOS maxDD 38.9% > 25%; OOS/IS Sharpe -0.40 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 81.3% > 35%; param retention 0.20 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.10 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 38.1% > 35%
- `sma_cross` [NULL4]: OOS Sharpe 0.65 < 1.0; OOS maxDD 44.1% > 25%; OOS/IS Sharpe 0.38 < 0.4 (overfit); MC p05 drawdown 70.7% > 35%; deflated P(SR>0) 0.29 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 40.6% > 35%
- `squeeze_breakout` [NULL1]: OOS maxDD 33.9% > 25%; MC p05 drawdown 56.2% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.49 < 0.8 (not distinguishable from luck over 962 trials)
- `squeeze_breakout` [NULL2]: OOS return -11.4% ≤ 0; OOS Sharpe -0.12 < 1.0; OOS PF 0.95 < 1.15; OOS maxDD 33.3% > 25%; OOS/IS Sharpe -0.05 < 0.4 (overfit); MC p05 drawdown 63.0% > 35%; deflated P(SR>0) 0.05 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.03 — edge dies with delay
- `squeeze_breakout` [NULL3]: OOS return -30.6% ≤ 0; OOS Sharpe -1.22 < 1.0; OOS PF 0.67 < 1.15; OOS maxDD 39.6% > 25%; OOS/IS Sharpe -33.46 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 67.7% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.48 — edge dies with delay
- `squeeze_breakout` [NULL4]: OOS maxDD 32.6% > 25%; MC p05 drawdown 40.8% > 35%; deflated P(SR>0) 0.75 < 0.8 (not distinguishable from luck over 962 trials)
- `support_resistance` [NULL1]: OOS maxDD 45.2% > 25%; MC p05 drawdown 64.4% > 35%; param retention -0.30 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.24 < 0.8 (not distinguishable from luck over 962 trials)
- `support_resistance` [NULL2]: OOS return -58.7% ≤ 0; OOS Sharpe -2.01 < 1.0; OOS PF 0.72 < 1.15; OOS maxDD 66.9% > 25%; only 25% WF windows positive; MC p05 drawdown 85.1% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.62 — edge dies with delay; worst regime DD 52.6% > 35%
- `support_resistance` [NULL3]: OOS Sharpe 0.84 < 1.0; OOS PF 1.13 < 1.15; OOS maxDD 43.5% > 25%; only 0% WF windows positive; MC p05 drawdown 65.5% > 35%; deflated P(SR>0) 0.35 < 0.8 (not distinguishable from luck over 962 trials)
- `support_resistance` [NULL4]: OOS Sharpe 0.82 < 1.0; OOS PF 1.14 < 1.15; OOS maxDD 43.3% > 25%; MC p05 drawdown 71.9% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.35 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 40.1% > 35%
- `trend_acceleration` [NULL1]: OOS maxDD 27.8% > 25%; MC p05 drawdown 43.2% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.56 < 0.8 (not distinguishable from luck over 962 trials)
- `trend_acceleration` [NULL2]: OOS return -16.6% ≤ 0; OOS Sharpe -0.97 < 1.0; OOS PF 0.93 < 1.15; only 25% WF windows positive; MC p05 drawdown 46.1% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.09 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.43 — edge dies with delay
- `trend_acceleration` [NULL3]: OOS return -44.0% ≤ 0; OOS Sharpe -2.30 < 1.0; OOS PF 0.74 < 1.15; OOS maxDD 52.7% > 25%; only 25% WF windows positive; MC p05 drawdown 69.1% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -3.28 — edge dies with delay; worst regime DD 37.9% > 35%
- `trend_acceleration` [NULL4]: OOS return -26.9% ≤ 0; OOS Sharpe -1.05 < 1.0; OOS PF 0.93 < 1.15; OOS maxDD 41.9% > 25%; OOS/IS Sharpe -8.61 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 62.8% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.05 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.68 — edge dies with delay
- `trend_pullback` [NULL1]: OOS maxDD 38.7% > 25%; MC p05 drawdown 59.6% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike)
- `trend_pullback` [NULL2]: OOS return -12.1% ≤ 0; OOS Sharpe 0.13 < 1.0; OOS maxDD 62.5% > 25%; 19 OOS trades < 25; OOS/IS Sharpe 0.07 < 0.4 (overfit); MC p05 drawdown 75.5% > 35%; deflated P(SR>0) 0.29 < 0.8 (not distinguishable from luck over 962 trials)
- `trend_pullback` [NULL3]: OOS return -62.3% ≤ 0; OOS Sharpe -2.16 < 1.0; OOS PF 0.24 < 1.15; OOS maxDD 68.2% > 25%; 24 OOS trades < 25; OOS/IS Sharpe -2.94 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 85.7% > 35%; deflated P(SR>0) 0.04 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.13 — edge dies with delay; worst regime DD 35.8% > 35%
- `trend_pullback` [NULL4]: OOS maxDD 35.2% > 25%; MC p05 drawdown 65.8% > 35%; deflated P(SR>0) 0.55 < 0.8 (not distinguishable from luck over 962 trials)
- `tsmom` [NULL1]: OOS maxDD 43.0% > 25%; 21 OOS trades < 25; MC p05 drawdown 57.0% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.52 < 0.8 (not distinguishable from luck over 962 trials)
- `tsmom` [NULL2]: OOS maxDD 34.5% > 25%; MC p05 drawdown 56.2% > 35%; deflated P(SR>0) 0.60 < 0.8 (not distinguishable from luck over 962 trials)
- `tsmom` [NULL3]: OOS return -60.3% ≤ 0; OOS Sharpe -2.20 < 1.0; OOS PF 0.52 < 1.15; OOS maxDD 72.1% > 25%; OOS/IS Sharpe -1.13 < 0.4 (overfit); MC p05 drawdown 83.9% > 35%; param retention 0.01 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.79 — edge dies with delay; worst regime DD 37.4% > 35%
- `tsmom` [NULL4]: OOS maxDD 28.5% > 25%; MC p05 drawdown 55.9% > 35%; deflated P(SR>0) 0.19 < 0.8 (not distinguishable from luck over 962 trials)
- `vol_exhaustion` [NULL1]: OOS return -22.1% ≤ 0; OOS Sharpe -1.71 < 1.0; OOS PF 0.46 < 1.15; OOS maxDD 37.7% > 25%; 10 OOS trades < 25; OOS/IS Sharpe -0.91 < 0.4 (overfit); MC p05 drawdown 55.8% > 35%; deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.60 — edge dies with delay; worst regime DD 38.3% > 35%
- `vol_exhaustion` [NULL2]: 10 OOS trades < 25; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.46 < 0.8 (not distinguishable from luck over 962 trials)
- `vol_exhaustion` [NULL3]: OOS return -4.8% ≤ 0; OOS Sharpe -1.09 < 1.0; OOS PF 0.07 < 1.15; 2 OOS trades < 25; OOS/IS Sharpe -2.71 < 0.4 (overfit); param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.09 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.83 — edge dies with delay
- `vol_exhaustion` [NULL4]: OOS return -11.9% ≤ 0; OOS Sharpe -0.96 < 1.0; OOS PF 0.58 < 1.15; 7 OOS trades < 25; OOS/IS Sharpe -7.39 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 37.5% > 35%; param retention -0.54 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials)
- `vol_expansion` [NULL1]: 23 OOS trades < 25; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.19 < 0.8 (not distinguishable from luck over 962 trials)
- `vol_expansion` [NULL2]: param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.54 < 0.8 (not distinguishable from luck over 962 trials)
- `vol_expansion` [NULL3]: OOS return -27.3% ≤ 0; OOS Sharpe -3.36 < 1.0; OOS PF 0.40 < 1.15; OOS maxDD 30.6% > 25%; only 0% WF windows positive; MC p05 drawdown 51.1% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials)
- `vol_expansion` [NULL4]: OOS maxDD 26.5% > 25%; MC p05 drawdown 39.7% > 35%; param retention -0.43 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.53 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.12 — edge dies with delay
- `vol_regime_momentum` [NULL1]: OOS Sharpe 0.30 < 1.0; OOS PF 1.11 < 1.15; OOS maxDD 29.3% > 25%; MC p05 drawdown 58.1% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.03 — edge dies with delay
- `vol_regime_momentum` [NULL2]: OOS maxDD 30.4% > 25%; MC p05 drawdown 53.6% > 35%; param retention -0.49 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.25 < 0.8 (not distinguishable from luck over 962 trials)
- `vol_regime_momentum` [NULL3]: OOS return -32.8% ≤ 0; OOS Sharpe -1.49 < 1.0; OOS PF 0.83 < 1.15; OOS maxDD 39.3% > 25%; OOS/IS Sharpe -11.87 < 0.4 (overfit); MC p05 drawdown 65.2% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.03 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.27 — edge dies with delay
- `vol_regime_momentum` [NULL4]: MC p05 drawdown 37.2% > 35%; param retention -0.01 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.23 < 0.8 (not distinguishable from luck over 962 trials)
- `volume_momentum` [NULL1]: OOS return -52.7% ≤ 0; OOS Sharpe -2.41 < 1.0; OOS PF 0.91 < 1.15; OOS maxDD 56.5% > 25%; only 0% WF windows positive; MC p05 drawdown 79.5% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.61 — edge dies with delay
- `volume_momentum` [NULL2]: OOS return -22.9% ≤ 0; OOS Sharpe -0.61 < 1.0; OOS PF 1.05 < 1.15; OOS maxDD 39.1% > 25%; only 25% WF windows positive; MC p05 drawdown 66.6% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.08 < 0.8 (not distinguishable from luck over 962 trials)
- `volume_momentum` [NULL3]: OOS return -72.4% ≤ 0; OOS Sharpe -4.31 < 1.0; OOS PF 0.76 < 1.15; OOS maxDD 73.9% > 25%; only 0% WF windows positive; MC p05 drawdown 88.1% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -4.31 — edge dies with delay; worst regime DD 48.9% > 35%
- `volume_momentum` [NULL4]: OOS return -18.9% ≤ 0; OOS Sharpe -0.42 < 1.0; OOS PF 1.07 < 1.15; OOS maxDD 43.4% > 25%; MC p05 drawdown 65.0% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.19 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.52 — edge dies with delay; worst regime DD 35.0% > 35%
- `weighted_composite` [NULL1]: OOS Sharpe 0.36 < 1.0; OOS PF 1.13 < 1.15; MC p05 drawdown 53.4% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.59 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -0.17 — edge dies with delay
- `weighted_composite` [NULL2]: OOS maxDD 38.5% > 25%; MC p05 drawdown 58.2% > 35%; deflated P(SR>0) 0.64 < 0.8 (not distinguishable from luck over 962 trials)
- `weighted_composite` [NULL3]: OOS return -54.2% ≤ 0; OOS Sharpe -1.96 < 1.0; OOS PF 0.50 < 1.15; OOS maxDD 62.2% > 25%; OOS/IS Sharpe -4.92 < 0.4 (overfit); MC p05 drawdown 81.5% > 35%; param retention -1.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.00 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.25 — edge dies with delay
- `weighted_composite` [NULL4]: OOS Sharpe 0.50 < 1.0; OOS maxDD 39.1% > 25%; OOS/IS Sharpe 0.35 < 0.4 (overfit); MC p05 drawdown 70.0% > 35%; deflated P(SR>0) 0.23 < 0.8 (not distinguishable from luck over 962 trials); worst regime DD 40.9% > 35%
- `xsec_momentum` [NULL1+NULL2+NULL3+NULL4]: OOS return -32.0% ≤ 0; OOS Sharpe -1.81 < 1.0; OOS PF 0.82 < 1.15; OOS maxDD 42.0% > 25%; OOS/IS Sharpe -2.43 < 0.4 (overfit); only 25% WF windows positive; MC p05 drawdown 60.5% > 35%; deflated P(SR>0) 0.02 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.08 — edge dies with delay
- `zscore_reversion` [NULL1]: OOS return -40.9% ≤ 0; OOS Sharpe -1.90 < 1.0; OOS PF 0.62 < 1.15; OOS maxDD 45.1% > 25%; OOS/IS Sharpe -2.47 < 0.4 (overfit); only 0% WF windows positive; MC p05 drawdown 71.9% > 35%; deflated P(SR>0) 0.01 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -2.17 — edge dies with delay
- `zscore_reversion` [NULL2]: OOS return -33.4% ≤ 0; OOS Sharpe -1.37 < 1.0; OOS PF 0.56 < 1.15; OOS maxDD 45.3% > 25%; only 0% WF windows positive; MC p05 drawdown 68.9% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.04 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.46 — edge dies with delay
- `zscore_reversion` [NULL3]: OOS Sharpe 0.88 < 1.0; MC p05 drawdown 49.7% > 35%; param retention 0.06 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.12 < 0.8 (not distinguishable from luck over 962 trials)
- `zscore_reversion` [NULL4]: OOS return -45.4% ≤ 0; OOS Sharpe -1.81 < 1.0; OOS PF 0.62 < 1.15; OOS maxDD 58.8% > 25%; only 25% WF windows positive; MC p05 drawdown 80.2% > 35%; param retention 0.00 < 0.3 (performance is a parameter spike); deflated P(SR>0) 0.03 < 0.8 (not distinguishable from luck over 962 trials); +1-bar-lag Sharpe -1.59 — edge dies with delay
