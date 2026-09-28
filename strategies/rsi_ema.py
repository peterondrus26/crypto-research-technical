"""
strategies/rsi_ema.py — The original RSI + EMA trend strategy.

Long:  EMA-fast > EMA-slow, RSI in [rsi_lo, rsi_hi], ATR expanding
Short: EMA-fast < EMA-slow, RSI in [rsi_lo, rsi_hi], ATR expanding

Exit rules:
  TP    — price hits entry ± tp_mult * ATR
  SL    — price hits entry ∓ sl_mult * ATR
  RSI   — RSI crosses rsi_exit_long/rsi_exit_short
  TIME  — bars_in_trade >= max_bars

Params:
  rsi_lo, rsi_hi             — entry RSI band (same band for longs and shorts)
  rsi_exit_long, rsi_exit_short
  tp_mult, sl_mult           — ATR multipliers
  max_bars                   — time stop
  enable_shorts              — turn shorts on/off
  enable_regime_filter       — use EMA-trend filter
"""

import pandas as pd

from strategy_base import StrategyBase, Decision


class RSIEMAStrategy(StrategyBase):
    name = "rsi_ema"
    description = "RSI pullback with EMA trend filter (original design)"
    default_params = {
        "rsi_lo": 47,
        "rsi_hi": 53,
        "rsi_exit_long": 68,
        "rsi_exit_short": 32,
        "tp_mult": 3.0,
        "sl_mult": 1.4,
        "max_bars": 18,
        "enable_shorts": True,
        "enable_regime_filter": True,
    }

    # ------------------------------------------------------------------
    def check_entry(self, state, row, context):
        if state["position_type"] is not None:
            return Decision("HOLD")
        if state["cooldown"] > 0:
            return Decision("HOLD")

        allow_longs, allow_shorts = self._regime(row)

        # Try long
        if (
            allow_longs
            and row["ema_f"] > row["ema_s"]
            and self.params["rsi_lo"] < row["rsi"] < self.params["rsi_hi"]
            and context["atr_expanding"]
            and state["usd"] > 1
        ):
            return Decision("OPEN_LONG")

        # Try short
        if (
            allow_shorts
            and row["ema_f"] < row["ema_s"]
            and self.params["rsi_lo"] < row["rsi"] < self.params["rsi_hi"]
            and context["atr_expanding"]
            and state["asset"] > state["base_asset"] * 0.1
        ):
            return Decision("OPEN_SHORT")

        return Decision("HOLD")

    # ------------------------------------------------------------------
    def check_exit(self, state, row, price, context):
        if state["position_type"] == "LONG":
            if price >= state["tp"]:
                return Decision("CLOSE", "TP")
            if price <= state["sl"]:
                return Decision("CLOSE", "SL")
            if row["rsi"] > self.params["rsi_exit_long"]:
                return Decision("CLOSE", "RSI")
            if state["bars_in_trade"] >= self.params["max_bars"]:
                return Decision("CLOSE", "TIME")

        elif state["position_type"] == "SHORT":
            if price <= state["tp"]:
                return Decision("CLOSE", "TP")
            if price >= state["sl"]:
                return Decision("CLOSE", "SL")
            if row["rsi"] < self.params["rsi_exit_short"]:
                return Decision("CLOSE", "RSI")
            if state["bars_in_trade"] >= self.params["max_bars"]:
                return Decision("CLOSE", "TIME")

        return Decision("HOLD")

    # ------------------------------------------------------------------
    def _regime(self, row):
        """Return (allow_longs, allow_shorts)."""
        if not self.params["enable_regime_filter"]:
            return True, self.params["enable_shorts"]

        higher_tf_bullish = row["close"] > row["ema_trend"]
        higher_tf_bearish = row["close"] < row["ema_trend"]

        return (higher_tf_bullish, higher_tf_bearish and self.params["enable_shorts"])
