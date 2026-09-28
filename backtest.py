"""
backtest.py — Historical simulation of the strategy.

Imports the SAME strategy.py functions the live bot uses,
so backtest and live behavior are guaranteed identical.

Usage:
    python backtest.py                       # use config.py defaults
    python backtest.py path/to/data.csv      # custom CSV
"""
import os
import sys
from datetime import datetime, timezone

import pandas as pd

import config
from config import (
    PAIR, TRADING_FEE, START_BALANCE, INITIAL_ASSET_ALLOCATION,
    ATR_LOOKBACK_PERIODS, MAX_BARS_IN_TRADE, COOLDOWN_BARS,
    EMA_FAST, EMA_SLOW, EMA_TREND,
)
from indicators import enrich, atr_percentile_threshold
from strategy import (
    is_regime_allowed, check_open_long, check_open_short,
    check_close_long, check_close_short,
)


# ----------------------------------------------------------------------
# State setup
# ----------------------------------------------------------------------
def make_initial_state(price: float) -> dict:
    """Replicate the live bot's initial holdings (40% SOL / 60% USD)."""
    usd_to_spend = START_BALANCE * INITIAL_ASSET_ALLOCATION
    buy_fee      = usd_to_spend * TRADING_FEE
    asset_bought = (usd_to_spend - buy_fee) / price

    return {
        "base_usd":          START_BALANCE - usd_to_spend,
        "base_asset":        asset_bought,
        "usd":               START_BALANCE - usd_to_spend,
        "asset":             asset_bought,
        "entry":             None,
        "tp":                None,
        "sl":                None,
        "cooldown":          0,
        "position_type":     None,
        "position_size":     0.0,
        "bars_in_trade":     0,
    }


# ----------------------------------------------------------------------
# Actions (mirror live_bot.py exactly)
# ----------------------------------------------------------------------
def _open_long(state, price, atr, tp_mult, sl_mult):
    size = state["usd"] * 0.95
    fee  = size * TRADING_FEE
    qty  = (size - fee) / price

    state["usd"]          -= size
    state["asset"]        += qty
    state["entry"]         = price
    state["tp"]            = price + atr * tp_mult
    state["sl"]            = price - atr * sl_mult
    state["position_type"] = "LONG"
    state["position_size"] = qty
    state["bars_in_trade"] = 0


def _open_short(state, price, atr, tp_mult, sl_mult):
    qty   = state["asset"] * 0.50
    gross = qty * price
    fee   = gross * TRADING_FEE
    net   = gross - fee

    state["asset"]        -= qty
    state["usd"]          += net
    state["entry"]         = price
    state["tp"]            = price - atr * tp_mult
    state["sl"]            = price + atr * sl_mult
    state["position_type"] = "SHORT"
    state["position_size"] = qty
    state["bars_in_trade"] = 0


def _close_long(state, price, reason, trades, timestamp, bars):
    qty   = state["position_size"]
    gross = qty * price
    fee   = gross * TRADING_FEE
    net   = gross - fee
    cost  = qty * state["entry"]
    pnl   = net - cost

    state["asset"]         -= qty
    state["usd"]           += net
    state["position_type"]  = None
    state["entry"]          = None
    state["cooldown"]       = COOLDOWN_BARS
    state["bars_in_trade"]  = 0

    trades.append({
        "timestamp": timestamp, "type": "LONG",
        "pnl": pnl, "exit_reason": reason, "bars_held": bars,
        "entry": state.get("last_entry", price), "exit": price,
    })


def _close_short(state, price, reason, trades, timestamp, bars):
    qty        = state["position_size"]
    cost       = qty * price
    fee        = cost * TRADING_FEE
    total_cost = cost + fee
    proceeds   = qty * state["entry"]
    pnl        = proceeds - total_cost

    state["usd"]           -= total_cost
    state["asset"]         += qty
    state["position_type"]  = None
    state["entry"]          = None
    state["cooldown"]       = COOLDOWN_BARS
    state["bars_in_trade"]  = 0

    trades.append({
        "timestamp": timestamp, "type": "SHORT",
        "pnl": pnl, "exit_reason": reason, "bars_held": bars,
        "entry": state.get("last_entry", price), "exit": price,
    })


# ----------------------------------------------------------------------
# Main backtest loop
# ----------------------------------------------------------------------
def run_backtest(df: pd.DataFrame,
                 atr_tp: float = None,
                 atr_sl: float = None,
                 atr_pct: int = None,
                 verbose: bool = False) -> dict:
    if atr_tp is None:
        atr_tp = config.ATR_TP
    if atr_sl is None:
        atr_sl = config.ATR_SL
    if atr_pct is None:
        atr_pct = config.ATR_PERCENTILE_THRESHOLD
    """
    Run the strategy over the given dataframe.
    Returns dict with trades, equity curve, and summary metrics.
    """
    if len(df) < EMA_TREND + ATR_LOOKBACK_PERIODS:
        raise ValueError(
            f"Not enough candles ({len(df)}); need at least "
            f"{EMA_TREND + ATR_LOOKBACK_PERIODS}."
        )

    df = enrich(df, EMA_FAST, EMA_SLOW, EMA_TREND)
    df = df.dropna(subset=["ema_trend", "rsi", "atr"]).reset_index(drop=True)

    state  = make_initial_state(df.iloc[0]["close"])
    trades = []

    equity_times = []
    equity_vals  = []

    for i in range(len(df)):
        row   = df.iloc[i]
        price = float(row["close"])
        ts    = row["time"]

        # Track position duration
        if state["position_type"] is not None:
            state["bars_in_trade"] += 1

        # Rolling ATR threshold using data up to (not including) current bar
        atr_window = df["atr"].iloc[max(0, i - ATR_LOOKBACK_PERIODS):i]
        if len(atr_window.dropna()) >= 10:
            atr_thr = float(atr_window.quantile(atr_pct / 100.0))
        else:
            atr_thr = float(row["atr"])

        atr_expanding = bool(row["atr"] > atr_thr)
        allow_longs, allow_shorts = is_regime_allowed(row)

        # ---- Try to OPEN ----
        d = check_open_long(state, row, allow_longs, atr_expanding)
        if d.action == "OPEN_LONG":
            state["last_entry"] = price
            _open_long(state, price, float(row["atr"]), atr_tp, atr_sl)
        else:
            d = check_open_short(state, row, allow_shorts, atr_expanding)
            if d.action == "OPEN_SHORT":
                state["last_entry"] = price
                _open_short(state, price, float(row["atr"]), atr_tp, atr_sl)
            else:
                # ---- Try to CLOSE ----
                if state["position_type"] == "LONG":
                    d = check_close_long(state, row, price)
                    if d.action == "CLOSE":
                        _close_long(state, price, d.reason, trades,
                                    ts, state["bars_in_trade"])
                elif state["position_type"] == "SHORT":
                    d = check_close_short(state, row, price)
                    if d.action == "CLOSE":
                        _close_short(state, price, d.reason, trades,
                                     ts, state["bars_in_trade"])

        # Cooldown
        if state["cooldown"] > 0:
            state["cooldown"] -= 1

        # Track equity
        equity_times.append(ts)
        equity_vals.append(state["usd"] + state["asset"] * price)

    return {
        "trades":       pd.DataFrame(trades),
        "equity_time":  equity_times,
        "equity_value": equity_vals,
        "final_state":  state,
        "df":           df,
    }


# ----------------------------------------------------------------------
# Summary output
# ----------------------------------------------------------------------
def summarize(result: dict) -> dict:
    trades = result["trades"]
    eq     = result["equity_value"]

    if len(trades) == 0:
        print("No trades were taken.")
        return {}

    wins   = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] <= 0]

    final_val   = eq[-1]
    total_ret   = (final_val - START_BALANCE) / START_BALANCE * 100

    # Max drawdown
    eq_series    = pd.Series(eq)
    running_max  = eq_series.cummax()
    drawdown_pct = ((eq_series - running_max) / running_max * 100).min()

    summary = {
        "total_trades":  len(trades),
        "wins":          len(wins),
        "losses":        len(losses),
        "win_rate":      len(wins) / len(trades) * 100,
        "total_pnl":     trades["pnl"].sum(),
        "final_equity":  final_val,
        "total_return":  total_ret,
        "avg_win":       wins["pnl"].mean()   if len(wins)   else 0,
        "avg_loss":      losses["pnl"].mean() if len(losses) else 0,
        "best_trade":    trades["pnl"].max(),
        "worst_trade":   trades["pnl"].min(),
        "max_drawdown":  drawdown_pct,
        "longs":         len(trades[trades["type"] == "LONG"]),
        "shorts":        len(trades[trades["type"] == "SHORT"]),
        "tp_exits":      len(trades[trades["exit_reason"] == "TP"]),
        "sl_exits":      len(trades[trades["exit_reason"] == "SL"]),
        "rsi_exits":     len(trades[trades["exit_reason"] == "RSI"]),
        "time_exits":    len(trades[trades["exit_reason"] == "TIME"]),
    }
    return summary


def print_summary(s: dict):
    if not s:
        return
    print()
    print("=" * 70)
    print("  BACKTEST RESULTS")
    print("=" * 70)
    print(f"  Total Trades:        {s['total_trades']}")
    print(f"    Longs:             {s['longs']}")
    print(f"    Shorts:            {s['shorts']}")
    print()
    print(f"  Win Rate:            {s['win_rate']:.1f}%  ({s['wins']}W / {s['losses']}L)")
    print(f"  Total PnL:           ${s['total_pnl']:.2f}")
    print(f"  Final Equity:        ${s['final_equity']:.2f}")
    print(f"  Total Return:        {s['total_return']:+.2f}%")
    print(f"  Max Drawdown:        {s['max_drawdown']:.2f}%")
    print()
    print(f"  Avg Win:             ${s['avg_win']:.3f}")
    print(f"  Avg Loss:            ${s['avg_loss']:.3f}")
    if s['avg_loss'] != 0:
        print(f"  R:R Ratio:           {abs(s['avg_win'] / s['avg_loss']):.2f}")
    print(f"  Best Trade:          ${s['best_trade']:.3f}")
    print(f"  Worst Trade:         ${s['worst_trade']:.3f}")
    print()
    print(f"  Exit Reasons:")
    print(f"    TP:                {s['tp_exits']}")
    print(f"    SL:                {s['sl_exits']}")
    print(f"    RSI:               {s['rsi_exits']}")
    print(f"    TIME:              {s['time_exits']}")
    print("=" * 70)


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/solusdt_5m_30d.csv"
    if not os.path.exists(csv_path):
        print(f"[ERROR] Data file not found: {csv_path}")
        sys.exit(1)

    print(f"[INFO] Loading {csv_path}...")
    df = pd.read_csv(csv_path, parse_dates=["time"])
    print(f"[INFO] {len(df)} candles, "
          f"{df['time'].iloc[0]} -> {df['time'].iloc[-1]}")

    print(f"[INFO] Params: TP={config.ATR_TP}x, SL={config.ATR_SL}x, "
          f"ATR%={config.ATR_PERCENTILE_THRESHOLD}, "
          f"Longs+Shorts={config.ENABLE_SHORTS}, "
          f"Regime={config.ENABLE_REGIME_FILTER}")
    print("[INFO] Running backtest...")

    result = run_backtest(df)
    s = summarize(result)
    print_summary(s)

    if len(result["trades"]) > 0:
        out = "backtest_trades.csv"
        result["trades"].to_csv(out, index=False)
        print(f"\n[OK] Trade log saved to {out}")


if __name__ == "__main__":
    main()