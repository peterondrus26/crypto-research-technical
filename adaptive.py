"""
adaptive.py — AdaptiveParameterManager.

Adjusts TP / SL / ATR percentile based on recent trade performance.
Changes ONE parameter at a time, within hard safety bounds.
"""

import os
from datetime import datetime, timezone

import pandas as pd

from config import (
    ATR_TP,
    ATR_SL,
    ATR_PERCENTILE_THRESHOLD,
    ATR_TP_MIN,
    ATR_TP_MAX,
    ATR_SL_MIN,
    ATR_SL_MAX,
    OPTIMIZATION_INTERVAL_HOURS,
    MIN_TRADES_FOR_OPTIMIZATION,
)


class AdaptiveParameterManager:
    def __init__(self, perf_log_file: str, param_log_file: str):
        self.perf_log = perf_log_file
        self.param_log = param_log_file
        self.last_optimization = datetime.now(timezone.utc)

        self.atr_tp = ATR_TP
        self.atr_sl = ATR_SL
        self.atr_percentile = ATR_PERCENTILE_THRESHOLD

        if not os.path.exists(self.param_log):
            with open(self.param_log, "w") as f:
                f.write("timestamp,atr_tp,atr_sl,atr_percentile,reason\n")

    # ---------- gating ----------
    def should_optimize(self) -> bool:
        hours = (
            datetime.now(timezone.utc) - self.last_optimization
        ).total_seconds() / 3600
        return hours >= OPTIMIZATION_INTERVAL_HOURS

    def get_recent_trades(self, n: int = 30):
        if not os.path.exists(self.perf_log):
            return None
        try:
            df = pd.read_csv(self.perf_log)
            if len(df) < MIN_TRADES_FOR_OPTIMIZATION:
                return None
            return df.tail(n)
        except Exception:
            return None

    # ---------- metrics ----------
    def calculate_metrics(self, trades_df):
        if trades_df is None or len(trades_df) == 0:
            return None

        wins = trades_df[trades_df["pnl"] > 0]
        losses = trades_df[trades_df["pnl"] <= 0]

        m = {
            "total_trades": len(trades_df),
            "win_rate": len(wins) / len(trades_df) if len(trades_df) else 0,
            "avg_win": wins["pnl"].mean() if len(wins) else 0,
            "avg_loss": losses["pnl"].mean() if len(losses) else 0,
            "total_pnl": trades_df["pnl"].sum(),
            "expectancy": trades_df["pnl"].mean(),
            "tp_count": len(trades_df[trades_df["exit_reason"] == "TP"]),
            "sl_count": len(trades_df[trades_df["exit_reason"] == "SL"]),
            "time_count": len(trades_df[trades_df["exit_reason"] == "TIME"]),
            "rsi_count": len(trades_df[trades_df["exit_reason"] == "RSI"]),
        }
        m["rr_ratio"] = abs(m["avg_win"] / m["avg_loss"]) if m["avg_loss"] else 0
        return m

    # ---------- optimization ----------
    def optimize_parameters(self, metrics) -> str:
        if metrics is None:
            return "No metrics"

        adjustments = []

        if metrics["avg_win"] > 0 and metrics["avg_win"] < 0.20:
            new_tp = min(self.atr_tp + 0.2, ATR_TP_MAX)
            if new_tp != self.atr_tp:
                self.atr_tp = new_tp
                adjustments.append(f"Increased TP to {new_tp:.1f} (wins too small)")

        elif metrics["win_rate"] < 0.45:
            new_pct = min(self.atr_percentile + 5, 75)
            if new_pct != self.atr_percentile:
                self.atr_percentile = new_pct
                adjustments.append(f"Raised ATR filter to {new_pct}% (low win rate)")

        elif metrics["time_count"] > metrics["total_trades"] * 0.3:
            new_sl = min(self.atr_sl + 0.1, ATR_SL_MAX)
            if new_sl != self.atr_sl:
                self.atr_sl = new_sl
                adjustments.append(f"Widened SL to {new_sl:.1f} (many time exits)")

        elif metrics["expectancy"] > 0 and metrics["rr_ratio"] < 2.0:
            new_tp = min(self.atr_tp + 0.3, ATR_TP_MAX)
            if new_tp != self.atr_tp:
                self.atr_tp = new_tp
                adjustments.append(f"Increased TP to {new_tp:.1f} (improve RR ratio)")

        elif metrics["total_trades"] > 20 and metrics["expectancy"] < 0:
            new_pct = min(self.atr_percentile + 5, 75)
            if new_pct != self.atr_percentile:
                self.atr_percentile = new_pct
                adjustments.append(
                    f"Raised ATR filter to {new_pct}% (negative expectancy)"
                )

        elif metrics["expectancy"] > 0.15 and metrics["total_trades"] < 10:
            new_pct = max(self.atr_percentile - 3, 55)
            if new_pct != self.atr_percentile:
                self.atr_percentile = new_pct
                adjustments.append(
                    f"Lowered ATR filter to {new_pct}% (good performance, low volume)"
                )

        reason = " | ".join(adjustments) if adjustments else "No changes needed"

        with open(self.param_log, "a") as f:
            f.write(
                f"{datetime.now(timezone.utc).isoformat()},"
                f"{self.atr_tp:.2f},{self.atr_sl:.2f},"
                f"{self.atr_percentile},{reason}\n"
            )

        self.last_optimization = datetime.now(timezone.utc)
        return reason

    def run_optimization(self):
        if not self.should_optimize():
            return None
        trades = self.get_recent_trades(30)
        metrics = self.calculate_metrics(trades)
        if metrics is None:
            return None

        reason = self.optimize_parameters(metrics)
        return {
            "metrics": metrics,
            "new_params": {
                "atr_tp": self.atr_tp,
                "atr_sl": self.atr_sl,
                "atr_percentile": self.atr_percentile,
            },
            "reason": reason,
        }
