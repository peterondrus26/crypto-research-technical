"""
batch.py — Run a strategy across many pairs and timeframes.

Usage:
    python batch.py --strategy breakout --pairs SOL/USDT,BTC/USDT,ETH/USDT \
                    --timeframes 5m,1h --days 30
"""

import argparse
import itertools
import sys
import time

import pandas as pd

import config
from config_loader import load_config
import registry
from core.data_loader import load_or_fetch
from core.backtest_engine import run, prepare_dataframe

DEFAULT_PAIRS = ["SOL/USDT", "BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT"]
DEFAULT_TIMEFRAMES = ["5m", "1h"]


def run_batch(
    strategy_name: str,
    pairs: list[str],
    timeframes: list[str],
    days_map: dict[str, int],
    config_path: str,
):
    load_config(config_path)
    strategy_cls = registry.get_strategy_class(strategy_name)

    combos = list(itertools.product(pairs, timeframes))
    print(f"[BATCH] Testing {strategy_name} on {len(combos)} pairs × timeframes")
    print(f"[BATCH] Pairs:      {pairs}")
    print(f"[BATCH] Timeframes: {timeframes}\n")

    results = []
    t0 = time.time()

    for i, (pair, tf) in enumerate(combos, 1):
        days = days_map[tf]
        try:
            df_raw = load_or_fetch(pair, tf, days)
            df = prepare_dataframe(df_raw)
            strat = strategy_cls()
            result = run(df, strat)
            s = result.summary

            if not s:
                row = {
                    "pair": pair,
                    "tf": tf,
                    "trades": 0,
                    "strategy_return": 0.0,
                    "note": "no trades",
                }
            else:
                row = {
                    "pair": pair,
                    "tf": tf,
                    "trades": s["total_trades"],
                    "win_rate": round(s["win_rate"], 1),
                    "strategy_pnl": round(s["total_pnl"], 2),
                    "strategy_return": round(s["strategy_return"], 2),
                    "equity_return": round(s["total_return"], 2),
                    "max_dd": round(s["max_drawdown"], 2),
                    "rr": round(s["rr_ratio"], 2),
                    "tp": s["tp_exits"],
                    "sl": s["sl_exits"],
                    "time": s["time_exits"],
                }
            results.append(row)

            status = (
                f"trades={row.get('trades', 0):3d}  "
                f"ret={row.get('strategy_return', 0):+6.2f}%  "
                f"dd={row.get('max_dd', 0):+6.2f}%"
            )
            print(f"  [{i:2d}/{len(combos)}] {pair:10s} {tf:4s}  {status}")

        except Exception as e:
            print(f"  [{i:2d}/{len(combos)}] {pair:10s} {tf:4s}  ERROR: {e}")
            results.append(
                {"pair": pair, "tf": tf, "strategy_return": None, "note": str(e)}
            )

    elapsed = time.time() - t0
    df_res = pd.DataFrame(results)
    out_file = f"batch_{strategy_name}.csv"
    df_res.to_csv(out_file, index=False)

    print(f"\n[BATCH] Done in {elapsed:.0f}s. Results saved to {out_file}")

    # Summary table
    valid = df_res[df_res["strategy_return"].notna()]
    if len(valid) == 0:
        print("[BATCH] No valid results.")
        return

    print()
    print("=" * 90)
    print(f"  BATCH RESULTS — {strategy_name}")
    print("=" * 90)
    print(valid.sort_values("strategy_return", ascending=False).to_string(index=False))
    print()

    n_pos = (valid["strategy_return"] > 0).sum()
    print(f"  Positive combos:  {n_pos}/{len(valid)}")
    print(f"  Best return:      {valid['strategy_return'].max():+.2f}%")
    print(f"  Median return:    {valid['strategy_return'].median():+.2f}%")
    print(f"  Worst return:     {valid['strategy_return'].min():+.2f}%")
    print("=" * 90)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--pairs", default=",".join(DEFAULT_PAIRS))
    ap.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES))
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    pairs = [p.strip() for p in args.pairs.split(",")]
    timeframes = [t.strip() for t in args.timeframes.split(",")]
    config_path = args.config or f"config/{args.strategy}.yaml"

    # Days per timeframe: keep candle count reasonable
    days_map = {"5m": 30, "15m": 60, "1h": 180, "4h": 180, "1d": 365}

    run_batch(args.strategy, pairs, timeframes, days_map, config_path)


if __name__ == "__main__":
    main()
