"""
strategy.py — Entry and exit signal logic.

Pure functions: given (state, indicators_row, price) return a decision.
Reads config at CALL TIME (not import time) so grid search can
monkey-patch parameters.
"""

from dataclasses import dataclass
import pandas as pd

import config


@dataclass
class Decision:
    action: str  # "OPEN_LONG", "OPEN_SHORT", "CLOSE", "HOLD"
    reason: str = ""  # for CLOSE: TP / SL / RSI / TIME


def is_regime_allowed(row: pd.Series) -> tuple[bool, bool]:
    """Returns (allow_longs, allow_shorts) based on higher-TF filter."""
    if not config.ENABLE_REGIME_FILTER:
        return True, config.ENABLE_SHORTS

    higher_tf_bullish = row["close"] > row["ema_trend"]
    higher_tf_bearish = row["close"] < row["ema_trend"]

    allow_longs = higher_tf_bullish
    allow_shorts = higher_tf_bearish and config.ENABLE_SHORTS
    return allow_longs, allow_shorts


def check_open_long(state, row, allow_longs, atr_expanding) -> Decision:
    if state["position_type"] is not None:
        return Decision("HOLD")
    if state["cooldown"] > 0:
        return Decision("HOLD")
    if not allow_longs:
        return Decision("HOLD")
    if not (row["ema_f"] > row["ema_s"]):
        return Decision("HOLD")
    if not (config.RSI_LONG_MIN < row["rsi"] < config.RSI_LONG_MAX):
        return Decision("HOLD")
    if not atr_expanding:
        return Decision("HOLD")
    if state["usd"] <= 1:
        return Decision("HOLD")
    return Decision("OPEN_LONG")


def check_open_short(state, row, allow_shorts, atr_expanding) -> Decision:
    if state["position_type"] is not None:
        return Decision("HOLD")
    if state["cooldown"] > 0:
        return Decision("HOLD")
    if not allow_shorts:
        return Decision("HOLD")
    if not (row["ema_f"] < row["ema_s"]):
        return Decision("HOLD")
    if not (config.RSI_SHORT_MIN < row["rsi"] < config.RSI_SHORT_MAX):
        return Decision("HOLD")
    if not atr_expanding:
        return Decision("HOLD")
    if state["asset"] <= state["base_asset"] * 0.1:
        return Decision("HOLD")
    return Decision("OPEN_SHORT")


def check_close_long(state, row, price) -> Decision:
    if state["position_type"] != "LONG":
        return Decision("HOLD")
    if price >= state["tp"]:
        return Decision("CLOSE", "TP")
    if price <= state["sl"]:
        return Decision("CLOSE", "SL")
    if row["rsi"] > config.RSI_EXIT_LONG:
        return Decision("CLOSE", "RSI")
    if state["bars_in_trade"] >= config.MAX_BARS_IN_TRADE:
        return Decision("CLOSE", "TIME")
    return Decision("HOLD")


def check_close_short(state, row, price) -> Decision:
    if state["position_type"] != "SHORT":
        return Decision("HOLD")
    if price <= state["tp"]:
        return Decision("CLOSE", "TP")
    if price >= state["sl"]:
        return Decision("CLOSE", "SL")
    if row["rsi"] < config.RSI_EXIT_SHORT:
        return Decision("CLOSE", "RSI")
    if state["bars_in_trade"] >= config.MAX_BARS_IN_TRADE:
        return Decision("CLOSE", "TIME")
    return Decision("HOLD")
