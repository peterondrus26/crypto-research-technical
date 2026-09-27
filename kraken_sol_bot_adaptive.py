import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone, timedelta
import json
import os
import sys
import signal
import requests
from collections import deque

PAIR = "SOL"
INTERVAL = "5"
START_BALANCE = 50.0
INITIAL_ASSET_ALLOCATION = 0.40
STATE_FILE = f"state_{PAIR.lower()}_adaptive.json"
PERF_LOG = f"performance_{PAIR.lower()}_adaptive.csv"
PARAM_LOG = f"parameters_{PAIR.lower()}_adaptive.csv"

# Kraken API settings
KRAKEN_PAIR = "SOLUSD"
USE_LIVE_DATA = True

# === ADAPTIVE STRATEGY PARAMETERS ===
# These will be adjusted automatically by the optimization module

# Core strategy (FIXED - don't auto-adjust)
EMA_FAST = 8
EMA_SLOW = 21
EMA_TREND = 200  # Higher timeframe trend filter

# RSI parameters (ADAPTIVE - tightened for pullbacks only)
RSI_LONG_MIN = 47  # Tighter: was 48
RSI_LONG_MAX = 53  # Tighter: was 55
RSI_SHORT_MIN = 47  # Symmetric
RSI_SHORT_MAX = 53  # Symmetric
RSI_EXIT_LONG = 68
RSI_EXIT_SHORT = 32

# Risk management (ADAPTIVE with bounds)
ATR_TP = 3.0  # IMPROVED: was 2.5, now 3.0 for SOL
ATR_SL = 1.4  # IMPROVED: was 1.2, now 1.4
ATR_TP_MIN = 2.2  # Safety bounds
ATR_TP_MAX = 4.0
ATR_SL_MIN = 1.2
ATR_SL_MAX = 2.0

# Time management
MAX_BARS_IN_TRADE = 18  # ~90 minutes on 5m (was 12)
COOLDOWN_BARS = 3

# Regime detection (NEW)
ENABLE_REGIME_FILTER = True  # Use higher TF trend
ENABLE_SHORTS = True  # Both directions enabled
ENABLE_ADAPTIVE_PARAMS = True  # Auto-optimization

# Dynamic ATR threshold (NEW - percentile based)
ATR_PERCENTILE_THRESHOLD = 60  # Only trade when ATR > 60th percentile
ATR_LOOKBACK_PERIODS = 50  # Rolling window for percentile

# Safety limits (NEW)
MAX_DAILY_LOSS = -2.0  # Stop trading if down 2%
MAX_CONSECUTIVE_LOSSES = 5  # Pause after 5 losses
DAILY_MAX_TRADES = 25  # Prevent overtrading

# Auto-optimization settings (NEW)
OPTIMIZATION_INTERVAL_HOURS = 6  # Re-evaluate every 6 hours
MIN_TRADES_FOR_OPTIMIZATION = 15  # Need at least 15 trades to optimize

# Kraken fees
MAKER_FEE = 0.0016
TAKER_FEE = 0.0026
TRADING_FEE = TAKER_FEE

# Global state
running = True

def signal_handler(sig, frame):
    global running
    print("\n[INFO] Shutting down gracefully...")
    running = False

signal.signal(signal.SIGINT, signal_handler)

# ========== ADAPTIVE PARAMETER MODULE ==========

class AdaptiveParameterManager:
    """
    Micro-optimization engine that adapts parameters based on recent performance
    WITHOUT overfitting or destabilizing the strategy
    """
    
    def __init__(self, perf_log_file, param_log_file):
        self.perf_log = perf_log_file
        self.param_log = param_log_file
        self.last_optimization = datetime.now(timezone.utc)
        
        # Current adaptive parameters
        self.atr_tp = ATR_TP
        self.atr_sl = ATR_SL
        self.atr_percentile = ATR_PERCENTILE_THRESHOLD
        
        # Initialize param log
        if not os.path.exists(self.param_log):
            with open(self.param_log, 'w') as f:
                f.write("timestamp,atr_tp,atr_sl,atr_percentile,reason\n")
    
    def should_optimize(self):
        """Check if it's time to re-optimize"""
        hours_since = (datetime.now(timezone.utc) - self.last_optimization).total_seconds() / 3600
        return hours_since >= OPTIMIZATION_INTERVAL_HOURS
    
    def get_recent_trades(self, n=30):
        """Load recent N trades from performance log"""
        if not os.path.exists(self.perf_log):
            return None
        
        try:
            df = pd.read_csv(self.perf_log)
            if len(df) < MIN_TRADES_FOR_OPTIMIZATION:
                return None
            return df.tail(n)
        except:
            return None
    
    def calculate_metrics(self, trades_df):
        """Calculate performance metrics"""
        if trades_df is None or len(trades_df) == 0:
            return None
        
        wins = trades_df[trades_df['pnl'] > 0]
        losses = trades_df[trades_df['pnl'] <= 0]
        
        metrics = {
            'total_trades': len(trades_df),
            'win_rate': len(wins) / len(trades_df) if len(trades_df) > 0 else 0,
            'avg_win': wins['pnl'].mean() if len(wins) > 0 else 0,
            'avg_loss': losses['pnl'].mean() if len(losses) > 0 else 0,
            'total_pnl': trades_df['pnl'].sum(),
            'expectancy': trades_df['pnl'].mean(),
            
            # Exit reason analysis
            'tp_count': len(trades_df[trades_df['exit_reason'] == 'TP']),
            'sl_count': len(trades_df[trades_df['exit_reason'] == 'SL']),
            'time_count': len(trades_df[trades_df['exit_reason'] == 'TIME']),
            'rsi_count': len(trades_df[trades_df['exit_reason'] == 'RSI'])
        }
        
        # Reward-to-risk ratio
        if metrics['avg_loss'] != 0:
            metrics['rr_ratio'] = abs(metrics['avg_win'] / metrics['avg_loss'])
        else:
            metrics['rr_ratio'] = 0
        
        return metrics
    
    def optimize_parameters(self, metrics):
        """
        Adjust parameters based on performance metrics
        ONE dimension at a time to avoid instability
        """
        if metrics is None:
            return "No metrics"
        
        adjustments = []
        
        # Rule 1: If avg win too small, increase TP
        if metrics['avg_win'] > 0 and metrics['avg_win'] < 0.20:
            new_tp = min(self.atr_tp + 0.2, ATR_TP_MAX)
            if new_tp != self.atr_tp:
                self.atr_tp = new_tp
                adjustments.append(f"Increased TP to {new_tp:.1f} (wins too small)")
        
        # Rule 2: If win rate too low, tighten entry (increase percentile)
        elif metrics['win_rate'] < 0.45:
            new_percentile = min(self.atr_percentile + 5, 75)
            if new_percentile != self.atr_percentile:
                self.atr_percentile = new_percentile
                adjustments.append(f"Raised ATR filter to {new_percentile}% (low win rate)")
        
        # Rule 3: If too many TIME exits, widen SL slightly
        elif metrics['time_count'] > metrics['total_trades'] * 0.3:
            new_sl = min(self.atr_sl + 0.1, ATR_SL_MAX)
            if new_sl != self.atr_sl:
                self.atr_sl = new_sl
                adjustments.append(f"Widened SL to {new_sl:.1f} (many time exits)")
        
        # Rule 4: If expectancy positive but RR poor, increase TP
        elif metrics['expectancy'] > 0 and metrics['rr_ratio'] < 2.0:
            new_tp = min(self.atr_tp + 0.3, ATR_TP_MAX)
            if new_tp != self.atr_tp:
                self.atr_tp = new_tp
                adjustments.append(f"Increased TP to {new_tp:.1f} (improve RR ratio)")
        
        # Rule 5: If overtrading (expectancy negative), raise filter
        elif metrics['total_trades'] > 20 and metrics['expectancy'] < 0:
            new_percentile = min(self.atr_percentile + 5, 75)
            if new_percentile != self.atr_percentile:
                self.atr_percentile = new_percentile
                adjustments.append(f"Raised ATR filter to {new_percentile}% (negative expectancy)")
        
        # Rule 6: If performing well, can slightly relax to get more trades
        elif metrics['expectancy'] > 0.15 and metrics['total_trades'] < 10:
            new_percentile = max(self.atr_percentile - 3, 55)
            if new_percentile != self.atr_percentile:
                self.atr_percentile = new_percentile
                adjustments.append(f"Lowered ATR filter to {new_percentile}% (good performance, low volume)")
        
        reason = " | ".join(adjustments) if adjustments else "No changes needed"
        
        # Log parameter changes
        with open(self.param_log, 'a') as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()},{self.atr_tp:.2f},{self.atr_sl:.2f},{self.atr_percentile},{reason}\n")
        
        self.last_optimization = datetime.now(timezone.utc)
        return reason
    
    def run_optimization(self):
        """Main optimization routine"""
        if not self.should_optimize():
            return None
        
        trades = self.get_recent_trades(30)
        metrics = self.calculate_metrics(trades)
        
        if metrics is None:
            return None
        
        reason = self.optimize_parameters(metrics)
        
        return {
            'metrics': metrics,
            'new_params': {
                'atr_tp': self.atr_tp,
                'atr_sl': self.atr_sl,
                'atr_percentile': self.atr_percentile
            },
            'reason': reason
        }

# ========== UTILITIES ==========

def now():
    return datetime.now(timezone.utc)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            # Ensure all fields exist
            defaults = {
                "initialized": False,
                "base_usd": 0,
                "base_asset": 0,
                "position_type": None,
                "bars_in_trade": 0,
                "daily_trades": 0,
                "daily_pnl": 0,
                "consecutive_losses": 0,
                "last_reset_date": now().date().isoformat(),
                "trades_today": []
            }
            for key, val in defaults.items():
                if key not in state:
                    state[key] = val
            return state
    
    return {
        "initialized": False,
        "base_usd": START_BALANCE * (1 - INITIAL_ASSET_ALLOCATION),
        "base_asset": 0,
        "usd": 0,
        "asset": 0,
        "entry": None,
        "tp": None,
        "sl": None,
        "cooldown": 0,
        "position_type": None,
        "bars_in_trade": 0,
        "daily_trades": 0,
        "daily_pnl": 0,
        "consecutive_losses": 0,
        "last_reset_date": now().date().isoformat(),
        "trades_today": []
    }

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)

def reset_daily_counters(state):
    """Reset daily limits at midnight UTC"""
    today = now().date().isoformat()
    if state.get("last_reset_date") != today:
        state["daily_trades"] = 0
        state["daily_pnl"] = 0
        state["last_reset_date"] = today
        state["trades_today"] = []
        print(f"[INFO] Daily counters reset for {today}")

def init_perf_log():
    if not os.path.exists(PERF_LOG):
        with open(PERF_LOG, "w") as f:
            f.write("timestamp,pair,position_type,pnl,exit_reason,bars_held\n")

def check_safety_limits(state):
    """Check if trading should be paused due to safety limits"""
    # Daily loss limit
    if state["daily_pnl"] <= MAX_DAILY_LOSS:
        return False, f"Daily loss limit hit: ${state['daily_pnl']:.2f}"
    
    # Consecutive losses
    if state["consecutive_losses"] >= MAX_CONSECUTIVE_LOSSES:
        return False, f"Too many consecutive losses: {state['consecutive_losses']}"
    
    # Daily trade limit
    if state["daily_trades"] >= DAILY_MAX_TRADES:
        return False, f"Daily trade limit hit: {state['daily_trades']}"
    
    return True, ""

# ========== INDICATORS ==========

def rsi(series, n=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = -delta.clip(upper=0).rolling(n).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def atr(df, n=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def atr_percentile_threshold(atr_series, lookback, percentile):
    """Calculate dynamic ATR threshold based on percentile"""
    if len(atr_series) < lookback:
        return atr_series.iloc[-1]  # Not enough data
    
    recent_atr = atr_series.iloc[-lookback:]
    threshold = np.percentile(recent_atr.dropna(), percentile)
    return threshold

# ========== DATA FETCHING ==========

def fetch_ohlcv_kraken():
    try:
        url = "https://api.kraken.com/0/public/OHLC"
        params = {"pair": KRAKEN_PAIR, "interval": INTERVAL}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("error") and len(data["error"]) > 0:
            print(f"[ERROR] Kraken API error: {data['error']}")
            return None
        
        pair_key = list(data["result"].keys())[0]
        ohlc_data = data["result"][pair_key]
        
        df = pd.DataFrame(ohlc_data, columns=[
            "timestamp", "open", "high", "low", "close", "vwap", "volume", "count"
        ])
        
        df["time"] = pd.to_datetime(df["timestamp"], unit="s")
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)
        
        df.set_index("time", inplace=True)
        return df[["open", "high", "low", "close", "volume"]].tail(250)  # Get more data for trend EMA
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {e}")
        return None

def fetch_ohlcv_csv():
    csv_file = "ohlcv_sample.csv"
    if not os.path.exists(csv_file):
        return None
    
    try:
        df = pd.read_csv(csv_file, parse_dates=["time"])
        df.set_index("time", inplace=True)
        return df.tail(250)
    except:
        return None

def fetch_ohlcv():
    if USE_LIVE_DATA:
        return fetch_ohlcv_kraken()
    else:
        return fetch_ohlcv_csv()

# ========== MAIN TRADING LOOP ==========

def run():
    global running
    
    init_perf_log()
    state = load_state()
    
    # Initialize adaptive parameter manager
    param_manager = AdaptiveParameterManager(PERF_LOG, PARAM_LOG) if ENABLE_ADAPTIVE_PARAMS else None
    
    data_source = "Kraken API (LIVE)" if USE_LIVE_DATA else "CSV (STATIC)"
    
    print(f"{'='*80}")
    print(f"  SOL ADAPTIVE BIDIRECTIONAL BOT - Professional Grade")
    print(f"{'='*80}")
    print(f"[CONFIG]")
    print(f"  Balance: ${START_BALANCE:.2f}")
    print(f"  Allocation: {INITIAL_ASSET_ALLOCATION*100:.0f}% {PAIR}, {(1-INITIAL_ASSET_ALLOCATION)*100:.0f}% USD")
    print(f"  Data: {data_source}")
    print(f"\n[STRATEGY]")
    print(f"  Directions: LONG + SHORT (both enabled)")
    print(f"  RSI: {RSI_LONG_MIN}-{RSI_LONG_MAX} (tight pullbacks)")
    print(f"  ATR TP/SL: {param_manager.atr_tp if param_manager else ATR_TP:.1f}x / {param_manager.atr_sl if param_manager else ATR_SL:.1f}x")
    print(f"  Time Stop: {MAX_BARS_IN_TRADE} bars (~{MAX_BARS_IN_TRADE*5} min)")
    print(f"\n[REGIME FILTERS]")
    print(f"  Trend Filter (EMA{EMA_TREND}): {'ENABLED' if ENABLE_REGIME_FILTER else 'DISABLED'}")
    print(f"  ATR Percentile: {param_manager.atr_percentile if param_manager else ATR_PERCENTILE_THRESHOLD}% (dynamic)")
    print(f"\n[SAFETY LIMITS]")
    print(f"  Max Daily Loss: {MAX_DAILY_LOSS}%")
    print(f"  Max Consecutive Losses: {MAX_CONSECUTIVE_LOSSES}")
    print(f"  Max Daily Trades: {DAILY_MAX_TRADES}")
    print(f"\n[ADAPTIVE OPTIMIZATION]")
    print(f"  Status: {'ENABLED' if ENABLE_ADAPTIVE_PARAMS else 'DISABLED'}")
    if ENABLE_ADAPTIVE_PARAMS:
        print(f"  Interval: Every {OPTIMIZATION_INTERVAL_HOURS} hours")
        print(f"  Min trades needed: {MIN_TRADES_FOR_OPTIMIZATION}")
    print(f"\n[INFO] Press Ctrl+C to stop")
    print(f"{'='*80}\n")

    iteration = 0
    last_optimization_check = now()
    
    while running:
        try:
            df = fetch_ohlcv()
            
            if df is None or len(df) < 30:
                print("[WARNING] Insufficient data, retrying in 10s...")
                time.sleep(10)
                continue

            # Calculate indicators
            df["ema_f"] = df["close"].ewm(span=EMA_FAST).mean()
            df["ema_s"] = df["close"].ewm(span=EMA_SLOW).mean()
            df["ema_trend"] = df["close"].ewm(span=EMA_TREND).mean()  # Higher TF trend
            df["rsi"] = rsi(df["close"])
            df["atr"] = atr(df)
            df["atrr"] = df["atr"] / df["close"]

            row = df.iloc[-1]
            price = row["close"]

            # Initialize base holdings
            if not state["initialized"]:
                usd_to_spend = START_BALANCE * INITIAL_ASSET_ALLOCATION
                buy_fee = usd_to_spend * TRADING_FEE
                asset_bought = (usd_to_spend - buy_fee) / price
                
                state["base_usd"] = START_BALANCE - usd_to_spend
                state["base_asset"] = asset_bought
                state["usd"] = state["base_usd"]
                state["asset"] = state["base_asset"]
                state["initialized"] = True
                
                print(f"[INIT] Bought {asset_bought:.4f} {PAIR} @ ${price:.3f} (fee: ${buy_fee:.4f})")
                print(f"[INIT] Holdings: ${state['base_usd']:.2f} + {state['base_asset']:.4f} {PAIR}\n")
                save_state(state)

            # Reset daily counters if needed
            reset_daily_counters(state)

            # Check safety limits
            can_trade, limit_msg = check_safety_limits(state)
            if not can_trade:
                if iteration % 12 == 0:  # Print every hour
                    print(f"[PAUSED] {limit_msg}")
                time.sleep(60)
                iteration += 1
                continue

            # Run adaptive optimization (if enabled)
            if param_manager and (now() - last_optimization_check).total_seconds() > 300:  # Check every 5 min
                opt_result = param_manager.run_optimization()
                if opt_result:
                    print(f"\n[OPTIMIZATION] {opt_result['reason']}")
                    print(f"  New params: TP={opt_result['new_params']['atr_tp']:.1f}x, SL={opt_result['new_params']['atr_sl']:.1f}x, ATR%={opt_result['new_params']['atr_percentile']}")
                    print(f"  Recent metrics: WR={opt_result['metrics']['win_rate']*100:.1f}%, Exp=${opt_result['metrics']['expectancy']:.3f}, RR={opt_result['metrics']['rr_ratio']:.2f}\n")
                last_optimization_check = now()

            # Get current adaptive parameters
            current_atr_tp = param_manager.atr_tp if param_manager else ATR_TP
            current_atr_sl = param_manager.atr_sl if param_manager else ATR_SL
            current_atr_percentile = param_manager.atr_percentile if param_manager else ATR_PERCENTILE_THRESHOLD

            # === REGIME DETECTION ===
            trend_up = row["ema_f"] > row["ema_s"]
            trend_down = row["ema_f"] < row["ema_s"]
            
            # Higher timeframe trend filter
            higher_tf_bullish = row["close"] > row["ema_trend"]
            higher_tf_bearish = row["close"] < row["ema_trend"]
            
            # Dynamic ATR threshold (percentile-based)
            atr_threshold_value = atr_percentile_threshold(
                df["atr"], 
                ATR_LOOKBACK_PERIODS, 
                current_atr_percentile
            )
            atr_expanding = row["atr"] > atr_threshold_value
            
            # Regime gating
            if ENABLE_REGIME_FILTER:
                allow_longs = higher_tf_bullish
                allow_shorts = higher_tf_bearish and ENABLE_SHORTS
            else:
                allow_longs = True
                allow_shorts = ENABLE_SHORTS

            # Position management
            if state["position_type"] is not None:
                state["bars_in_trade"] += 1

            # === OPEN LONG ===
            if (
                state["position_type"] is None
                and state["cooldown"] == 0
                and allow_longs
                and trend_up
                and RSI_LONG_MIN < row["rsi"] < RSI_LONG_MAX
                and atr_expanding
                and state["usd"] > 1
            ):
                size = state["usd"] * 0.95
                fee = size * TRADING_FEE
                qty = (size - fee) / price
                
                state["usd"] -= size
                state["asset"] += qty
                state["entry"] = price
                state["tp"] = price + row["atr"] * current_atr_tp
                state["sl"] = price - row["atr"] * current_atr_sl
                state["position_type"] = "LONG"
                state["position_size"] = qty
                state["bars_in_trade"] = 0
                state["daily_trades"] += 1
                
                regime = "HTF↑" if higher_tf_bullish else "HTF↓"
                print(f"[LONG] Open {qty:.4f} @ ${price:.2f} | TP:${state['tp']:.2f} SL:${state['sl']:.2f} | {regime} ATR:{(row['atr']/atr_threshold_value):.2f}x")

            # === OPEN SHORT ===
            elif (
                state["position_type"] is None
                and state["cooldown"] == 0
                and allow_shorts
                and trend_down
                and RSI_SHORT_MIN < row["rsi"] < RSI_SHORT_MAX
                and atr_expanding
                and state["asset"] > state["base_asset"] * 0.1
            ):
                qty = state["asset"] * 0.50
                gross = qty * price
                fee = gross * TRADING_FEE
                net = gross - fee
                
                state["asset"] -= qty
                state["usd"] += net
                state["entry"] = price
                state["tp"] = price - row["atr"] * current_atr_tp
                state["sl"] = price + row["atr"] * current_atr_sl
                state["position_type"] = "SHORT"
                state["position_size"] = qty
                state["bars_in_trade"] = 0
                state["daily_trades"] += 1
                
                regime = "HTF↓" if higher_tf_bearish else "HTF↑"
                print(f"[SHORT] Open {qty:.4f} @ ${price:.2f} | TP:${state['tp']:.2f} SL:${state['sl']:.2f} | {regime} ATR:{(row['atr']/atr_threshold_value):.2f}x")

            # === CLOSE LONG ===
            elif state["position_type"] == "LONG":
                exit_reason = None
                
                if price >= state["tp"]:
                    exit_reason = "TP"
                elif price <= state["sl"]:
                    exit_reason = "SL"
                elif row["rsi"] > RSI_EXIT_LONG:
                    exit_reason = "RSI"
                elif state["bars_in_trade"] >= MAX_BARS_IN_TRADE:
                    exit_reason = "TIME"
                
                if exit_reason:
                    qty = state["position_size"]
                    gross = qty * price
                    fee = gross * TRADING_FEE
                    net = gross - fee
                    cost = qty * state["entry"]
                    pnl = net - cost
                    
                    state["asset"] -= qty
                    state["usd"] += net
                    state["position_type"] = None
                    state["entry"] = None
                    state["cooldown"] = COOLDOWN_BARS
                    bars_held = state["bars_in_trade"]
                    state["bars_in_trade"] = 0
                    state["daily_pnl"] += pnl
                    
                    # Track consecutive losses
                    if pnl > 0:
                        state["consecutive_losses"] = 0
                    else:
                        state["consecutive_losses"] += 1

                    with open(PERF_LOG, "a") as f:
                        f.write(f"{now().isoformat()},{PAIR},LONG,{pnl:.4f},{exit_reason},{bars_held}\n")

                    pnl_pct = (pnl / cost) * 100
                    total_value = state["usd"] + (state["asset"] * price)
                    print(f"[LONG] Close {exit_reason} | PnL:${pnl:.2f} ({pnl_pct:+.1f}%) | Held:{bars_held}bars | Total:${total_value:.2f}")

            # === CLOSE SHORT ===
            elif state["position_type"] == "SHORT":
                exit_reason = None
                
                if price <= state["tp"]:
                    exit_reason = "TP"
                elif price >= state["sl"]:
                    exit_reason = "SL"
                elif row["rsi"] < RSI_EXIT_SHORT:
                    exit_reason = "RSI"
                elif state["bars_in_trade"] >= MAX_BARS_IN_TRADE:
                    exit_reason = "TIME"
                
                if exit_reason:
                    qty = state["position_size"]
                    cost = qty * price
                    fee = cost * TRADING_FEE
                    total_cost = cost + fee
                    proceeds = qty * state["entry"]
                    pnl = proceeds - total_cost
                    
                    state["usd"] -= total_cost
                    state["asset"] += qty
                    state["position_type"] = None
                    state["entry"] = None
                    state["cooldown"] = COOLDOWN_BARS
                    bars_held = state["bars_in_trade"]
                    state["bars_in_trade"] = 0
                    state["daily_pnl"] += pnl
                    
                    # Track consecutive losses
                    if pnl > 0:
                        state["consecutive_losses"] = 0
                    else:
                        state["consecutive_losses"] += 1

                    with open(PERF_LOG, "a") as f:
                        f.write(f"{now().isoformat()},{PAIR},SHORT,{pnl:.4f},{exit_reason},{bars_held}\n")

                    pnl_pct = (pnl / proceeds) * 100
                    total_value = state["usd"] + (state["asset"] * price)
                    print(f"[SHORT] Close {exit_reason} | PnL:${pnl:.2f} ({pnl_pct:+.1f}%) | Held:{bars_held}bars | Total:${total_value:.2f}")

            if state["cooldown"] > 0:
                state["cooldown"] -= 1

            save_state(state)

            # Status line
            total_value = state["usd"] + (state["asset"] * price)
            total_pnl = total_value - START_BALANCE
            
            pos_str = "Flat"
            if state["position_type"] == "LONG":
                unrealized = (price - state["entry"]) * state["position_size"]
                pos_str = f"LONG {state['position_size']:.4f}@${state['entry']:.2f} U:${unrealized:+.2f}"
            elif state["position_type"] == "SHORT":
                unrealized = (state["entry"] - price) * state["position_size"]
                pos_str = f"SHORT {state['position_size']:.4f}@${state['entry']:.2f} U:${unrealized:+.2f}"
            
            regime_icon = "🔥" if atr_expanding else "  "
            trend_icon = "↑" if higher_tf_bullish else "↓"
            
            if iteration % 1 == 0:  # Every iteration
                print(f"{now().strftime('%H:%M:%S')} ${price:.2f}{trend_icon} RSI:{row['rsi']:.0f} {regime_icon}| {pos_str} | Tot:${total_value:.2f}({total_pnl:+.2f}) Day:{state['daily_trades']}/{DAILY_MAX_TRADES}")
            
            iteration += 1
            time.sleep(60)
            
        except KeyboardInterrupt:
            running = False
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)
    
    # Final summary
    final_price = price if 'price' in locals() else 0
    final_value = state["usd"] + (state["asset"] * final_price)
    total_pnl = final_value - START_BALANCE
    pnl_pct = (total_pnl / START_BALANCE) * 100
    
    print(f"\n{'='*80}")
    print(f"[SHUTDOWN SUMMARY]")
    print(f"{'='*80}")
    print(f"Holdings: ${state['usd']:.2f} + {state['asset']:.4f} {PAIR}")
    print(f"Total Value: ${final_value:.2f}")
    print(f"Total PnL: ${total_pnl:.2f} ({pnl_pct:+.1f}%)")
    print(f"Today: {state['daily_trades']} trades, ${state['daily_pnl']:.2f} PnL")
    print(f"{'='*80}")

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"[FATAL] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
