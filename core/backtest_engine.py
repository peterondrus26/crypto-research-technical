"""
core/backtest_engine.py — Run one strategy over one dataset.

This is the low-level engine. It knows nothing about pairs, timeframes,
or config files. Caller supplies an enriched DataFrame and a strategy.
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

import config
from indicators import enrich


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity_time: list
    equity_value: list
    final_state: dict
    summary: dict = field(default_factory=dict)


# ----------------------------------------------------------------------
# State & entry/exit mechanics (same as old backtest.py)
# ----------------------------------------------------------------------
def _make_initial_state(price: float) -> dict:
    usd_spend = config.START_BALANCE * config.INITIAL_ASSET_ALLOCATION
    fee = usd_spend * config.TRADING_FEE
    qty = (usd_spend - fee) / price
    return {
        "base_usd":      config.START_BALANCE - usd_spend,
        "base_asset":    qty,
        "usd":           config.START_BALANCE - usd_spend,
        "asset":         qty,
        "entry":         None,
        "tp":            None,
        "sl":            None,
        "cooldown":      0,
        "position_type": None,
        "position_size": 0.0,
        "bars_in_trade": 0,
        "last_entry":    None,
    }


def _open_long(state, price, tp, sl):
    size = state["usd"] * 0.95
    fee = size * config.TRADING_FEE
    qty = (size - fee) / price
    state["usd"] -= size
    state["asset"] += qty
    state["entry"] = price
    state["tp"] = tp
    state["sl"] = sl
    state["position_type"] = "LONG"
    state["position_size"] = qty
    state["bars_in_trade"] = 0


def _open_short(state, price, tp, sl):
    qty = state["asset"] * 0.50
    gross = qty * price
    fee = gross * config.TRADING_FEE
    net = gross - fee
    state["asset"] -= qty
    state["usd"] += net
    state["entry"] = price
    state["tp"] = tp
    state["sl"] = sl
    state["position_type"] = "SHORT"
    state["position_size"] = qty
    state["bars_in_trade"] = 0


def _close(state, price, reason, trades, ts, bars):
    if state["position_type"] == "LONG":
        qty = state["position_size"]
        gross = qty * price
        fee = gross * config.TRADING_FEE
        net = gross - fee
        cost = qty * state["entry"]
        pnl = net - cost
        entry_px = state["entry"]
        state["asset"] -= qty
        state["usd"] += net
    else:  # SHORT
        qty = state["position_size"]
        cost = qty * price
        fee = cost * config.TRADING_FEE
        total_cost = cost + fee
        proceeds = qty * state["entry"]
        pnl = proceeds - total_cost
        entry_px = state["entry"]
        state["usd"] -= total_cost
        state["asset"] += qty

    trades.append({
        "timestamp": ts,
        "type": state["position_type"],
        "pnl": pnl,
        "exit_reason": reason,
        "bars_held": bars,
        "entry": entry_px,
        "exit": price,
    })
    state["position_type"] = None
    state["entry"] = None
    state["cooldown"] = 3
    state["bars_in_trade"] = 0


# ----------------------------------------------------------------------
def run(df: pd.DataFrame, strategy) -> BacktestResult:
    """
    df must already be enriched with indicator columns.
    strategy is a StrategyBase instance.
    """
    if len(df) < 30:
        raise ValueError("Not enough candles.")

    state = _make_initial_state(df.iloc[0]["close"])
    trades = []
    eq_times = []
    eq_vals = []

    for i in range(len(df)):
        row = df.iloc[i]
        price = float(row["close"])
        ts = row["time"]

        if state["position_type"] is not None:
            state["bars_in_trade"] += 1

        # ATR percentile (rolling)
        lookback = config.ATR_LOOKBACK_PERIODS
        atr_window = df["atr"].iloc[max(0, i - lookback):i]
        if len(atr_window.dropna()) >= 10:
            atr_thr = float(atr_window.quantile(
                config.ATR_PERCENTILE_THRESHOLD / 100.0))
        else:
            atr_thr = float(row["atr"])
        atr_expanding = bool(row["atr"] > atr_thr)

        context = {"atr_expanding": atr_expanding, "atr_threshold": atr_thr}

        strategy.pre_bar(state, row, context)

        # Entry
        if state["position_type"] is None:
            d = strategy.check_entry(state, row, context)
            if d.action == "OPEN_LONG":
                state["last_entry"] = price
                if strategy.uses_runner_tp_sl:
                    tp, sl = strategy.get_entry_levels(
                        price, float(row["atr"]), row)
                else:
                    sl_mult = strategy.params.get("sl_atr_mult", 2.0)
                    tp, sl = None, price - float(row["atr"]) * sl_mult
                _open_long(state, price, tp, sl)
            elif d.action == "OPEN_SHORT":
                state["last_entry"] = price
                if strategy.uses_runner_tp_sl:
                    tp, sl = strategy.get_entry_levels(
                        price, float(row["atr"]), row)
                    tp = price - (tp - price)
                    sl = price + (price - sl)
                else:
                    sl_mult = strategy.params.get("sl_atr_mult", 2.0)
                    tp, sl = None, price + float(row["atr"]) * sl_mult
                _open_short(state, price, tp, sl)

        # Exit
        if state["position_type"] is not None:
            d = strategy.check_exit(state, row, price, context)
            if d.action == "CLOSE":
                _close(state, price, d.reason, trades, ts,
                       state["bars_in_trade"])

        if state["cooldown"] > 0:
            state["cooldown"] -= 1

        eq_times.append(ts)
        eq_vals.append(state["usd"] + state["asset"] * price)

    result = BacktestResult(
        trades=pd.DataFrame(trades),
        equity_time=eq_times,
        equity_value=eq_vals,
        final_state=state,
    )
    result.summary = summarize(result)
    return result


# ----------------------------------------------------------------------
def summarize(result: BacktestResult) -> dict:
    t = result.trades
    eq = result.equity_value
    if len(t) == 0:
        return {}

    wins = t[t["pnl"] > 0]
    losses = t[t["pnl"] <= 0]
    final_val = eq[-1]

    eq_s = pd.Series(eq)
    run_max = eq_s.cummax()
    dd = ((eq_s - run_max) / run_max * 100).min()

    avg_w = wins["pnl"].mean() if len(wins) else 0.0
    avg_l = losses["pnl"].mean() if len(losses) else 0.0
    rr = abs(avg_w / avg_l) if avg_l else 0.0

    return {
        "total_trades": len(t),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(t) * 100,
        "total_pnl": t["pnl"].sum(),
        "final_equity": final_val,
        "total_return": (final_val - config.START_BALANCE)
                        / config.START_BALANCE * 100,
        "avg_win": avg_w,
        "avg_loss": avg_l,
        "rr_ratio": rr,
        "best_trade": t["pnl"].max(),
        "worst_trade": t["pnl"].min(),
        "max_drawdown": dd,
        "longs": len(t[t["type"] == "LONG"]),
        "shorts": len(t[t["type"] == "SHORT"]),
        "tp_exits": len(t[t["exit_reason"] == "TP"]),
        "sl_exits": len(t[t["exit_reason"] == "SL"]),
        "rsi_exits": len(t[t["exit_reason"] == "RSI"]),
        "time_exits": len(t[t["exit_reason"] == "TIME"]),
    }


def prepare_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Enrich and clean a raw OHLCV dataframe."""
    df = enrich(df_raw, config.EMA_FAST, config.EMA_SLOW, config.EMA_TREND)
    df = df.dropna(subset=["ema_trend", "rsi", "atr"]).reset_index(drop=True)
    return df