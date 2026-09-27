"""
download_data.py — Fetch historical OHLCV data using CCXT.

Note: Kraken's public API returns only the most recent 720 candles,
so we use Binance for historical data. Binance pagination works
correctly with the `since` parameter.

Usage:
    python download_data.py            # 30 days default
    python download_data.py 7          # 7 days
"""
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import ccxt
import pandas as pd

from config import INTERVAL


# ---- data source -------------------------------------------------
DATA_EXCHANGE = "binance"
DATA_SYMBOL   = "SOL/USDT"

# ---- pagination --------------------------------------------------
CANDLE_SECONDS = int(INTERVAL) * 60
SAFETY_LIMIT   = 200
SLEEP_BETWEEN  = 1.0


def fetch_range(exchange, symbol, timeframe, since_ms, end_ms):
    """Fetch all candles in [since_ms, end_ms) via paginated fetch_ohlcv."""
    all_rows = []
    cursor   = since_ms
    requests = 0

    while cursor < end_ms and requests < SAFETY_LIMIT:
        try:
            batch = exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, since=cursor, limit=720,
            )
        except Exception as e:
            print(f"[WARN] fetch_ohlcv error: {e}, retrying in 3s...")
            time.sleep(3)
            continue

        if not batch:
            print(f"[INFO] Empty batch at cursor={cursor}, stopping.")
            break

        batch = [row for row in batch if row[0] <= end_ms]
        if not batch:
            break

        all_rows.extend(batch)
        requests += 1

        last_ts = batch[-1][0]
        print(f"[INFO] Request {requests}: got {len(batch)} rows, "
              f"latest={pd.to_datetime(last_ts, unit='ms', utc=True)}")

        next_cursor = last_ts + CANDLE_SECONDS * 1000
        if next_cursor <= cursor:
            print("[WARN] Cursor did not advance; stopping.")
            break

        if last_ts >= end_ms:
            print("[INFO] Reached end of window.")
            break

        cursor = next_cursor
        time.sleep(SLEEP_BETWEEN)

    if not all_rows:
        raise RuntimeError("No candles returned.")

    df = pd.DataFrame(all_rows, columns=[
        "timestamp", "open", "high", "low", "close", "volume"
    ])
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df[["time", "open", "high", "low", "close", "volume"]]
    df = (df.drop_duplicates(subset=["time"])
            .sort_values("time")
            .reset_index(drop=True))
    return df


def download(symbol, timeframe, days):
    exchange = getattr(ccxt, DATA_EXCHANGE)({"enableRateLimit": True})

    end_dt   = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=days)

    since_ms = int(start_dt.timestamp() * 1000)
    end_ms   = int(end_dt.timestamp() * 1000)

    minutes = int(timeframe.rstrip("m"))

    print(f"[INFO] Downloading {symbol} {timeframe} candles via "
          f"{DATA_EXCHANGE.upper()}")
    print(f"[INFO] Range: {start_dt.isoformat()} -> {end_dt.isoformat()}")
    print(f"[INFO] Expected candles: ~{days * 24 * 60 // minutes}")
    print()

    df = fetch_range(exchange, symbol, timeframe, since_ms, end_ms)

    print(f"\n[INFO] Final range: {df['time'].iloc[0]} -> {df['time'].iloc[-1]}")
    print(f"[INFO] Total candles: {len(df)}")
    return df


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    os.makedirs("data", exist_ok=True)
    safe_name = DATA_SYMBOL.replace("/", "").lower()
    out_path = f"data/{safe_name}_{INTERVAL}m_{days}d.csv"

    try:
        df = download(DATA_SYMBOL, INTERVAL + "m", days)
        df.to_csv(out_path, index=False)
        print(f"\n[OK] Saved {len(df)} candles to {out_path}")
    except Exception as e:
        print(f"\n[FATAL] Download failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()