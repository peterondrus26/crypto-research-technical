"""
strategies/meanrev.py — Mean reversion strategy.
"""
import pandas as pd

from strategy_base import StrategyBase, Decision


class MeanRevStrategy(StrategyBase):
    uses_runner_tp_sl = False
    name = "meanrev"
    description = "Buy oversold dips, exit on reversion to mean"
    default_params = {
        "z_entry": 2.0,
        "rsi_entry": 30,
        "rsi_exit": 55,
        "max_bars": 12,
        "sl_atr_mult": 2.0,
    }

    def check_entry(self, state, row, context):
        if state["position_type"] is not None:
            return Decision("HOLD")
        if state["cooldown"] > 0:
            return Decision("HOLD")
        if pd.isna(row["stddev20"]) or pd.isna(row["zscore20"]):
            return Decision("HOLD")

        z = row["zscore20"]
        rsi = row["rsi"]

        if (z < -self.params["z_entry"]
                and rsi < self.params["rsi_entry"]
                and state["usd"] > 1):
            return Decision("OPEN_LONG")

        return Decision("HOLD")

    def check_exit(self, state, row, price, context):
        if state["position_type"] != "LONG":
            return Decision("HOLD")

        if state["sl"] is not None and price <= state["sl"]:
            return Decision("CLOSE", "SL")
        if price >= row["ema20"]:
            return Decision("CLOSE", "TP")
        if row["rsi"] > self.params["rsi_exit"]:
            return Decision("CLOSE", "RSI")
        if state["bars_in_trade"] >= self.params["max_bars"]:
            return Decision("CLOSE", "TIME")

        return Decision("HOLD")