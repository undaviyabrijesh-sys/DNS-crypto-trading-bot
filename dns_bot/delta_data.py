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

def history_quality(frame: pd.DataFrame, timeframe: str, now=None) -> dict:
    """Summarize internal candle continuity and latest completed-bar age.

    Gap counts describe only intervals between returned candles; missing leading
    or trailing history is not inferred. Staleness is flagged after 2.5 bars
    (with a five-minute minimum), and no missing bars are synthesized.
    """
    if timeframe not in SUPPORTED_RESOLUTIONS:
        raise ValueError(f"Unsupported Delta resolution: {timeframe}")
    if frame is None or frame.empty:
        raise ValueError("Cannot assess an empty candle history")
    if "timestamp" not in frame.columns:
        raise ValueError("Candle history is missing the timestamp column")

    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dropna()
    if timestamps.empty:
        raise ValueError("Candle history has no valid timestamps")
    timestamps = timestamps.sort_values().drop_duplicates().reset_index(drop=True)

    seconds = _resolution_seconds(timeframe)
    deltas = timestamps.diff().dropna().dt.total_seconds()
    gap_intervals = 0
    missing_candles = 0
    irregular_intervals = 0
    for delta in deltas:
        ratio = float(delta) / seconds
        if ratio > 1.0 + 1e-6:
            gap_intervals += 1
            nearest = round(ratio)
            if nearest > 1 and abs(ratio - nearest) <= 1e-6:
                missing_candles += int(nearest - 1)
            else:
                irregular_intervals += 1
        elif ratio < 1.0 - 1e-6:
            irregular_intervals += 1

    reference = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    reference = reference.tz_localize("UTC") if reference.tzinfo is None else reference.tz_convert("UTC")
    latest_open = timestamps.iloc[-1]
    latest_close = latest_open + pd.Timedelta(seconds=seconds)
    age_minutes = (reference - latest_close).total_seconds() / 60.0
    stale_after_minutes = max(5.0, seconds / 60.0 * 2.5)
    has_gaps = gap_intervals > 0 or irregular_intervals > 0
    is_stale = age_minutes > stale_after_minutes
    is_future = age_minutes < -2.0

    return {
        "rows": int(len(timestamps)),
        "gap_intervals": int(gap_intervals),
        "missing_candles": int(missing_candles),
        "irregular_intervals": int(irregular_intervals),
        "has_gaps": bool(has_gaps),
        "latest_open_utc": latest_open.isoformat(),
        "latest_close_utc": latest_close.isoformat(),
        "age_minutes": round(float(age_minutes), 2),
        "stale_after_minutes": round(float(stale_after_minutes), 2),
        "is_stale": bool(is_stale),
        "is_future": bool(is_future),
        "is_usable": bool(not has_gaps and not is_stale and not is_future),
    }
