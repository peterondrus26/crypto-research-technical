"""
registry.py — Central registry of available strategies.

Add a new strategy in three lines:
    from strategies.my_strategy import MyStrategy
    _REGISTRY["my_strategy"] = MyStrategy

Then it's available everywhere: backtest, live, menu, grid_search.
"""
from strategy_base import StrategyBase
from strategies.rsi_ema import RSIEMAStrategy


_REGISTRY: dict[str, type[StrategyBase]] = {
    "rsi_ema": RSIEMAStrategy,
    # future strategies register here:
    # "meanrev": MeanRevStrategy,
    # "breakout": BreakoutStrategy,
}


def register(name: str, cls: type[StrategyBase]) -> None:
    """Programmatic registration (useful for tests)."""
    _REGISTRY[name] = cls


def get_strategy_class(name: str) -> type[StrategyBase]:
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown strategy: '{name}'. "
            f"Available: {sorted(_REGISTRY.keys())}"
        )
    return _REGISTRY[name]


def build_strategy(name: str, params: dict | None = None) -> StrategyBase:
    """Instantiate a strategy by name with optional params override."""
    cls = get_strategy_class(name)
    return cls(params=params)


def list_strategies() -> list[str]:
    return sorted(_REGISTRY.keys())


def describe_strategy(name: str) -> dict:
    cls = get_strategy_class(name)
    return {
        "name": cls.name,
        "description": cls.description,
        "params": dict(cls.default_params),
    }