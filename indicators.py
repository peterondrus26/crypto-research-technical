"""
indicators.py — Technical indicators and helpers.

Pure functions. No global state, no I/O.
"""
import numpy as np
import pandas as pd

from config import RSI_PERIOD, ATR_PERIOD


def rsi(series: pd.Series, n: int = RSI_PERIOD) -> pd.Series:
    """Wilder-style RSI using rolling mean (same as original bot)."""
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(n).mean()
    loss  = -delta.clip(upper=0).rolling(n).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, n: int = ATR_PERIOD) -> pd.Series:
    """Average True Range using rolling mean (same as original bot)."""
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"]  - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def atr_percentile_threshold(atr_series: pd.Series,
                             lookback: int,
                             percentile: float) -> float:
    """
    Dynamic ATR threshold = Nth percentile of the last `lookback` ATR values.
    Returns the latest ATR if there isn't enough data yet.
    """
    if len(atr_series) < lookback:
        return float(atr_series.iloc[-1])

    recent = atr_series.iloc[-lookback:].dropna()
    if len(recent) == 0:
        return float(atr_series.iloc[-1])
    return float(np.percentile(recent, percentile))


def enrich(df: pd.DataFrame,
           ema_fast: int,
           ema_slow: int,
           ema_trend: int) -> pd.DataFrame:
    """
    Add all indicator columns used by the strategy.
    Returns a new DataFrame (does not mutate input).
    """
    df = df.copy()
    df["ema_f"]     = df["close"].ewm(span=ema_fast).mean()
    df["ema_s"]     = df["close"].ewm(span=ema_slow).mean()
    df["ema_trend"] = df["close"].ewm(span=ema_trend).mean()
    df["rsi"]       = rsi(df["close"])
    df["atr"]       = atr(df)
    df["atrr"]      = df["atr"] / df["close"]
    return df