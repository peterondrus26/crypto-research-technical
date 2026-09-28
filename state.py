"""
state.py — JSON state persistence and daily counter management.

Bug fix: reset_daily_counters() now also resets consecutive_losses,
so a losing streak from a previous day doesn't lock the bot forever.
"""

import json
import os
from datetime import datetime, timezone

from config import STATE_FILE, START_BALANCE, INITIAL_ASSET_ALLOCATION


def now() -> datetime:
    return datetime.now(timezone.utc)


def _default_state() -> dict:
    return {
        "initialized": False,
        "base_usd": START_BALANCE * (1 - INITIAL_ASSET_ALLOCATION),
        "base_asset": 0.0,
        "usd": 0.0,
        "asset": 0.0,
        "entry": None,
        "tp": None,
        "sl": None,
        "cooldown": 0,
        "position_type": None,
        "position_size": 0.0,
        "bars_in_trade": 0,
        "daily_trades": 0,
        "daily_pnl": 0.0,
        "consecutive_losses": 0,
        "last_reset_date": now().date().isoformat(),
        "trades_today": [],
    }


def load_state(path: str = STATE_FILE) -> dict:
    if os.path.exists(path):
        with open(path, "r") as f:
            state = json.load(f)
        # Ensure all defaults exist (forward-compat for older state files)
        defaults = _default_state()
        for key, val in defaults.items():
            state.setdefault(key, val)
        return state
    return _default_state()


def save_state(state: dict, path: str = STATE_FILE) -> None:
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def reset_daily_counters(state: dict) -> bool:
    """
    Reset daily counters at midnight UTC.

    FIX: also resets consecutive_losses. A losing streak should not
    carry over into a new day — the daily safety limit already gates
    the bot within the day.
    """
    today = now().date().isoformat()
    if state.get("last_reset_date") != today:
        state["daily_trades"] = 0
        state["daily_pnl"] = 0.0
        state["consecutive_losses"] = 0  # ← THE FIX
        state["last_reset_date"] = today
        state["trades_today"] = []
        return True
    return False
