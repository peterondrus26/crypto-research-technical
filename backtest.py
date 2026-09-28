"""
backtest.py — Historical simulation of a pluggable strategy.

Usage:
    python backtest.py                            # uses config/rsi_ema.yaml
    python backtest.py --config config/meanrev.yaml
    python backtest.py --config my.yaml --set rsi_lo=25 --set tp_mult=2.5
"""
import argparse
import os
from datetime import datetime, timezone

import pandas as pd

import config
from config_loader import load_config, get_strategy_params
import registry
from indicators import enrich, atr_percentile_threshold


# ----------------------------------------------------------------------
def make_initial_state(price: float) -> dict:
    usd_to_spend = config.START_BALANCE * config.INITIAL_ASSET_ALLOCATION
    buy_fee = usd_to_spend * config.TRADING_FEE
    asset_bought = (usd_to_spend - buy_fee) / price
    return {
        "base_usd":          config.START_BALANCE - usd_to_spend,
        "base_asset":        asset_bought,
        "usd":               config.START_BALANCE - usd_to_spend,
        "asset":             asset_bought,
        "entry":             None,
        "tp":                None,
        "sl":                None,
        "cooldown":          0,
        "position_type":     None,
        "position_size":     0.0,
        "bars_in_trade":     0,
        "last_entry":        None,
    }


# ----------------------------------------------------------------------
def _open_long(state, price, atr, tp_mult, sl_mult):
    size = state["usd"] * 0.95
    fee = size * config.TRADING_FEE
    qty = (size - fee) / price
    state["usd"] -= size
    state["asset"] += qty
    state["entry"] = price
    state["tp"] = price + atr * tp_mult
    state["sl"] = price - atr * sl_mult
    state["position_type"] = "LONG"
    state["position_size"] = qty
    state["bars_in_trade"] = 0


def _open_short(state, price, atr, tp_mult, sl_mult):
    qty = state["asset"] * 0.50
    gross = qty * price
    fee = gross * config.TRADING_FEE
    net = gross - fee
    state["asset"] -= qty
    state["usd"] += net
    state["entry"] = price
    state["tp"] = price - atr * tp_mult
    state["sl"] = price + atr * sl_mult
    state["position_type"] = "SHORT"
    state["position_size"] = qty
    state["bars_in_trade"] = 0


def _close_long(state, price, reason, trades, timestamp, bars):
    qty = state["position_size"]
    gross = qty * price
    fee = gross * config.TRADING_FEE
    net = gross - fee
    cost = qty * state["entry"]
    pnl = net - cost

    entry_px = state["entry"]
    state["asset"] -= qty
    state["usd"] += net
    state["position_type"] = None
    state["entry"] = None
    state["cooldown"] = 3
    state["bars_in_trade"] = 0

    trades.append({
        "timestamp": timestamp, "type": "LONG",
        "pnl": pnl, "exit_reason": reason, "bars_held": bars,
        "entry": entry_px, "exit": price,
    })


def _close_short(state, price, reason, trades, timestamp, bars):
    qty = state["position_size"]
    cost = qty * price
    fee = cost * config.TRADING_FEE
    total_cost = cost + fee
    proceeds = qty * state["entry"]
    pnl = proceeds - total_cost

    entry_px = state["entry"]
    state["usd"] -= total_cost
    state["asset"] += qty
    state["position_type"] = None
    state["entry"] = None
    state["cooldown"] = 3
    state["bars_in_trade"] = 0

    trades.append({
        "timestamp": timestamp, "type": "SHORT",
        "pnl": pnl, "exit_reason": reason, "bars_held": bars,
        "entry": entry_px, "exit": price,
    })


# ----------------------------------------------------------------------
def run_backtest(df: pd.DataFrame, strategy) -> dict:
    """
    Run a strategy (StrategyBase instance) over a DataFrame.
    Returns dict with trades, equity curve, final state, enriched df.
    """
    if len(df) < config.EMA_TREND + config.ATR_LOOKBACK_PERIODS:
        raise ValueError("Not enough candles for indicators.")

    df = enrich(df, config.EMA_FAST, config.EMA_SLOW, config.EMA_TREND)
    df = df.dropna(subset=["ema_trend", "rsi", "atr"]).reset_index(drop=True)

    state = make_initial_state(df.iloc[0]["close"])
    trades = []
    equity_times = []
    equity_vals = []

    for i in range(len(df)):
        row = df.iloc[i]
        price = float(row["close"])
        ts = row["time"]

        if state["position_type"] is not None:
            state["bars_in_trade"] += 1

        # Rolling ATR percentile
        atr_window = df["atr"].iloc[max(0, i - config.ATR_LOOKBACK_PERIODS):i]
        if len(atr_window.dropna()) >= 10:
            atr_thr = float(atr_window.quantile(
                config.ATR_PERCENTILE_THRESHOLD / 100.0))
        else:
            atr_thr = float(row["atr"])
        atr_expanding = bool(row["atr"] > atr_thr)

        context = {
            "atr_expanding": atr_expanding,
            "atr_threshold": atr_thr,
        }

        # Strategy hooks
        strategy.pre_bar(state, row, context)

        # Try entry
        if state["position_type"] is None:
            d = strategy.check_entry(state, row, context)
            if d.action == "OPEN_LONG":
                state["last_entry"] = price
                _open_long(state, price, float(row["atr"]),
                           strategy.params.get("tp_mult", config.ATR_TP),
                           strategy.params.get("sl_mult", config.ATR_SL))
            elif d.action == "OPEN_SHORT":
                state["last_entry"] = price
                _open_short(state, price, float(row["atr"]),
                            strategy.params.get("tp_mult", config.ATR_TP),
                            strategy.params.get("sl_mult", config.ATR_SL))

        # Try exit
        if state["position_type"] is not None:
            d = strategy.check_exit(state, row, price, context)
            if d.action == "CLOSE":
                if state["position_type"] == "LONG":
                    _close_long(state, price, d.reason, trades, ts,
                                state["bars_in_trade"])
                else:
                    _close_short(state, price, d.reason, trades, ts,
                                 state["bars_in_trade"])

        if state["cooldown"] > 0:
            state["cooldown"] -= 1

        equity_times.append(ts)
        equity_vals.append(state["usd"] + state["asset"] * price)

    return {
        "trades": pd.DataFrame(trades),
        "equity_time": equity_times,
        "equity_value": equity_vals,
        "final_state": state,
        "df": df,
    }


# ----------------------------------------------------------------------
def summarize(result: dict) -> dict:
    trades = result["trades"]
    eq = result["equity_value"]

    if len(trades) == 0:
        return {}

    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] <= 0]

    final_val = eq[-1]
    total_ret = (final_val - config.START_BALANCE) / config.START_BALANCE * 100

    eq_series = pd.Series(eq)
    running_max = eq_series.cummax()
    drawdown_pct = ((eq_series - running_max) / running_max * 100).min()

    avg_win = wins["pnl"].mean() if len(wins) else 0
    avg_loss = losses["pnl"].mean() if len(losses) else 0
    rr = abs(avg_win / avg_loss) if avg_loss else 0

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100,
        "total_pnl": trades["pnl"].sum(),
        "final_equity": final_val,
        "total_return": total_ret,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "rr_ratio": rr,
        "best_trade": trades["pnl"].max(),
        "worst_trade": trades["pnl"].min(),
        "max_drawdown": drawdown_pct,
        "longs": len(trades[trades["type"] == "LONG"]),
        "shorts": len(trades[trades["type"] == "SHORT"]),
        "tp_exits": len(trades[trades["exit_reason"] == "TP"]),
        "sl_exits": len(trades[trades["exit_reason"] == "SL"]),
        "rsi_exits": len(trades[trades["exit_reason"] == "RSI"]),
        "time_exits": len(trades[trades["exit_reason"] == "TIME"]),
    }


def print_summary(s: dict, strategy_name: str = ""):
    if not s:
        print("No trades.")
        return
    title = f"  BACKTEST RESULTS  ({strategy_name})" if strategy_name \
        else "  BACKTEST RESULTS"
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    print(f"  Total Trades:        {s['total_trades']}")
    print(f"    Longs:             {s['longs']}")
    print(f"    Shorts:            {s['shorts']}")
    print()
    print(f"  Win Rate:            {s['win_rate']:.1f}%  "
          f"({s['wins']}W / {s['losses']}L)")
    print(f"  Total PnL:           ${s['total_pnl']:.2f}")
    print(f"  Final Equity:        ${s['final_equity']:.2f}")
    print(f"  Total Return:        {s['total_return']:+.2f}%")
    print(f"  Max Drawdown:        {s['max_drawdown']:.2f}%")
    print()
    print(f"  Avg Win:             ${s['avg_win']:.3f}")
    print(f"  Avg Loss:            ${s['avg_loss']:.3f}")
    print(f"  R:R Ratio:           {s['rr_ratio']:.2f}")
    print(f"  Best Trade:          ${s['best_trade']:.3f}")
    print(f"  Worst Trade:         ${s['worst_trade']:.3f}")
    print()
    print(f"  Exit Reasons:")
    print(f"    TP:                {s['tp_exits']}")
    print(f"    SL:                {s['sl_exits']}")
    print(f"    RSI:               {s['rsi_exits']}")
    print(f"    TIME:              {s['time_exits']}")
    print("=" * 70)


# ----------------------------------------------------------------------
def parse_overrides(pairs: list[str]) -> dict:
    """Convert ['k=v', 'k2=v2'] into {'k': 'v', 'k2': 'v2'} with type coercion."""
    out = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--set expects key=value, got: {pair}")
        k, v = pair.split("=", 1)
        # Try numeric, then bool, then string
        if v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        else:
            try:
                out[k] = int(v)
            except ValueError:
                try:
                    out[k] = float(v)
                except ValueError:
                    out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/rsi_ema.yaml")
    ap.add_argument("--data", default=None,
                    help="Override data file path")
    ap.add_argument("--set", action="append", default=[],
                    help="Override a strategy param, e.g. --set rsi_lo=25")
    args = ap.parse_args()

    # Load config
    cfg = load_config(args.config)
    strategy_name, params = get_strategy_params(cfg)

    # CLI overrides
    overrides = parse_overrides(args.set)
    params.update(overrides)

    # Build strategy
    strategy = registry.build_strategy(strategy_name, params)
    print(f"[INFO] Strategy: {strategy}")

    # Data file
    data_path = args.data or getattr(config, "DATA_FILE",
                                     "data/solusdt_5m_30d.csv")
    if not os.path.exists(data_path):
        print(f"[ERROR] Data file not found: {data_path}")
        return

    print(f"[INFO] Loading {data_path}...")
    df = pd.read_csv(data_path, parse_dates=["time"])
    print(f"[INFO] {len(df)} candles, "
          f"{df['time'].iloc[0]} -> {df['time'].iloc[-1]}")

    result = run_backtest(df, strategy)
    s = summarize(result)
    print_summary(s, strategy_name)

    if len(result["trades"]) > 0:
        out = "backtest_trades.csv"
        result["trades"].to_csv(out, index=False)
        print(f"\n[OK] Trade log saved to {out}")


if __name__ == "__main__":
    main()