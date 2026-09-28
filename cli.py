"""
cli.py — Single entry point for the trading bot.

Usage:
    python cli.py run --pair SOL/USDT --strategy meanrev --timeframe 5m
    python cli.py run --pair SOL/USDT --strategy rsi_ema --timeframe 5m --days 30
"""

import argparse
import sys
import os

import pandas as pd

import config
from config_loader import load_config
import registry
from core.data_loader import load_or_fetch, data_path
from core.backtest_engine import run, prepare_dataframe, summarize
from core.backtest_engine import BacktestResult


def cmd_run(args):
    # Load config for the strategy
    cfg_path = args.config or f"config/{args.strategy}.yaml"
    if not os.path.exists(cfg_path):
        print(f"[ERROR] Config file not found: {cfg_path}")
        print(f"        Create config/{args.strategy}.yaml first.")
        sys.exit(1)

    load_config(cfg_path)
    strategy = registry.build_strategy(args.strategy)
    print(f"[INFO] Strategy: {strategy}")

    # Load data
    df_raw = load_or_fetch(
        args.pair, args.timeframe, args.days, force_download=args.force_download
    )

    # Prepare
    df = prepare_dataframe(df_raw)
    print(f"[INFO] Prepared {len(df)} bars after indicator warmup")

    # Run
    result = run(df, strategy)
    s = result.summary

    if not s:
        print("No trades.")
        return

    print()
    print("=" * 70)
    print(f"  RESULT — {args.strategy} on {args.pair} {args.timeframe}")
    print("=" * 70)
    print(
        f"  Trades:         {s['total_trades']}  " f"(L:{s['longs']} S:{s['shorts']})"
    )
    print(
        f"  Win rate:       {s['win_rate']:.1f}%  " f"({s['wins']}W / {s['losses']}L)"
    )
    print(f"  Total PnL:      ${s['total_pnl']:.2f}")
    print(f"  Equity Return:  {s['total_return']:+.2f}%   " f"(includes market drift)")
    print(f"  Strategy Return:{s['strategy_return']:+.2f}%   " f"(trading edge only)")
    print(f"  Max Drawdown:   {s['max_drawdown']:.2f}%")
    print(f"  R:R Ratio:      {s['rr_ratio']:.2f}")
    print(
        f"  Exits:          TP:{s['tp_exits']}  SL:{s['sl_exits']}  "
        f"RSI:{s['rsi_exits']}  TIME:{s['time_exits']}"
    )
    print("=" * 70)

    # Optional: save trades
    if args.save_trades:
        result.trades.to_csv(args.save_trades, index=False)
        print(f"[OK] Trades saved to {args.save_trades}")


def build_parser():
    p = argparse.ArgumentParser(prog="cli.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run a backtest")
    run_p.add_argument("--pair", required=True, help="e.g. SOL/USDT")
    run_p.add_argument(
        "--strategy", required=True, help=f"One of: {registry.list_strategies()}"
    )
    run_p.add_argument(
        "--timeframe", default="5m", help="1m, 5m, 15m, 1h, 4h (default 5m)"
    )
    run_p.add_argument("--days", type=int, default=30)
    run_p.add_argument("--config", default=None)
    run_p.add_argument("--force-download", action="store_true")
    run_p.add_argument("--save-trades", default=None)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
