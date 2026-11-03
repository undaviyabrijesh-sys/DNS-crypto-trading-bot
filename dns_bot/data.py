from __future__ import annotations

import ccxt
import pandas as pd


SUPPORTED_DEFAULTS = {"BTC/USDT", "ETH/USDT"}


def fetch_ohlcv(
    exchange_id: str = "binance",
    symbol: str = "BTC/USDT",
    timeframe: str = "5m",
    limit: int = 500,
) -> pd.DataFrame:
    """Fetch public OHLCV candles. No API key is required."""
    if limit < 50:
        raise ValueError("limit must be at least 50 candles")
    exchange_class = getattr(ccxt, exchange_id, None)
    if exchange_class is None:
        raise ValueError(f"Unsupported CCXT exchange: {exchange_id}")
    exchange = exchange_class({"enableRateLimit": True})
    if not exchange.has.get("fetchOHLCV"):
        raise ValueError(f"{exchange_id} does not support OHLCV via CCXT")
    rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    if not rows:
        raise RuntimeError(f"No OHLCV returned for {symbol} {timeframe}")
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
