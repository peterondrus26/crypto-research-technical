"""
config.py — All tunable constants for the SOL adaptive bot.

This is the single source of truth for parameters.
Change values here; nothing else should hardcode numbers.
"""

# ============================================================
# CORE IDENTITY
# ============================================================
PAIR = "SOL"
KRAKEN_PAIR = "SOLUSD"
INTERVAL = "5"                # 5-minute candles
START_BALANCE = 50.0
INITIAL_ASSET_ALLOCATION = 0.40   # 40% in SOL, 60% in USD

# ============================================================
# FILE PATHS
# ============================================================
STATE_FILE = f"state_{PAIR.lower()}_adaptive.json"
PERF_LOG   = f"performance_{PAIR.lower()}_adaptive.csv"
PARAM_LOG  = f"parameters_{PAIR.lower()}_adaptive.csv"

# ============================================================
# DATA SOURCE
# ============================================================
USE_LIVE_DATA = True          # True = Kraken API, False = ohlcv_sample.csv

# ============================================================
# INDICATOR SETTINGS (FIXED — not auto-tuned)
# ============================================================
EMA_FAST  = 8
EMA_SLOW  = 21
EMA_TREND = 200               # Higher-timeframe regime filter
RSI_PERIOD = 14
ATR_PERIOD = 14

# ============================================================
# ENTRY/EXIT THRESHOLDS (RSI)
# ============================================================
RSI_LONG_MIN   = 47
RSI_LONG_MAX   = 53
RSI_SHORT_MIN  = 47
RSI_SHORT_MAX  = 53
RSI_EXIT_LONG  = 68
RSI_EXIT_SHORT = 32

# ============================================================
# RISK PARAMETERS (initial values; AdaptiveParameterManager may override)
# ============================================================
ATR_TP = 3.0
ATR_SL = 1.4

# Hard safety bounds for the adaptive engine — MUST NOT be exceeded
ATR_TP_MIN = 2.2
ATR_TP_MAX = 4.0
ATR_SL_MIN = 1.2
ATR_SL_MAX = 2.0

# ============================================================
# TIME MANAGEMENT
# ============================================================
MAX_BARS_IN_TRADE = 18        # ~90 min on 5m candles
COOLDOWN_BARS     = 3

# ============================================================
# FEATURE TOGGLES
# ============================================================
ENABLE_REGIME_FILTER  = True
ENABLE_SHORTS         = True
ENABLE_ADAPTIVE_PARAMS = True

# ============================================================
# VOLATILITY GATING (percentile-based ATR filter)
# ============================================================
ATR_PERCENTILE_THRESHOLD = 60
ATR_LOOKBACK_PERIODS     = 50
ATR_MIN                  = 0.0015     # absolute floor (ratio, not $)

# ============================================================
# SAFETY LIMITS
# ============================================================
MAX_DAILY_LOSS           = -2.0       # in USD (matches old logic)
MAX_CONSECUTIVE_LOSSES   = 5
DAILY_MAX_TRADES         = 25

# ============================================================
# ADAPTIVE ENGINE
# ============================================================
OPTIMIZATION_INTERVAL_HOURS  = 6
MIN_TRADES_FOR_OPTIMIZATION  = 15

# ============================================================
# FEES (Kraken taker fee schedule, tier 0)
# ============================================================
MAKER_FEE = 0.0016
TAKER_FEE = 0.0026
TRADING_FEE = TAKER_FEE