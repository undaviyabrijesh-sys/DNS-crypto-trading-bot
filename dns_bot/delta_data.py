from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import requests

BASE_URL = "https://api.india.delta.exchange"
SYMBOL = "BTCUSD"
SUPPORTED_RESOLUTIONS = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "1d", "1w"}


class DeltaAPIError(RuntimeError):
    pass


def fetch_delta_history(symbol: str = SYMBOL, timeframe: str = "15m",
                        days: int = 365, end_time: int | None = None) -> pd.DataFrame:
    """Fetch public Delta India OHLCV in <=2000-candle windows.

    Delta timestamps are Unix seconds. The returned frame follows the
    project's standard UTC timestamp/open/high/low/close/volume schema.
    """
    if timeframe not in SUPPORTED_RESOLUTIONS:
        raise ValueError(f"Unsupported Delta resolution: {timeframe}")
    if days <= 0:
        raise ValueError("days must be positive")
    end_ts = int(end_time or time.time())
    start_ts = end_ts - int(days * 86400)
    seconds = _resolution_seconds(timeframe)
    max_window = seconds * 1999
    rows: list[dict] = []
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": "dns-crypto-trading-bot/1.0"})
    cursor = start_ts
    while cursor < end_ts:
        window_end = min(end_ts, cursor + max_window)
        response = session.get(
            f"{BASE_URL}/v2/history/candles",
            params={"resolution": timeframe, "symbol": symbol,
                    "start": cursor, "end": window_end},
            timeout=(5, 30),
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success", False):
            raise DeltaAPIError(f"Delta candle API returned unsuccessful response: {payload}")
        batch = payload.get("result") or []
        rows.extend(batch)
        cursor = window_end + 1
    if not rows:
        raise DeltaAPIError(f"No Delta candles returned for {symbol} / {timeframe}")
    frame = pd.DataFrame(rows)
    required = {"time", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise DeltaAPIError(f"Delta candle response missing fields: {sorted(missing)}")
    if "volume" not in frame:
        frame["volume"] = 0.0
    frame = frame.rename(columns={"time": "timestamp"})
    frame["timestamp"] = pd.to_datetime(pd.to_numeric(frame["timestamp"]), unit="s", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = (frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
                   .drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True))
    # Exclude the still-forming candle.
    frame = frame[frame["timestamp"] + pd.to_timedelta(seconds, unit="s")
                  <= pd.Timestamp(end_ts, unit="s", tz="UTC")].reset_index(drop=True)
    if frame.empty:
        raise DeltaAPIError("Delta returned no completed candles after filtering")
    return frame[["timestamp", "open", "high", "low", "close", "volume"]]


def _resolution_seconds(resolution: str) -> int:
    if resolution.endswith("m"):
        return int(resolution[:-1]) * 60
    if resolution.endswith("h"):
        return int(resolution[:-1]) * 3600
    if resolution.endswith("d"):
        return int(resolution[:-1]) * 86400
    if resolution.endswith("w"):
        return int(resolution[:-1]) * 604800
    raise ValueError(f"Unsupported resolution: {resolution}")
