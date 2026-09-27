"""
data.py — OHLCV fetching from Kraken and CSV.
"""
import os
import pandas as pd
import requests

from config import KRAKEN_PAIR, INTERVAL, USE_LIVE_DATA


def fetch_ohlcv_kraken(lookback_rows: int = 250) -> pd.DataFrame | None:
    """Fetch 5m OHLCV from Kraken public API."""
    try:
        url = "https://api.kraken.com/0/public/OHLC"
        params = {"pair": KRAKEN_PAIR, "interval": INTERVAL}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("error"):
            print(f"[ERROR] Kraken API error: {data['error']}")
            return None

        pair_key = list(data["result"].keys())[0]
        ohlc_data = data["result"][pair_key]

        df = pd.DataFrame(ohlc_data, columns=[
            "timestamp", "open", "high", "low", "close",
            "vwap", "volume", "count"
        ])
        df["time"] = pd.to_datetime(df["timestamp"], unit="s")
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)

        df.set_index("time", inplace=True)
        return df[["open", "high", "low", "close", "volume"]].tail(lookback_rows)

    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {e}")
        return None


def fetch_ohlcv_csv(path: str = "ohlcv_sample.csv",
                    lookback_rows: int = 250) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, parse_dates=["time"])
        df.set_index("time", inplace=True)
        return df.tail(lookback_rows)
    except Exception:
        return None


def fetch_ohlcv(lookback_rows: int = 250) -> pd.DataFrame | None:
    """Unified entry point respecting USE_LIVE_DATA toggle."""
    if USE_LIVE_DATA:
        return fetch_ohlcv_kraken(lookback_rows)
    return fetch_ohlcv_csv(lookback_rows=lookback_rows)