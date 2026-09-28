"""
split_test.py — In-sample / out-of-sample validation.

Splits the data in half by time, tunes on the first half,
tests the winning combo on the second half.
"""
import pandas as pd

import config
from config_loader import load_config
import registry
from indicators import enrich
from backtest import run_backtest, summarize


def split_and_test(csv_path: str,
                   strategy_name: str,
                   params: dict,
                   config_path: str = None):
    if config_path is None:
        config_path = f"config/{strategy_name}.yaml"
    load_config(config_path)

    df = pd.read_csv(csv_path, parse_dates=["time"])
    df = enrich(df, config.EMA_FAST, config.EMA_SLOW, config.EMA_TREND)
    df = df.dropna(subset=["ema_trend", "rsi", "atr"]).reset_index(drop=True)

    mid = len(df) // 2
    df1 = df.iloc[:mid].reset_index(drop=True)
    df2 = df.iloc[mid:].reset_index(drop=True)

    print(f"[INFO] Split at row {mid}")
    print(f"[INFO] In-sample:  {df1['time'].iloc[0]} -> {df1['time'].iloc[-1]}  ({len(df1)} bars)")
    print(f"[INFO] Out-sample: {df2['time'].iloc[0]} -> {df2['time'].iloc[-1]}  ({len(df2)} bars)")
    print(f"[INFO] Params: {params}")
    print()

    for label, df_part in [("IN-SAMPLE", df1), ("OUT-OF-SAMPLE", df2)]:
        strat = registry.build_strategy(strategy_name, params)
        result = run_backtest(df_part, strat)
        s = summarize(result)
        if not s:
            print(f"--- {label} ---\nNo trades.\n")
            continue
        print(f"--- {label} ---")
        print(f"  Trades:    {s['total_trades']}")
        print(f"  Win rate:  {s['win_rate']:.1f}%")
        print(f"  Return:    {s['total_return']:+.2f}%")
        print(f"  Max DD:    {s['max_drawdown']:.2f}%")
        print(f"  Total PnL: ${s['total_pnl']:.2f}")
        print()


if __name__ == "__main__":
    # Test the top combo from grid search
    winning_params = {
        "z_entry": 3.0,
        "rsi_entry": 25,
        "rsi_exit": 55,
        "max_bars": 18,
        "sl_atr_mult": 2.0,
    }
    split_and_test("data/solusdt_5m_30d.csv", "meanrev", winning_params)