from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd

from dns_bot.zones import detect_fvg_zones, detect_base_leg_zones


@dataclass
class Trade:
    symbol: str
    side: str
    zone_method: str
    zone_pattern: str
    zone_created: str
    entry_time: str
    exit_time: str
    entry: float
    stop: float
    target: float
    exit_price: float
    result_r: float
    net_result_r: float
    exit_reason: str
    zone_score: int
    trend_aligned: bool
    touch_number: int


def fetch_history(exchange_id: str, symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """Paginated public OHLCV download; excludes the currently forming candle."""
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})
    if not exchange.has.get("fetchOHLCV"):
        raise RuntimeError(f"{exchange_id} does not support fetchOHLCV")
    now = exchange.milliseconds()
    since = now - days * 24 * 60 * 60 * 1000
    rows, last = [], None
    limit = 1000
    while since < now:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        if not batch:
            break
        rows.extend(batch)
        newest = batch[-1][0]
        if last == newest or newest < since:
            break
        last = newest
        since = newest + 1
        if len(batch) < 2:
            break
    if not rows:
        raise RuntimeError("Exchange returned no historical candles")
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    # Exclude a candle that may still be forming.
    ms = exchange.parse_timeframe(timeframe) * 1000
    df = df[df["timestamp"].astype("int64") // 10**6 + ms <= now].reset_index(drop=True)
    return df


def _trend_flags(df: pd.DataFrame) -> pd.Series:
    """Causal 4h trend proxy: last completed 4h close vs 20 completed 4h bars ago."""
    htf = df.set_index("timestamp").resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    htf["trend"] = htf["close"] > htf["close"].shift(20)
    # A 4h bar's value becomes usable only after that bar has closed.
    htf["trend"] = htf["trend"].shift(1).fillna(False)
    htf = htf.rename_axis("htf_time").reset_index()
    aligned = pd.merge_asof(
        df[["timestamp"]].sort_values("timestamp"),
        htf[["htf_time", "trend"]].sort_values("htf_time"),
        left_on="timestamp", right_on="htf_time", direction="backward"
    )
    return aligned["trend"].fillna(False).astype(bool).set_axis(df.index)


def _daily_curve_position(df: pd.DataFrame) -> pd.Series:
    """Current close position inside the prior 20 completed daily bars' range."""
    daily = df.set_index("timestamp").resample("1D").agg(
        {"high": "max", "low": "min"}
    ).dropna()
    prior_high = daily["high"].rolling(20, min_periods=5).max().shift(1)
    prior_low = daily["low"].rolling(20, min_periods=5).min().shift(1)
    levels = pd.DataFrame({
        "daily_time": daily.index,
        "prior_high": prior_high.values,
        "prior_low": prior_low.values,
    }).dropna()
    aligned = pd.merge_asof(
        df[["timestamp", "close"]].sort_values("timestamp"),
        levels.sort_values("daily_time"),
        left_on="timestamp", right_on="daily_time", direction="backward"
    )
    width = (aligned["prior_high"] - aligned["prior_low"]).replace(0, np.nan)
    return ((aligned["close"] - aligned["prior_low"]) / width).set_axis(df.index)
    variants = {
        "strict_3R": {"target_r": 3.0, "min_score": args.min_score + 10},
        "balanced_2R": {"target_r": 2.0, "min_score": args.min_score},
        "looser_2R": {"target_r": 2.0, "min_score": max(0, args.min_score - 20)},
    }
    comparison = {}
    for name, config in variants.items():
        trades, metrics = run_backtest(
            df, symbol=args.symbol, min_score=config["min_score"],
            target_r=config["target_r"]
        )
        trades.to_csv(out / f"{name}_trades.csv", index=False)
        comparison[name] = metrics
    (out / "metrics.json").write_text(json.dumps(comparison, indent=2))

