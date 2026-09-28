"""
oos_test.py — Out-of-sample validation.

Fetches data ending at a fixed past date (default: 2026-03-31 UTC),
then runs the given strategy across all pairs on that held-out data.

Usage:
    python oos_test.py --strategy breakout
    python oos_test.py --strategy breakout --end-date 2026-03-31
"""
import argparse
import itertools
import time
from datetime import datetime, timezone

import pandas as pd

import config
from config_loader import load_config
import registry
from core.data_loader import load_or_fetch
from core.backtest_engine import run, prepare_dataframe


DEFAULT_PAIRS = ["SOL/USDT", "BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT"]


def parse_date(s: str) -> datetime:
    """Parse YYYY-MM-DD as end-of-day UTC (00:00 next day)."""
    d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return d


def run_oos(strategy_name: str, pairs: list[str],
            timeframe: str, days: int,
            end_date: str, config_path: str):
    load_config(config_path)
    end_dt = parse_date(end_date)
    print(f"[OOS] Strategy:     {strategy_name}")
    print(f"[OOS] Pairs:        {pairs}")
    print(f"[OOS] Timeframe:    {timeframe}  ({days} days)")
    print(f"[OOS] End date:     {end_dt.date()}")
    start_dt = end_dt.replace(hour=0, minute=0, second=0) - \
        __import__("datetime").timedelta(days=days)
    print(f"[OOS] Actual range: {start_dt.date()} → {end_dt.date()}\n")

    strategy_cls = registry.get_strategy_class(strategy_name)
    results = []
    t0 = time.time()

    for i, pair in enumerate(pairs, 1):
        try:
            df_raw = load_or_fetch(
                pair, timeframe, days,
                force_download=False,
                end_dt_utc=end_dt,
                tag="oos",
            )
            # Trim any candles after end_dt (defensive)
            df_raw = df_raw[df_raw["time"] <= end_dt].reset_index(drop=True)
            df = prepare_dataframe(df_raw)
            strat = strategy_cls()
            result = run(df, strat)
            s = result.summary

            if not s:
                row = {"pair": pair, "tf": timeframe, "trades": 0,
                       "strategy_return": 0.0, "note": "no trades"}
            else:
                row = {
                    "pair": pair,
                    "tf": timeframe,
                    "trades": s["total_trades"],
                    "win_rate": round(s["win_rate"], 1),
                    "strategy_pnl": round(s["total_pnl"], 2),
                    "strategy_return": round(s["strategy_return"], 2),
                    "max_dd": round(s["max_drawdown"], 2),
                    "rr": round(s["rr_ratio"], 2),
                    "sl": s["sl_exits"],
                    "time": s["time_exits"],
                }
            results.append(row)

            status = (f"trades={row.get('trades', 0):3d}  "
                      f"ret={row.get('strategy_return', 0):+6.2f}%  "
                      f"dd={row.get('max_dd', 0):+6.2f}%  "
                      f"rr={row.get('rr', 0):.2f}")
            print(f"  [{i}/{len(pairs)}] {pair:10s}  {status}")

        except Exception as e:
            print(f"  [{i}/{len(pairs)}] {pair:10s}  ERROR: {e}")
            results.append({"pair": pair, "tf": timeframe,
                            "strategy_return": None, "note": str(e)})

    elapsed = time.time() - t0
    df_res = pd.DataFrame(results)
    out_file = f"oos_{strategy_name}.csv"
    df_res.to_csv(out_file, index=False)

    print(f"\n[OOS] Done in {elapsed:.0f}s. Results saved to {out_file}")
    valid = df_res[df_res["strategy_return"].notna()]
    if len(valid) == 0:
        print("[OOS] No valid results.")
        return

    print()
    print("=" * 90)
    print(f"  OUT-OF-SAMPLE RESULTS — {strategy_name} ({end_date})")
    print("=" * 90)
    print(valid.sort_values("strategy_return", ascending=False)
              .to_string(index=False))
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
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--end-date", default="2026-03-31",
                    help="YYYY-MM-DD UTC (default 2026-03-31)")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    pairs = [p.strip() for p in args.pairs.split(",")]
    config_path = args.config or f"config/{args.strategy}.yaml"

    run_oos(args.strategy, pairs, args.timeframe,
            args.days, args.end_date, config_path)


if __name__ == "__main__":
    main()