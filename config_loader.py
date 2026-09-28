"""
config_loader.py — Load YAML config files into a structured object.

Because `config.py` (the module) is still imported all over the codebase,
loading a YAML file updates the module's attributes in place. This lets
us keep backward compatibility while moving to file-based configs.
"""

import os
import yaml

import config as config_module


def load_yaml(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r") as f:
        return yaml.safe_load(f)


def apply_to_config_module(cfg: dict) -> None:
    """
    Mutate config.py module attributes from a parsed YAML dict.
    Only touches known keys.
    """
    market = cfg.get("market", {})
    account = cfg.get("account", {})
    vol = cfg.get("volatility", {})
    safety = cfg.get("safety", {})
    adaptive = cfg.get("adaptive", {})

    if "pair" in market:
        config_module.PAIR = market["pair"]
    if "kraken_pair" in market:
        config_module.KRAKEN_PAIR = market["kraken_pair"]
    if "interval" in market:
        config_module.INTERVAL = market["interval"]
    if "data_file" in market:
        config_module.DATA_FILE = market["data_file"]

    if "start_balance" in account:
        config_module.START_BALANCE = account["start_balance"]
    if "initial_asset_allocation" in account:
        config_module.INITIAL_ASSET_ALLOCATION = account["initial_asset_allocation"]
    if "trading_fee" in account:
        config_module.TRADING_FEE = account["trading_fee"]

    if "atr_percentile" in vol:
        config_module.ATR_PERCENTILE_THRESHOLD = vol["atr_percentile"]
    if "atr_lookback_periods" in vol:
        config_module.ATR_LOOKBACK_PERIODS = vol["atr_lookback_periods"]
    if "atr_min" in vol:
        config_module.ATR_MIN = vol["atr_min"]

    if "max_daily_loss" in safety:
        config_module.MAX_DAILY_LOSS = safety["max_daily_loss"]
    if "max_consecutive_losses" in safety:
        config_module.MAX_CONSECUTIVE_LOSSES = safety["max_consecutive_losses"]
    if "daily_max_trades" in safety:
        config_module.DAILY_MAX_TRADES = safety["daily_max_trades"]

    if "enabled" in adaptive:
        config_module.ENABLE_ADAPTIVE_PARAMS = adaptive["enabled"]


def load_config(path: str) -> dict:
    """Load YAML, apply to config module, return parsed dict."""
    cfg = load_yaml(path)
    apply_to_config_module(cfg)
    return cfg


def get_strategy_params(cfg: dict) -> tuple[str, dict]:
    """Extract (strategy_name, params) from a loaded config dict."""
    name = cfg.get("strategy")
    if not name:
        raise ValueError("Config missing 'strategy' key")
    params = cfg.get("params", {}) or {}
    return name, params
