"""
risk.py — Safety limits and position sizing.
"""
from config import (
    MAX_DAILY_LOSS, MAX_CONSECUTIVE_LOSSES, DAILY_MAX_TRADES
)


def check_safety_limits(state: dict) -> tuple[bool, str]:
    """
    Return (can_trade, reason).
    If can_trade is False, `reason` explains why.
    """
    if state["daily_pnl"] <= MAX_DAILY_LOSS:
        return False, f"Daily loss limit hit: ${state['daily_pnl']:.2f}"

    if state["consecutive_losses"] >= MAX_CONSECUTIVE_LOSSES:
        return False, f"Too many consecutive losses: {state['consecutive_losses']}"

    if state["daily_trades"] >= DAILY_MAX_TRADES:
        return False, f"Daily trade limit hit: {state['daily_trades']}"

    return True, ""