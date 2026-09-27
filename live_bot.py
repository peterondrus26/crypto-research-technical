"""
live_bot.py — Main trading loop.

Thin orchestration layer: fetch → enrich → decide → execute → log.
All decisions live in strategy.py, all state in state.py.
"""
import os
import time
from datetime import datetime, timezone

from config import (
    PAIR, PERF_LOG, PARAM_LOG, START_BALANCE,
    INITIAL_ASSET_ALLOCATION, TRADING_FEE, DAILY_MAX_TRADES,
    MAX_DAILY_LOSS, MAX_CONSECUTIVE_LOSSES, ATR_LOOKBACK_PERIODS,
    MAX_BARS_IN_TRADE, COOLDOWN_BARS,
    ENABLE_REGIME_FILTER, ENABLE_SHORTS, ENABLE_ADAPTIVE_PARAMS,
    OPTIMIZATION_INTERVAL_HOURS, MIN_TRADES_FOR_OPTIMIZATION,
    EMA_FAST, EMA_SLOW, EMA_TREND,
)
from data       import fetch_ohlcv
from indicators import enrich, atr_percentile_threshold
from state      import load_state, save_state, reset_daily_counters, now
from risk       import check_safety_limits
from strategy   import (
    is_regime_allowed, check_open_long, check_open_short,
    check_close_long, check_close_short,
)
from adaptive   import AdaptiveParameterManager


# ---------------------------------------------------------------
# helpers
# ---------------------------------------------------------------
def init_perf_log() -> None:
    if not os.path.exists(PERF_LOG):
        with open(PERF_LOG, "w") as f:
            f.write("timestamp,pair,position_type,pnl,exit_reason,bars_held\n")


def log_trade(position_type: str, pnl: float,
              exit_reason: str, bars_held: int) -> None:
    with open(PERF_LOG, "a") as f:
        f.write(f"{now().isoformat()},{PAIR},{position_type},"
                f"{pnl:.4f},{exit_reason},{bars_held}\n")


def total_value(state: dict, price: float) -> float:
    return state["usd"] + state["asset"] * price


def _print_banner(param_mgr) -> None:
    print("=" * 80)
    print("  SOL ADAPTIVE BIDIRECTIONAL BOT - Modular Refactor")
    print("=" * 80)
    print(f"[CONFIG]")
    print(f"  Balance: ${START_BALANCE:.2f}")
    print(f"  Allocation: {INITIAL_ASSET_ALLOCATION*100:.0f}% {PAIR}, "
          f"{(1-INITIAL_ASSET_ALLOCATION)*100:.0f}% USD")
    print(f"\n[STRATEGY]")
    print(f"  Directions: LONG + SHORT "
          f"({'both enabled' if ENABLE_SHORTS else 'shorts disabled'})")
    print(f"  ATR TP/SL: {param_mgr.atr_tp if param_mgr else '?'}x / "
          f"{param_mgr.atr_sl if param_mgr else '?'}x")
    print(f"  Time Stop: {MAX_BARS_IN_TRADE} bars (~{MAX_BARS_IN_TRADE*5} min)")
    print(f"\n[REGIME FILTERS]")
    print(f"  Trend Filter (EMA{EMA_TREND}): "
          f"{'ENABLED' if ENABLE_REGIME_FILTER else 'DISABLED'}")
    print(f"\n[SAFETY LIMITS]")
    print(f"  Max Daily Loss: {MAX_DAILY_LOSS}")
    print(f"  Max Consecutive Losses: {MAX_CONSECUTIVE_LOSSES}")
    print(f"  Max Daily Trades: {DAILY_MAX_TRADES}")
    print(f"\n[ADAPTIVE OPTIMIZATION]")
    print(f"  Status: {'ENABLED' if ENABLE_ADAPTIVE_PARAMS else 'DISABLED'}")
    print(f"\n[INFO] Press Ctrl+C to stop")
    print("=" * 80 + "\n")


# ---------------------------------------------------------------
# actions
# ---------------------------------------------------------------
def _initialize_holdings(state: dict, price: float) -> None:
    usd_to_spend = START_BALANCE * INITIAL_ASSET_ALLOCATION
    buy_fee = usd_to_spend * TRADING_FEE
    asset_bought = (usd_to_spend - buy_fee) / price

    state["base_usd"]    = START_BALANCE - usd_to_spend
    state["base_asset"]  = asset_bought
    state["usd"]         = state["base_usd"]
    state["asset"]       = state["base_asset"]
    state["initialized"] = True

    print(f"[INIT] Bought {asset_bought:.4f} {PAIR} @ ${price:.3f} "
          f"(fee: ${buy_fee:.4f})")
    print(f"[INIT] Holdings: ${state['base_usd']:.2f} + "
          f"{state['base_asset']:.4f} {PAIR}\n")


def _open_long(state, price, atr, tp_mult, sl_mult,
               higher_tf_bullish, atr_ratio) -> None:
    size = state["usd"] * 0.95
    fee  = size * TRADING_FEE
    qty  = (size - fee) / price

    state["usd"]            -= size
    state["asset"]          += qty
    state["entry"]           = price
    state["tp"]              = price + atr * tp_mult
    state["sl"]              = price - atr * sl_mult
    state["position_type"]   = "LONG"
    state["position_size"]   = qty
    state["bars_in_trade"]   = 0
    state["daily_trades"]   += 1

    regime = "HTF↑" if higher_tf_bullish else "HTF↓"
    print(f"[LONG] Open {qty:.4f} @ ${price:.2f} | "
          f"TP:${state['tp']:.2f} SL:${state['sl']:.2f} | "
          f"{regime} ATR:{atr_ratio:.2f}x")


def _open_short(state, price, atr, tp_mult, sl_mult,
                higher_tf_bearish, atr_ratio) -> None:
    qty   = state["asset"] * 0.50
    gross = qty * price
    fee   = gross * TRADING_FEE
    net   = gross - fee

    state["asset"]          -= qty
    state["usd"]            += net
    state["entry"]           = price
    state["tp"]              = price - atr * tp_mult
    state["sl"]              = price + atr * sl_mult
    state["position_type"]   = "SHORT"
    state["position_size"]   = qty
    state["bars_in_trade"]   = 0
    state["daily_trades"]   += 1

    regime = "HTF↓" if higher_tf_bearish else "HTF↑"
    print(f"[SHORT] Open {qty:.4f} @ ${price:.2f} | "
          f"TP:${state['tp']:.2f} SL:${state['sl']:.2f} | "
          f"{regime} ATR:{atr_ratio:.2f}x")


def _close_long(state, price, reason) -> None:
    qty   = state["position_size"]
    gross = qty * price
    fee   = gross * TRADING_FEE
    net   = gross - fee
    cost  = qty * state["entry"]
    pnl   = net - cost

    state["asset"]          -= qty
    state["usd"]            += net
    state["position_type"]   = None
    state["entry"]           = None
    state["cooldown"]        = COOLDOWN_BARS
    bars_held                = state["bars_in_trade"]
    state["bars_in_trade"]   = 0
    state["daily_pnl"]      += pnl

    state["consecutive_losses"] = 0 if pnl > 0 else state["consecutive_losses"] + 1

    log_trade("LONG", pnl, reason, bars_held)

    pnl_pct = (pnl / cost) * 100 if cost else 0
    tv = total_value(state, price)
    print(f"[LONG] Close {reason} | PnL:${pnl:.2f} ({pnl_pct:+.1f}%) | "
          f"Held:{bars_held}bars | Total:${tv:.2f}")


def _close_short(state, price, reason) -> None:
    qty       = state["position_size"]
    cost      = qty * price
    fee       = cost * TRADING_FEE
    total_cost= cost + fee
    proceeds  = qty * state["entry"]
    pnl       = proceeds - total_cost

    state["usd"]            -= total_cost
    state["asset"]          += qty
    state["position_type"]   = None
    state["entry"]           = None
    state["cooldown"]        = COOLDOWN_BARS
    bars_held                = state["bars_in_trade"]
    state["bars_in_trade"]   = 0
    state["daily_pnl"]      += pnl

    state["consecutive_losses"] = 0 if pnl > 0 else state["consecutive_losses"] + 1

    log_trade("SHORT", pnl, reason, bars_held)

    pnl_pct = (pnl / proceeds) * 100 if proceeds else 0
    tv = total_value(state, price)
    print(f"[SHORT] Close {reason} | PnL:${pnl:.2f} ({pnl_pct:+.1f}%) | "
          f"Held:{bars_held}bars | Total:${tv:.2f}")


def _run_optimizer(param_mgr) -> None:
    result = param_mgr.run_optimization()
    if not result:
        return
    m = result["metrics"]
    print(f"\n[OPTIMIZATION] {result['reason']}")
    print(f"  New params: TP={result['new_params']['atr_tp']:.1f}x, "
          f"SL={result['new_params']['atr_sl']:.1f}x, "
          f"ATR%={result['new_params']['atr_percentile']}")
    print(f"  Recent metrics: WR={m['win_rate']*100:.1f}%, "
          f"Exp=${m['expectancy']:.3f}, RR={m['rr_ratio']:.2f}\n")


def _print_status(state, row, price, atr_expanding, iteration) -> None:
    if iteration % 1 != 0:
        return

    tv = total_value(state, price)
    pnl = tv - START_BALANCE

    if state["position_type"] == "LONG":
        u = (price - state["entry"]) * state["position_size"]
        pos_str = f"LONG {state['position_size']:.4f}@${state['entry']:.2f} U:${u:+.2f}"
    elif state["position_type"] == "SHORT":
        u = (state["entry"] - price) * state["position_size"]
        pos_str = f"SHORT {state['position_size']:.4f}@${state['entry']:.2f} U:${u:+.2f}"
    else:
        pos_str = "Flat"

    regime_icon = "🔥" if atr_expanding else "  "
    trend_icon  = "↑" if row["close"] > row["ema_trend"] else "↓"

    print(f"{now().strftime('%H:%M:%S')} ${price:.2f}{trend_icon} "
          f"RSI:{row['rsi']:.0f} {regime_icon}| {pos_str} | "
          f"Tot:${tv:.2f}({pnl:+.2f}) Day:{state['daily_trades']}/{DAILY_MAX_TRADES}")


def _print_shutdown(state) -> None:
    print(f"\n{'='*80}")
    print(f"[SHUTDOWN SUMMARY]")
    print(f"{'='*80}")
    print(f"Holdings: ${state['usd']:.2f} + {state['asset']:.4f} {PAIR}")
    print(f"Today: {state['daily_trades']} trades, "
          f"${state['daily_pnl']:.2f} PnL")
    print("=" * 80)


# ---------------------------------------------------------------
# main loop
# ---------------------------------------------------------------
def run() -> None:
    init_perf_log()
    state = load_state()

    param_mgr = AdaptiveParameterManager(PERF_LOG, PARAM_LOG) \
        if ENABLE_ADAPTIVE_PARAMS else None

    _print_banner(param_mgr)

    iteration = 0
    last_opt_check = now()

    while True:
        try:
            df = fetch_ohlcv(lookback_rows=250)
            if df is None or len(df) < 30:
                print("[WARNING] Insufficient data, retrying in 10s...")
                time.sleep(10)
                continue

            df = enrich(df, EMA_FAST, EMA_SLOW, EMA_TREND)
            row = df.iloc[-1]
            price = float(row["close"])

            if not state["initialized"]:
                _initialize_holdings(state, price)
                save_state(state)

            if reset_daily_counters(state):
                print(f"[INFO] Daily counters reset for {state['last_reset_date']}")

            can_trade, limit_msg = check_safety_limits(state)
            if not can_trade:
                if iteration % 12 == 0:
                    print(f"[PAUSED] {limit_msg}")
                time.sleep(60)
                iteration += 1
                continue

            if param_mgr and (now() - last_opt_check).total_seconds() > 300:
                _run_optimizer(param_mgr)
                last_opt_check = now()

            cur_tp  = param_mgr.atr_tp  if param_mgr else 3.0
            cur_sl  = param_mgr.atr_sl  if param_mgr else 1.4
            cur_pct = param_mgr.atr_percentile if param_mgr else 60

            atr_thr = atr_percentile_threshold(df["atr"], ATR_LOOKBACK_PERIODS, cur_pct)
            atr_expanding = bool(row["atr"] > atr_thr)

            allow_longs, allow_shorts = is_regime_allowed(row)

            if state["position_type"] is not None:
                state["bars_in_trade"] += 1

            d = check_open_long(state, row, allow_longs, atr_expanding)
            if d.action == "OPEN_LONG":
                _open_long(state, price, float(row["atr"]), cur_tp, cur_sl,
                           higher_tf_bullish=(row["close"] > row["ema_trend"]),
                           atr_ratio=(row["atr"] / atr_thr))

            else:
                d = check_open_short(state, row, allow_shorts, atr_expanding)
                if d.action == "OPEN_SHORT":
                    _open_short(state, price, float(row["atr"]), cur_tp, cur_sl,
                                higher_tf_bearish=(row["close"] < row["ema_trend"]),
                                atr_ratio=(row["atr"] / atr_thr))

                elif state["position_type"] == "LONG":
                    d = check_close_long(state, row, price)
                    if d.action == "CLOSE":
                        _close_long(state, price, d.reason)

                elif state["position_type"] == "SHORT":
                    d = check_close_short(state, row, price)
                    if d.action == "CLOSE":
                        _close_short(state, price, d.reason)

            if state["cooldown"] > 0:
                state["cooldown"] -= 1

            save_state(state)
            _print_status(state, row, price, atr_expanding, iteration)

            iteration += 1
            time.sleep(60)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback; traceback.print_exc()
            time.sleep(5)

    _print_shutdown(state)


if __name__ == "__main__":
    run()