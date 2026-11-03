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
    # Shift one 4h bar so a lower-timeframe candle never sees a still-forming HTF bar.
    htf["trend"] = htf["trend"].shift(1).fillna(False)
    return df["timestamp"].map(htf["trend"]).fillna(False).astype(bool)


def _zone_bounds(zone):
    return min(zone.proximal, zone.distal), max(zone.proximal, zone.distal)


def _zone_score(zone, aligned: bool, overlapping: bool, atr_pct: float) -> int:
    # Transparent rule score, not a trained probability.
    score = 30  # fresh at the time it is first detected
    score += 25 if zone.strength >= 0.65 else 12 if zone.strength >= 0.45 else 0
    score += 20 if aligned else 0
    score += 15 if overlapping else 0
    score += 10 if atr_pct < 0.025 else 0
    return score


def run_backtest(
    df: pd.DataFrame,
    symbol: str = "BTC/USDT",
    fee_bps: float = 5.0,
    slippage_bps: float = 2.0,
    target_r: float = 2.0,
    min_score: int = 50,
    max_bars_in_trade: int = 96,
    max_zone_touches: int = 2,
) -> tuple[pd.DataFrame, dict]:
    """Causal, one-position-at-a-time OHLC backtest.

    Signal: first zone retest, then a later candle closes beyond the touch
    candle's opposite extreme. Entry is next candle open. SL is beyond the
    touch extreme by 0.1 ATR. If SL and TP both occur in one candle, SL wins.
    """
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        raise ValueError(f"Data missing columns: {sorted(required - set(df.columns))}")
    if len(df) < 300:
        raise ValueError("Need at least 300 candles for a meaningful run")

    data = df.copy().reset_index(drop=True)
    data["atr"] = (data["high"] - data["low"]).rolling(14).mean()
    data["trend_up"] = _trend_flags(data)
    active, seen = [], set()
    trades: list[Trade] = []
    position = None
    pending = None

    for i in range(60, len(data) - 1):
        row = data.iloc[i]
        stamp = str(row["timestamp"])

        # Detect zones using only data available at this candle close.
        prefix = data.iloc[:i + 1]
        found = detect_fvg_zones(prefix) + detect_base_leg_zones(prefix)
        for z in found:
            key = (z.kind, z.method, z.created_at, round(z.proximal, 8), round(z.distal, 8))
            if key not in seen and z.created_at == stamp:
                seen.add(key)
                active.append({"zone": z, "touches": 0, "touch_idx": None,
                               "touch_high": None, "touch_low": None, "invalid": False})

        # Enter only on the next bar after a valid confirmation close.
        if pending and position is None:
            side = pending["side"]
            entry = float(row["open"])
            stop = pending["stop"]
            risk = abs(entry - stop)
            if risk > 0:
                target = entry + target_r * risk if side == "long" else entry - target_r * risk
                position = {**pending, "entry": entry, "stop": stop, "target": target,
                            "entry_idx": i, "entry_time": stamp}
            pending = None

        # Manage open trade using conservative stop-first intrabar assumptions.
        if position:
            hit_sl = float(row["low"]) <= position["stop"] if position["side"] == "long" else float(row["high"]) >= position["stop"]
            hit_tp = float(row["high"]) >= position["target"] if position["side"] == "long" else float(row["low"]) <= position["target"]
            timed_out = i - position["entry_idx"] >= max_bars_in_trade
            if hit_sl or hit_tp or timed_out:
                if hit_sl:
                    exit_price, reason = position["stop"], "stop"
                elif hit_tp:
                    exit_price, reason = position["target"], "target"
                else:
                    exit_price, reason = float(row["close"]), "time"
                raw_r = ((exit_price - position["entry"]) / abs(position["entry"] - position["stop"])) * (1 if position["side"] == "long" else -1)
                costs = 2 * (fee_bps + slippage_bps) / 10000 * position["entry"] / abs(position["entry"] - position["stop"])
                trades.append(Trade(
                    symbol, position["side"], position["zone"].method, position["zone"].pattern,
                    position["zone"].created_at, position["entry_time"], stamp,
                    position["entry"], position["stop"], position["target"], exit_price,
                    raw_r, raw_r - costs, reason, position["score"], position["aligned"],
                    position["touch_number"]
                ))
                position = None

        if position or pending:
            continue

        # Update each zone in chronological order; no future candle is inspected.
        for state in active:
            z = state["zone"]
            if state["invalid"] or state["touches"] >= max_zone_touches:
                continue
            lo, hi = _zone_bounds(z)
            intersects = float(row["low"]) <= hi and float(row["high"]) >= lo
            if state["touch_idx"] is None:
                if not intersects or i <= (z.base_end if z.method == "base_leg" else i - 1):
                    continue
                state["touches"] += 1
                state["touch_idx"] = i
                state["touch_high"] = float(row["high"])
                state["touch_low"] = float(row["low"])
                continue

            # A close beyond the touch candle extreme is confirmation.
            aligned = bool(row["trend_up"]) if z.kind == "demand" else not bool(row["trend_up"])
            if z.kind == "demand":
                confirmed = float(row["close"]) > state["touch_high"]
            else:
                confirmed = float(row["close"]) < state["touch_low"]

            # If price decisively closes through the distal edge, invalidate.
            if (z.kind == "demand" and float(row["close"]) < lo) or (z.kind == "supply" and float(row["close"]) > hi):
                state["invalid"] = True
                continue

            if confirmed and i > state["touch_idx"] and i < len(data) - 1:
                atr = float(row["atr"]) if pd.notna(row["atr"]) else float(row["high"] - row["low"])
                stop = state["touch_low"] - 0.1 * atr if z.kind == "demand" else state["touch_high"] + 0.1 * atr
                # Nearby same-direction zones add confluence, using only known zones.
                overlapping = any(
                    other is not state and other["zone"].kind == z.kind
                    and abs(other["zone"].proximal - z.proximal) / max(abs(z.proximal), 1e-9) < 0.002
                    for other in active
                )
                atr_pct = atr / max(float(row["close"]), 1e-9)
                score = _zone_score(z, aligned, overlapping, atr_pct)
                if score >= min_score and (aligned or score >= min_score + 15):
                    pending = {
                        "side": "long" if z.kind == "demand" else "short",
                        "stop": stop, "zone": z, "score": score,
                        "aligned": aligned, "touch_number": state["touches"]
                    }
                state["touch_idx"] = None
                state["touch_high"] = None
                state["touch_low"] = None
                break

    trades_df = pd.DataFrame([asdict(t) for t in trades])
    if trades_df.empty:
        metrics = {"trades": 0, "message": "No completed trades under the selected rules."}
        return trades_df, metrics

    wins = trades_df[trades_df["net_result_r"] > 0]
    losses = trades_df[trades_df["net_result_r"] <= 0]
    equity = (1 + trades_df["net_result_r"] * 0.01).cumprod()
    drawdown = equity / equity.cummax() - 1
    gross_win = wins["net_result_r"].sum()
    gross_loss = abs(losses["net_result_r"].sum())
    metrics = {
        "symbol": symbol,
        "trades": int(len(trades_df)),
        "win_rate_pct": round(len(wins) / len(trades_df) * 100, 2),
        "net_expectancy_r": round(float(trades_df["net_result_r"].mean()), 4),
        "profit_factor": round(float(gross_win / gross_loss), 3) if gross_loss else None,
        "net_total_r": round(float(trades_df["net_result_r"].sum()), 2),
        "max_drawdown_pct_at_1pct_risk": round(float(drawdown.min() * 100), 2),
        "avg_win_r": round(float(wins["net_result_r"].mean()), 3) if len(wins) else 0,
        "avg_loss_r": round(float(losses["net_result_r"].mean()), 3) if len(losses) else 0,
        "stop_rate_pct": round(float((trades_df["exit_reason"] == "stop").mean() * 100), 2),
        "target_rate_pct": round(float((trades_df["exit_reason"] == "target").mean() * 100), 2),
    }
    return trades_df, metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--min-score", type=int, default=50)
    parser.add_argument("--output", default="backtest_results")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    df = fetch_history(args.exchange, args.symbol, args.timeframe, args.days)
    df.to_csv(out / "candles.csv", index=False)
    trades, metrics = run_backtest(df, symbol=args.symbol, min_score=args.min_score)
    trades.to_csv(out / "trades.csv", index=False)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps({"candles": len(df), "from": str(df.timestamp.min()),
                      "to": str(df.timestamp.max()), "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
