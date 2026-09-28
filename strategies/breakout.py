"""
strategies/breakout.py — Breakout / trend-following strategy.

Entry LONG: price closes above the highest high of the last `lookback`
            bars AND volume exceeds `vol_mult` × 20-bar average.
Exit:       trailing stop at `trail_atr` × ATR from the peak, OR time stop.

Params:
    lookback    — bars to look back for the high (default 20)
    vol_mult    — volume must exceed avg * this (default 1.5)
    trail_atr   — trailing stop distance in ATR (default 2.0)
    max_bars    — time stop (default 24)
"""

import pandas as pd

from strategy_base import StrategyBase, Decision


class BreakoutStrategy(StrategyBase):
    uses_runner_tp_sl = False
    name = "breakout"
    description = "Enter on N-bar high breakout with volume confirmation"
    default_params = {
        "lookback": 20,
        "vol_mult": 1.5,
        "trail_atr": 2.0,
        "max_bars": 24,
    }

    def check_entry(self, state, row, context):
        if state["position_type"] is not None:
            return Decision("HOLD")
        if state["cooldown"] > 0:
            return Decision("HOLD")

        if pd.isna(row["vol_ratio"]):
            return Decision("HOLD")

        rolling_high = context.get("rolling_high")
        if rolling_high is None:
            return Decision("HOLD")

        if (
            row["close"] > rolling_high
            and row["vol_ratio"] > self.params["vol_mult"]
            and state["usd"] > 1
        ):
            return Decision("OPEN_LONG")

        return Decision("HOLD")

    def check_exit(self, state, row, price, context):
        if state["position_type"] != "LONG":
            return Decision("HOLD")

        # Trailing stop: raise SL as price climbs
        trail_atr = self.params["trail_atr"]
        new_sl = price - float(row["atr"]) * trail_atr
        if state["sl"] is None or new_sl > state["sl"]:
            state["sl"] = new_sl

        if price <= state["sl"]:
            return Decision("CLOSE", "SL")
        if state["bars_in_trade"] >= self.params["max_bars"]:
            return Decision("CLOSE", "TIME")

        return Decision("HOLD")
