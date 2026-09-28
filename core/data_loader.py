"""
core/data_loader.py — Fetch and cache OHLCV data.

Data is cached at data/{PAIR}_{TIMEFRAME}_{DAYS}d[_tag].csv.
If the file exists, we load it; otherwise we download from Binance via CCXT.
"""

import os
from datetime import datetime, timezone, timedelta

import ccxt
import pandas as pd

DATA_DIR = "data"
CANDLE_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def data_path(pair: str, timeframe: str, days: int, tag: str = "") -> str:
    """
    Return the cache file path for a given (pair, tf, days, tag).
    `tag` lets us cache alternative windows (e.g., 'oos') without
    colliding with the default files.
    """
    safe_pair = pair.replace("/", "")
    suffix = f"_{tag}" if tag else ""
    return os.path.join(DATA_DIR, f"{safe_pair}_{timeframe}_{days}d{suffix}.csv")


def download(
    pair: str,
    timeframe: str,
    days: int,
    exchange_name: str = "binance",
    end_dt_utc: datetime | None = None,
) -> pd.DataFrame:
    """
    Download `days` of OHLCV from the exchange, paginating as needed.
    If end_dt_utc is provided, downloads the window ending at that time
    instead of "now". Returns DataFrame: time, open, high, low, close, volume.
    """
    if timeframe not in CANDLE_SECONDS:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    candle_sec = CANDLE_SECONDS[timeframe]
    exchange = getattr(ccxt, exchange_name)({"enableRateLimit": True})

    if end_dt_utc is None:
        end_dt = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    else:
        end_dt = end_dt_utc
    start_dt = end_dt - timedelta(days=days)

    since_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    print(
        f"[DOWNLOAD] {pair} {timeframe} for {days} days "
        f"({start_dt.date()} -> {end_dt.date()})"
    )

    all_rows = []
    cursor = since_ms
    requests = 0

    while cursor < end_ms and requests < 500:
        try:
            batch = exchange.fetch_ohlcv(
                pair, timeframe=timeframe, since=cursor, limit=1000
            )
        except Exception as e:
            print(f"[WARN] fetch error: {e}; retrying in 3s...")
            import time as _t

            _t.sleep(3)
            continue

        if not batch:
            break

        batch = [row for row in batch if row[0] <= end_ms]
        if not batch:
            break

        all_rows.extend(batch)
        requests += 1

        last_ts = batch[-1][0]
        next_cursor = last_ts + candle_sec * 1000
        if next_cursor <= cursor:
            break
        if last_ts >= end_ms:
            break
        cursor = next_cursor

        if requests % 5 == 0:
            print(f"  ... {len(all_rows)} candles so far")

    if not all_rows:
        raise RuntimeError(f"No data returned for {pair} {timeframe}")

    df = pd.DataFrame(
        all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df[["time", "open", "high", "low", "close", "volume"]]
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)

    print(f"[DOWNLOAD] Got {len(df)} candles")
    return df


def load_or_fetch(
    pair: str,
    timeframe: str,
    days: int,
    force_download: bool = False,
    end_dt_utc: datetime | None = None,
    tag: str = "",
) -> pd.DataFrame:
    """
    Return OHLCV dataframe. Uses cache if available unless force_download=True.
    If end_dt_utc or tag provided, uses a distinct cache file.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    path = data_path(pair, timeframe, days, tag=tag)

    if os.path.exists(path) and not force_download:
        df = pd.read_csv(path, parse_dates=["time"])
        print(f"[CACHE] Loaded {len(df)} candles from {path}")
        return df

    df = download(pair, timeframe, days, end_dt_utc=end_dt_utc)
    df.to_csv(path, index=False)
    print(f"[SAVE] Wrote {len(df)} candles to {path}")
    return df
