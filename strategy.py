"""
strategy.py — Entry and exit signal logic.

Pure functions: given (state, indicators_row, price, params) return
a decision. No side effects. Same code runs in backtest and live.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from config import (
    ENABLE_REGIME_FILTER, ENABLE_SHORTS,
    RSI_LONG_MIN, RSI_LONG_MAX, RSI_SHORT_MIN, RSI_SHORT_MAX,
    RSI_EXIT_LONG, RSI_EXIT_SHORT, MAX_BARS_IN_TRADE,
)


@dataclass
class Decision:
    action: str            # "OPEN_LONG", "OPEN_SHORT", "CLOSE", "HOLD"
    reason: str = ""       # for CLOSE: TP / SL / RSI / TIME


def is_regime_allowed(row: pd.Series) -> tuple[bool, bool]:
    """
    Returns (allow_longs, allow_shorts) based on higher-TF filter.
    """
    if not ENABLE_REGIME_FILTER:
        return True, ENABLE_SHORTS

    higher_tf_bullish = row["close"] > row["ema_trend"]
    higher_tf_bearish = row["close"] < row["ema_trend"]

    allow_longs  = higher_tf_bullish
    allow_shorts = higher_tf_bearish and ENABLE_SHORTS
    return allow_longs, allow_shorts


def check_open_long(state: dict,
                    row: pd.Series,
                    allow_longs: bool,
                    atr_expanding: bool) -> Decision:
    """Decide whether to open a LONG right now."""
    if state["position_type"] is not None:
        return Decision("HOLD")
    if state["cooldown"] > 0:
        return Decision("HOLD")
    if not allow_longs:
        return Decision("HOLD")
    if not (row["ema_f"] > row["ema_s"]):
        return Decision("HOLD")
    if not (RSI_LONG_MIN < row["rsi"] < RSI_LONG_MAX):
        return Decision("HOLD")
    if not atr_expanding:
        return Decision("HOLD")
    if state["usd"] <= 1:
        return Decision("HOLD")

    return Decision("OPEN_LONG")


def check_open_short(state: dict,
                     row: pd.Series,
                     allow_shorts: bool,
                     atr_expanding: bool) -> Decision:
    """Decide whether to open a SHORT right now."""
    if state["position_type"] is not None:
        return Decision("HOLD")
    if state["cooldown"] > 0:
        return Decision("HOLD")
    if not allow_shorts:
        return Decision("HOLD")
    if not (row["ema_f"] < row["ema_s"]):
        return Decision("HOLD")
    if not (RSI_SHORT_MIN < row["rsi"] < RSI_SHORT_MAX):
        return Decision("HOLD")
    if not atr_expanding:
        return Decision("HOLD")
    if state["asset"] <= state["base_asset"] * 0.1:
        return Decision("HOLD")

    return Decision("OPEN_SHORT")


def check_close_long(state: dict,
                     row: pd.Series,
                     price: float) -> Decision:
    """Decide whether to close an open LONG."""
    if state["position_type"] != "LONG":
        return Decision("HOLD")

    if price >= state["tp"]:
        return Decision("CLOSE", "TP")
    if price <= state["sl"]:
        return Decision("CLOSE", "SL")
    if row["rsi"] > RSI_EXIT_LONG:
        return Decision("CLOSE", "RSI")
    if state["bars_in_trade"] >= MAX_BARS_IN_TRADE:
        return Decision("CLOSE", "TIME")

    return Decision("HOLD")


def check_close_short(state: dict,
                      row: pd.Series,
                      price: float) -> Decision:
    """Decide whether to close an open SHORT."""
    if state["position_type"] != "SHORT":
        return Decision("HOLD")

    if price <= state["tp"]:
        return Decision("CLOSE", "TP")
    if price >= state["sl"]:
        return Decision("CLOSE", "SL")
    if row["rsi"] < RSI_EXIT_SHORT:
        return Decision("CLOSE", "RSI")
    if state["bars_in_trade"] >= MAX_BARS_IN_TRADE:
        return Decision("CLOSE", "TIME")

    return Decision("HOLD")