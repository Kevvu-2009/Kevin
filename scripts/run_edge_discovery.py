"""Edge-discovery runner.

Three modes:

1. CALIBRATION (offline, no network) — proves the harness itself:
     python scripts/run_edge_discovery.py --calibrate
   * NULL test: martingale data (zero drift, GARCH vol). A trustworthy
     pipeline must reject ~everything here; acceptances are false positives.
   * POWER test: regime-switching data with PLANTED trend structure. The
     pipeline must find the planted edge family; missing it means the
     validation is so strict it would never select anything.

2. REAL DATA (requires network or a populated cache):
     python scripts/run_edge_discovery.py --symbols BTC/USDT,ETH/USDT \
         --exchange binance --since 2021-01-01 --timeframe 1h
   Equivalent to `python -m quantbot.cli discover` and writes the same
   reports (leaderboard.csv, report.md/html, summary.json).

3. CONFIG file:
     python scripts/run_edge_discovery.py --config config/discovery.yaml
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def calibrate(out_root: Path, include_ml: bool = False) -> int:
    from quantbot.data.synthetic import generate_ohlcv, generate_random_walk
    from quantbot.reporting.research_report import write_research_report
    from quantbot.research.discovery import DiscoveryConfig, run_discovery

    cfg = DiscoveryConfig(timeframe="1h", include_ml=include_ml, mc_sims=400, wf_splits=4)

    print("=" * 72)
    print("CALIBRATION 1/2 — NULL TEST (martingale data; expect ~zero passes)")
    print("=" * 72)
    null_panel = {
        f"NULL{i}": generate_random_walk(n=12_000, seed=100 + i) for i in range(1, 5)
    }
    null_res = run_discovery(null_panel, cfg)
    n_null = len(null_res.candidates)
    fp_rate = len(null_res.selected) / max(1, n_null)
    print(f"\nNull result: {len(null_res.selected)}/{n_null} accepted "
          f"(false-positive rate {fp_rate:.1%})")
    write_research_report(null_res, out_root / "null",
                          title="Calibration — NULL (martingale) data")

    print()
    print("=" * 72)
    print("CALIBRATION 2/2 — POWER TEST (planted trend regimes; expect trend-family passes)")
    print("=" * 72)
    power_panel = {
        f"TREND{i}": generate_ohlcv(n=12_000, seed=10 + i, start_price=100.0 * i)
        for i in range(1, 5)
    }
    power_res = run_discovery(power_panel, cfg)
    n_pow = len(power_res.candidates)
    print(f"\nPower result: {len(power_res.selected)}/{n_pow} accepted")
    for cv in power_res.selected[:10]:
        print(f"  {cv.robustness_score:6.1f}  {cv.signal_name:24s} "
              f"[{'+'.join(cv.symbols)}]  OOS Sharpe {cv.oos_stats['sharpe']:.2f} "
              f"DSR {cv.deflated_prob:.2f}")
    write_research_report(power_res, out_root / "power",
                          title="Calibration — POWER (planted trend) data")

    print()
    print("=" * 72)
    print("CALIBRATION VERDICT")
    print("=" * 72)
    ok_null = fp_rate <= 0.05
    ok_power = any(cv.family in ("trend", "momentum", "regime", "hybrid")
                   for cv in power_res.selected)
    print(f"  false-positive control (≤5% on null): {'PASS' if ok_null else 'FAIL'} "
          f"({fp_rate:.1%})")
    print(f"  discovery power (planted edge found):  {'PASS' if ok_power else 'FAIL'} "
          f"({len(power_res.selected)} selections)")
    print(f"  reports: {out_root}/null, {out_root}/power")
    return 0 if (ok_null and ok_power) else 1


def real_run(args) -> int:
    from quantbot.cli import cmd_discover

    return cmd_discover(args)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calibrate", action="store_true",
                    help="run the offline null+power calibration of the harness")
    ap.add_argument("--include-ml", action="store_true",
                    help="include ML candidates in calibration (slow)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--exchange", default="binance")
    ap.add_argument("--since", default=None)
    ap.add_argument("--cache-dir", default="data_cache")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", default="reports/research")
    args = ap.parse_args()

    if args.calibrate:
        return calibrate(Path("reports/research_calibration"), args.include_ml)
    if not (args.config or args.symbols):
        ap.error("provide --calibrate, --config, or --symbols")
    return real_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
