"""
analyze_trades.py — Quick diagnostic on backtest_trades.csv
"""
import pandas as pd
import sys
import os

path = sys.argv[1] if len(sys.argv) > 1 else "backtest_trades.csv"

if not os.path.exists(path):
    print(f"[ERROR] File not found: {path}")
    sys.exit(1)

df = pd.read_csv(path)

print("=" * 60)
print(f"  TRADE ANALYSIS: {path}")
print("=" * 60)
print(f"Total trades: {len(df)}")
print()

# ---- Direction breakdown ----
print("--- DIRECTION BREAKDOWN ---")
for direction in ["LONG", "SHORT"]:
    sub = df[df["type"] == direction]
    if len(sub) == 0:
        continue
    wins = (sub["pnl"] > 0).sum()
    losses = (sub["pnl"] <= 0).sum()
    wr = wins / len(sub) * 100
    total = sub["pnl"].sum()
    avg_w = sub[sub["pnl"] > 0]["pnl"].mean() if wins else 0
    avg_l = sub[sub["pnl"] <= 0]["pnl"].mean() if losses else 0
    print(f"  {direction:5s}: n={len(sub):3d}  "
          f"W/L={wins}/{losses}  WR={wr:5.1f}%  "
          f"Total=${total:+7.2f}  AvgW=${avg_w:+.3f}  AvgL=${avg_l:+.3f}")

print()

# ---- Exit reason breakdown ----
print("--- EXIT REASON BREAKDOWN ---")
for reason in ["TP", "SL", "RSI", "TIME"]:
    sub = df[df["exit_reason"] == reason]
    if len(sub) == 0:
        continue
    wins = (sub["pnl"] > 0).sum()
    wr = wins / len(sub) * 100 if len(sub) else 0
    total = sub["pnl"].sum()
    avg = sub["pnl"].mean()
    print(f"  {reason:5s}: n={len(sub):3d}  "
          f"WR={wr:5.1f}%  Total=${total:+7.2f}  Avg=${avg:+.3f}")

print()

# ---- Best and worst trades ----
print("--- TOP 5 WINNERS ---")
top5 = df.nlargest(5, "pnl")[["timestamp", "type", "pnl", "exit_reason", "bars_held"]]
for _, r in top5.iterrows():
    print(f"  {r['timestamp'][:16]}  {r['type']:5s}  "
          f"${r['pnl']:+.3f}  {r['exit_reason']:4s}  {r['bars_held']}bars")

print()
print("--- TOP 5 LOSERS ---")
bot5 = df.nsmallest(5, "pnl")[["timestamp", "type", "pnl", "exit_reason", "bars_held"]]
for _, r in bot5.iterrows():
    print(f"  {r['timestamp'][:16]}  {r['type']:5s}  "
          f"${r['pnl']:+.3f}  {r['exit_reason']:4s}  {r['bars_held']}bars")

print()

# ---- Bars held vs PnL ----
print("--- BARS HELD vs PnL ---")
df["bar_bucket"] = pd.cut(df["bars_held"], 
                          bins=[0, 3, 8, 14, 18, 100],
                          labels=["1-3", "4-8", "9-14", "15-18", "18+"])
for bucket in ["1-3", "4-8", "9-14", "15-18", "18+"]:
    sub = df[df["bar_bucket"] == bucket]
    if len(sub) == 0:
        continue
    wr = (sub["pnl"] > 0).mean() * 100
    total = sub["pnl"].sum()
    print(f"  {bucket:6s}: n={len(sub):3d}  WR={wr:5.1f}%  Total=${total:+7.2f}")

print()
print("=" * 60)