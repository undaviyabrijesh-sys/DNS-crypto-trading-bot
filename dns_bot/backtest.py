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
    if exchange_id.lower() in {"deltaindia", "delta_india"}:
        from dns_bot.delta_data import fetch_delta_history
        return fetch_delta_history(symbol=symbol, timeframe=timeframe, days=days)
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})
    if not exchange.has.get("fetchOHLCV"):
        raise RuntimeError(f"{exchange_id} does not support fetchOHLCV")
    now = exchange.milliseconds()
    since = now - days * 24 * 60 * 60 * 1000
    rows, last = [], None
    while since < now:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
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
    ms = exchange.parse_timeframe(timeframe) * 1000
    df = df[df["timestamp"].astype("int64") // 10**6 + ms <= now].reset_index(drop=True)
    return df


def _trend_flags(df: pd.DataFrame) -> pd.Series:
    """Causal 4h trend proxy based on the last completed 4h close vs 20 bars ago."""
    htf = df.set_index("timestamp").resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    htf["trend"] = (htf["close"] > htf["close"].shift(20)).shift(1).fillna(False)
    htf = htf.rename_axis("htf_time").reset_index()
    aligned = pd.merge_asof(
        df[["timestamp"]].sort_values("timestamp"),
        htf[["htf_time", "trend"]].sort_values("htf_time"),
        left_on="timestamp", right_on="htf_time", direction="backward"
    )
    return aligned["trend"].fillna(False).astype(bool).set_axis(df.index)


def _daily_curve_position(df: pd.DataFrame) -> pd.Series:
    """Current close location within the prior 20 completed daily bars' range."""
    daily = df.set_index("timestamp").resample("1D").agg({"high": "max", "low": "min"}).dropna()
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


def _bounds(zone):
    return min(zone.proximal, zone.distal), max(zone.proximal, zone.distal)


def _zone_score(zone, aligned: bool, overlapping: bool, original: bool,
                in_curve_location: bool) -> int:
    # Rule-based ranking only. This is not a trained probability.
    score = 25  # zone is fresh on its first retest
    score += 20 if zone.strength >= 0.65 else 10 if zone.strength >= 0.45 else 0
    score += 15 if aligned else 0
    score += 15 if overlapping else 0
    score += 10 if original else 0
    score += 15 if in_curve_location else 0
    return score


def run_backtest(
    df: pd.DataFrame,
    symbol: str = "BTC/USDT",
    fee_bps: float = 5.0,
    slippage_bps: float = 2.0,
    target_r: float = 3.0,
    min_score: int = 50,
    max_bars_in_trade: int = 96,
    max_zone_touches: int = 1,
    require_curve: bool = True,
    require_trend: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Causal, one-position-at-a-time OHLC backtest.

    Detect zones using only candles closed at the current index. First retest
    starts a setup; confirmation must close beyond the touch candle extreme.
    Enter at the next candle open. Stop sits 0.1 ATR beyond the touch extreme.
    If SL and TP are both inside one candle, stop is assumed first.
    """
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        raise ValueError(f"Data missing columns: {sorted(required - set(df.columns))}")
    if len(df) < 300:
        raise ValueError("Need at least 300 candles for a meaningful run")

    data = df.copy().reset_index(drop=True)
    data["atr"] = (data["high"] - data["low"]).rolling(14).mean()
    data["trend_up"] = _trend_flags(data)
    data["curve_position"] = _daily_curve_position(data)

    active, seen = [], set()
    trades: list[Trade] = []
    position = None
    pending = None

    for i in range(60, len(data) - 1):
        row = data.iloc[i]
        stamp = str(row["timestamp"])

        # FVG requires three bars; base/leg requires only its local base and
        # rolling-range context. The bounded prefix avoids O(n^2) full-history scans.
        local = data.iloc[max(0, i - 25):i + 1]
        found = detect_fvg_zones(local.tail(3)) + detect_base_leg_zones(local, only_latest=True)
        for zone in found:
            key = (zone.kind, zone.method, zone.created_at,
                   round(zone.proximal, 8), round(zone.distal, 8))
            if key not in seen and zone.created_at == stamp:
                seen.add(key)
                active.append({"zone": zone, "touches": 0, "touch_idx": None,
                               "touch_high": None, "touch_low": None, "invalid": False})

        # Pending confirmation enters at this candle's open.
        if pending and position is None:
            entry = float(row["open"])
            risk = abs(entry - pending["stop"])
            if risk > 0:
                side = pending["side"]
                target = entry + target_r * risk if side == "long" else entry - target_r * risk
                position = {**pending, "entry": entry, "target": target,
                            "entry_idx": i, "entry_time": stamp}
            pending = None

        if position:
            hit_sl = (float(row["low"]) <= position["stop"] if position["side"] == "long"
                      else float(row["high"]) >= position["stop"])
            hit_tp = (float(row["high"]) >= position["target"] if position["side"] == "long"
                      else float(row["low"]) <= position["target"])
            timed_out = i - position["entry_idx"] >= max_bars_in_trade
            if hit_sl or hit_tp or timed_out:
                if hit_sl:
                    exit_price, reason = position["stop"], "stop"
                elif hit_tp:
                    exit_price, reason = position["target"], "target"
                else:
                    exit_price, reason = float(row["close"]), "time"
                direction = 1 if position["side"] == "long" else -1
                raw_r = (exit_price - position["entry"]) / abs(position["entry"] - position["stop"]) * direction
                costs = (2 * (fee_bps + slippage_bps) / 10000
                         * position["entry"] / abs(position["entry"] - position["stop"]))
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

        for state in active:
            zone = state["zone"]
            if state["invalid"] or state["touches"] >= max_zone_touches:
                continue
            low_bound, high_bound = _bounds(zone)
            intersects = float(row["low"]) <= high_bound and float(row["high"]) >= low_bound

            if state["touch_idx"] is None:
                # Zone cannot be retested on the same bar that created it.
                if not intersects or zone.created_at == stamp:
                    continue
                state["touches"] += 1
                state["touch_idx"] = i
                state["touch_high"] = float(row["high"])
                state["touch_low"] = float(row["low"])
                continue

            if zone.kind == "demand":
                confirmed = float(row["close"]) > state["touch_high"]
                invalid = float(row["close"]) < low_bound
                side = "long"
            else:
                confirmed = float(row["close"]) < state["touch_low"]
                invalid = float(row["close"]) > high_bound
                side = "short"

            if invalid:
                state["invalid"] = True
                continue

            if confirmed and i > state["touch_idx"]:
                atr = float(row["atr"]) if pd.notna(row["atr"]) else float(row["high"] - row["low"])
                stop = (state["touch_low"] - 0.1 * atr if side == "long"
                        else state["touch_high"] + 0.1 * atr)
                overlapping = any(
                    other is not state and other["zone"].kind == zone.kind
                    and max(_bounds(other["zone"])[0], low_bound)
                        <= min(_bounds(other["zone"])[1], high_bound)
                    for other in active
                )
                original = not overlapping
                aligned = bool(row["trend_up"]) if side == "long" else not bool(row["trend_up"])
                curve = row["curve_position"]
                in_curve = (pd.notna(curve) and
                            (float(curve) <= 0.50 if side == "long" else float(curve) >= 0.50))
                score = _zone_score(zone, aligned, overlapping, original, bool(in_curve))
                trend_ok = aligned or (
                    zone.pattern in ("DBR", "RBD") and score >= min_score + 15
                )
                # Permissive research mode can relax context filters, but never
                # relaxes the causal retest/close-confirmation/next-open entry.
                curve_ok = in_curve or not require_curve
                trend_filter_ok = trend_ok or not require_trend
                if score >= min_score and curve_ok and trend_filter_ok:
                    pending = {"side": side, "stop": stop, "zone": zone, "score": score,
                               "aligned": aligned, "touch_number": state["touches"]}
                state["touch_idx"] = None
                state["touch_high"] = None
                state["touch_low"] = None
                break

    trades_df = pd.DataFrame([asdict(trade) for trade in trades])
    if trades_df.empty:
        return trades_df, {"symbol": symbol, "trades": 0,
                           "message": "No completed trades under these rules."}

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
    parser.add_argument("--exchange", default="okx")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--min-score", type=int, default=50)
    parser.add_argument("--output", default="backtest_results")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    candles = fetch_history(args.exchange, args.symbol, args.timeframe, args.days)
    candles.to_csv(out / "candles.csv", index=False)

    variants = {
        "strict_3R": {"target_r": 3.0, "min_score": args.min_score + 10,
                      "require_curve": True, "require_trend": True, "max_zone_touches": 1},
        "balanced_2R": {"target_r": 2.0, "min_score": args.min_score,
                        "require_curve": True, "require_trend": True, "max_zone_touches": 1},
        "looser_2R": {"target_r": 2.0, "min_score": max(0, args.min_score - 20),
                      "require_curve": False, "require_trend": False, "max_zone_touches": 2},
        "imperfect_2R": {"target_r": 2.0, "min_score": 25,
                         "require_curve": False, "require_trend": False, "max_zone_touches": 2},
    }
    comparison = {}
    for name, config in variants.items():
        trades, metrics = run_backtest(
            candles, symbol=args.symbol, min_score=config["min_score"],
            target_r=config["target_r"], require_curve=config["require_curve"],
            require_trend=config["require_trend"], max_zone_touches=config["max_zone_touches"]
        )
        trades.to_csv(out / f"{name}_trades.csv", index=False)
        comparison[name] = metrics
    (out / "metrics.json").write_text(json.dumps(comparison, indent=2))
    print(json.dumps({
        "candles": len(candles), "from": str(candles.timestamp.min()),
        "to": str(candles.timestamp.max()), "comparison": comparison
    }, indent=2))


if __name__ == "__main__":
    main()
