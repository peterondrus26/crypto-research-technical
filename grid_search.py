"""
grid_search.py — Try many parameter combinations on the same data.
"""

import itertools
import pandas as pd

from backtest import run_backtest, summarize


def grid_search(csv_path: str):
    df = pd.read_csv(csv_path, parse_dates=["time"])

    # Parameter grid
    rsi_long_mins = [30, 35, 40, 45]
    rsi_long_maxs = [55, 60, 65, 70]
    tp_options = [2.0, 3.0, 4.0]
    sl_options = [1.0, 1.5, 2.0]
    atr_pcts = [55, 65, 75]
    direction_opts = ["both", "long", "short"]

    results = []
    combos = list(
        itertools.product(
            rsi_long_mins,
            rsi_long_maxs,
            tp_options,
            sl_options,
            atr_pcts,
            direction_opts,
        )
    )
    print(f"Testing {len(combos)} combinations...\n")

    for i, (rmin, rmax, tp, sl, pct, direction) in enumerate(combos, 1):
        if rmin >= rmax:
            continue

        # Monkey-patch config at runtime
        import config

        config.RSI_LONG_MIN = rmin
        config.RSI_LONG_MAX = rmax
        config.RSI_SHORT_MIN = 100 - rmax
        config.RSI_SHORT_MAX = 100 - rmin
        config.ENABLE_SHORTS = direction in ("both", "short")
        # For longs-only, keep shorts disabled
        if direction == "long":
            config.ENABLE_SHORTS = False

        try:
            result = run_backtest(df, atr_tp=tp, atr_sl=sl, atr_pct=pct)
            s = summarize(result)
            if not s:
                continue
            results.append(
                {
                    "rsi_lo": rmin,
                    "rsi_hi": rmax,
                    "tp": tp,
                    "sl": sl,
                    "atr_pct": pct,
                    "dir": direction,
                    "trades": s["total_trades"],
                    "win_rate": round(s["win_rate"], 1),
                    "return_pct": round(s["total_return"], 2),
                    "max_dd": round(s["max_drawdown"], 2),
                    "rr": round(s.get("rr_ratio", 0), 2) if "rr_ratio" in s else 0,
                }
            )
        except Exception as e:
            continue

        if i % 50 == 0:
            print(f"  {i}/{len(combos)} done...")

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("return_pct", ascending=False)
    results_df.to_csv("grid_results.csv", index=False)

    print("\n=== TOP 20 BY RETURN ===")
    print(results_df.head(20).to_string(index=False))

    print("\n=== BEST PER DIRECTION ===")
    for d in ["long", "short", "both"]:
        sub = results_df[results_df["dir"] == d]
        if len(sub):
            best = sub.iloc[0]
            print(
                f"  {d:5s}: ret={best['return_pct']:+.2f}%  "
                f"WR={best['win_rate']:.1f}%  trades={best['trades']}  "
                f"RSI={best['rsi_lo']}-{best['rsi_hi']} TP={best['tp']} SL={best['sl']}"
            )

    return results_df


if __name__ == "__main__":
    grid_search("data/solusdt_5m_30d.csv")
