"""
grid_search_v2.py — Grid search over any plug-in strategy.

Usage:
    python grid_search_v2.py meanrev
    python grid_search_v2.py rsi_ema
"""

import itertools
import sys
import time

import pandas as pd

import config
from config_loader import load_config
import registry
from backtest import run_backtest, summarize

# ---- Grid definitions per strategy --------------------------------
GRIDS = {
    "meanrev": {
        "z_entry": [1.5, 2.0, 2.5, 3.0],
        "rsi_entry": [25, 30, 35, 40],
        "rsi_exit": [50, 55, 60],
        "max_bars": [6, 9, 12, 18],
        "sl_atr_mult": [1.0, 1.5, 2.0, 2.5],
    },
    "rsi_ema": {
        "rsi_lo": [30, 35, 40, 45],
        "rsi_hi": [55, 60, 65],
        "tp_mult": [2.0, 3.0, 4.0],
        "sl_mult": [1.0, 1.5, 2.0],
        "max_bars": [12, 18],
        "enable_shorts": [True, False],
    },
}


def combinations(param_grid: dict):
    keys = list(param_grid.keys())
    for values in itertools.product(*(param_grid[k] for k in keys)):
        yield dict(zip(keys, values))


def run_grid(strategy_name: str, data_path: str, config_path: str = None):
    if strategy_name not in GRIDS:
        print(f"[ERROR] No grid defined for strategy '{strategy_name}'.")
        print(f"        Available: {list(GRIDS.keys())}")
        return None

    # Load config to get market/account/etc settings
    if config_path is None:
        config_path = f"config/{strategy_name}.yaml"
    print(f"[INFO] Loading base config: {config_path}")
    load_config(config_path)

    print(f"[INFO] Loading {data_path}...")
    df_full = pd.read_csv(data_path, parse_dates=["time"])
    print(f"[INFO] {len(df_full)} candles\n")

    # Pre-enrich once
    from indicators import enrich

    df = enrich(df_full, config.EMA_FAST, config.EMA_SLOW, config.EMA_TREND)
    df = df.dropna(subset=["ema_trend", "rsi", "atr"]).reset_index(drop=True)

    param_grid = GRIDS[strategy_name]
    combos = list(combinations(param_grid))
    print(f"[INFO] Testing {len(combos)} combinations\n")

    results = []
    t0 = time.time()

    for i, params in enumerate(combos, 1):
        try:
            strat = registry.build_strategy(strategy_name, params)
            result = run_backtest(df, strat)
            s = summarize(result)
            if not s:
                continue

            row = dict(params)
            row.update(
                {
                    "trades": s["total_trades"],
                    "win_rate": round(s["win_rate"], 1),
                    "return_pct": round(s["total_return"], 2),
                    "max_dd": round(s["max_drawdown"], 2),
                    "total_pnl": round(s["total_pnl"], 2),
                    "avg_win": round(s["avg_win"], 3),
                    "avg_loss": round(s["avg_loss"], 3),
                    "rr": round(s["rr_ratio"], 2),
                    "tp_exits": s["tp_exits"],
                    "sl_exits": s["sl_exits"],
                    "time_exits": s["time_exits"],
                }
            )
            results.append(row)
        except Exception as e:
            print(f"[WARN] combo {i} failed: {e}")
            continue

        if i % 25 == 0:
            elapsed = time.time() - t0
            eta = (elapsed / i) * (len(combos) - i)
            print(
                f"  [{i:4d}/{len(combos)}] elapsed={elapsed:.0f}s  " f"eta={eta:.0f}s"
            )

    if not results:
        print("[ERROR] No valid results.")
        return None

    df_res = pd.DataFrame(results).sort_values("return_pct", ascending=False)
    df_res.to_csv(f"grid_{strategy_name}.csv", index=False)

    # Dynamic column order
    param_cols = list(param_grid.keys())
    metric_cols = [
        "trades",
        "win_rate",
        "return_pct",
        "max_dd",
        "total_pnl",
        "rr",
        "tp_exits",
        "sl_exits",
        "time_exits",
    ]
    cols = param_cols + metric_cols

    print("\n" + "=" * 110)
    print(f"  TOP 20 — {strategy_name.upper()}")
    print("=" * 110)
    print(df_res[cols].head(20).to_string(index=False))

    print("\n" + "=" * 110)
    print("  STATISTICS")
    print("=" * 110)
    n_pos = (df_res["return_pct"] > 0).sum()
    n_breakeven = ((df_res["return_pct"] > -1) & (df_res["return_pct"] <= 0)).sum()
    print(f"  Total combos:              {len(df_res)}")
    print(f"  Positive return:           {n_pos}")
    print(f"  Breakeven (-1% to 0%):     {n_breakeven}")
    print(f"  Best return:               {df_res['return_pct'].max():+.2f}%")
    print(f"  Median return:             {df_res['return_pct'].median():+.2f}%")
    print(f"  Worst return:              {df_res['return_pct'].min():+.2f}%")

    print(f"\n[OK] Full results saved to grid_{strategy_name}.csv")
    return df_res


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python grid_search_v2.py <strategy_name>")
        print(f"       Available: {list(GRIDS.keys())}")
        sys.exit(1)

    strategy = sys.argv[1]
    data = sys.argv[2] if len(sys.argv) > 2 else "data/solusdt_5m_30d.csv"
    run_grid(strategy, data)
