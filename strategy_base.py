"""
strategy_base.py — Abstract interface for pluggable strategies.

Every strategy must inherit from StrategyBase and implement
check_entry() and check_exit(). Strategies receive a `context` dict
with market indicators; they receive `state` and can mutate it via
a returned Decision only — never directly.
"""
from dataclasses import dataclass, field
from typing import Any
import pandas as pd


@dataclass
class Decision:
    """Returned by check_entry/check_exit."""
    action: str                    # OPEN_LONG | OPEN_SHORT | CLOSE | HOLD
    reason: str = ""               # for CLOSE: TP/SL/RSI/TIME/<custom>
    metadata: dict = field(default_factory=dict)  # optional extras


class StrategyBase:
    """
    Base class for all strategies.

    Subclasses must set:
        name                — short id used on CLI and in config
        description         — one-line summary
        default_params      — dict of tunable parameters

    Subclasses must implement:
        check_entry(state, row, context)  -> Decision
        check_exit(state, row, price, context)  -> Decision
    """
    name: str = "unnamed"
    description: str = ""
    default_params: dict[str, Any] = {}

    def __init__(self, params: dict[str, Any] | None = None):
        """
        Merge user-supplied params over defaults.
        Any missing key falls back to default_params.
        """
        merged = dict(self.default_params)
        if params:
            for k, v in params.items():
                if k not in merged:
                    raise ValueError(
                        f"[{self.name}] Unknown parameter: '{k}'. "
                        f"Valid options: {list(merged.keys())}"
                    )
                merged[k] = v
        self.params = merged

    # ---- to be overridden by subclasses ----
    def check_entry(self, state: dict, row: pd.Series,
                    context: dict) -> Decision:
        raise NotImplementedError

    def check_exit(self, state: dict, row: pd.Series,
                   price: float, context: dict) -> Decision:
        raise NotImplementedError

    # ---- optional hook: called before each candle ----
    def pre_bar(self, state: dict, row: pd.Series,
                context: dict) -> None:
        """Override to run per-bar logic (e.g., trailing stops)."""
        pass

    # ---- helper: consistent string representation ----
    def __repr__(self) -> str:
        p = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"<{self.name}: {p}>"