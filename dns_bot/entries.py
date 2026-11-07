from __future__ import annotations

import math
import pandas as pd


def entry_history_ready(quality_15m: dict, quality_3m: dict) -> bool:
    """Allow setup scans only when both source timeframes pass feed-quality gates."""
    return all(
        isinstance(quality, dict) and quality.get("is_usable") is True
        for quality in (quality_15m, quality_3m)
    )


def atr_3m(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def find_entry_setups(
    candles_3m: pd.DataFrame,
    zones_15m: list,
    buffer_atr: float = 0.25,
    zone_timeframe_minutes: int = 15,
):
    """Find causal 3m touch-candle confirmations against completed 15m zones.

    A zone becomes available only after its 15m formation/confirmation candle
    closes. Demand uses the lowest-low touch candle and requires a later close
    above that candle's high; supply mirrors this with the highest-high touch
    candle. Entries use the following 3m candle open.
    """
    required = {"timestamp", "open", "high", "low", "close"}
    if not required.issubset(candles_3m.columns):
        raise ValueError(f"Missing columns: {sorted(required - set(candles_3m.columns))}")
    if not math.isfinite(float(buffer_atr)) or buffer_atr < 0:
        raise ValueError("buffer_atr must be a finite non-negative number")
    if isinstance(zone_timeframe_minutes, bool) or int(zone_timeframe_minutes) <= 0:
        raise ValueError("zone_timeframe_minutes must be a positive integer")
    if len(candles_3m) < 16:
        return []

    df = candles_3m.reset_index(drop=True).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    if df["timestamp"].isna().any():
        raise ValueError("timestamp values must be valid datetimes")
    if df["timestamp"].duplicated().any() or not df["timestamp"].is_monotonic_increasing:
        raise ValueError("timestamps must be unique and increasing")
    expected_step = pd.Timedelta(minutes=3)
    df["atr"] = atr_3m(df)
    results = []

    for zone in zones_15m:
        kind = str(getattr(zone, "kind", "")).lower()
        if kind not in ("demand", "supply") or str(getattr(zone, "status", "fresh")).lower() == "broken":
            continue

        low, high = sorted((float(zone.proximal), float(zone.distal)))
        origin = pd.to_datetime(getattr(zone, "created_at", None), utc=True, errors="coerce")
        if pd.notna(origin):
            # created_at is the OPEN timestamp of the completed 15m candle
            # that confirmed the zone, so its first causal use is after close.
            available_at = origin + pd.Timedelta(minutes=int(zone_timeframe_minutes))
            eligible = df.index[df["timestamp"] >= available_at]
        else:
            eligible = df.index
        if len(eligible) == 0:
            continue

        touch_idx = None
        touch_low = None
        touch_high = None
        for i in range(max(14, int(eligible[0])), len(df) - 1):
            if i > 0 and df.timestamp.iloc[i] - df.timestamp.iloc[i - 1] != expected_step:
                # Do not carry a touch confirmation across missing 3m candles.
                touch_idx = None
                touch_low = touch_high = None
            candle = df.iloc[i]
            candle_low = float(candle.low)
            candle_high = float(candle.high)
            close = float(candle.close)
            atr = candle.atr
            if pd.isna(atr):
                continue

            intersects = candle_low <= high and candle_high >= low
            if intersects:
                if touch_idx is None:
                    touch_idx = i
                    touch_low, touch_high = candle_low, candle_high
                elif kind == "demand" and candle_low < touch_low:
                    # Keep the most extreme (lowest-low) demand touch candle.
                    touch_idx = i
                    touch_low, touch_high = candle_low, candle_high
                elif kind == "supply" and candle_high > touch_high:
                    # Keep the most extreme (highest-high) supply touch candle.
                    touch_idx = i
                    touch_low, touch_high = candle_low, candle_high

            # A close through the distal boundary invalidates this zone setup.
            if (kind == "demand" and close < low) or (kind == "supply" and close > high):
                break

            # Confirmation must be a later closed candle than the extreme touch.
            if touch_idx is None or i <= touch_idx:
                continue
            if kind == "demand":
                confirmed, side = close > touch_high, "LONG"
                stop = low - float(atr) * float(buffer_atr)
            else:
                confirmed, side = close < touch_low, "SHORT"
                stop = high + float(atr) * float(buffer_atr)
            if not confirmed:
                continue

            if df.timestamp.iloc[i + 1] - df.timestamp.iloc[i] != expected_step:
                # The next-bar entry is not observable when that bar is missing.
                touch_idx = None
                touch_low = touch_high = None
                continue
            entry = float(df.iloc[i + 1].open)
            risk = entry - stop if side == "LONG" else stop - entry
            if risk <= 0:
                # A gap through the planned stop invalidates this entry only;
                # keep scanning for a later independent retest of the same zone.
                touch_idx = None
                touch_low = touch_high = None
                continue

            target_2r = entry + 2 * risk if side == "LONG" else entry - 2 * risk
            candidates = []
            for other in zones_15m:
                if str(getattr(other, "status", "fresh")).lower() == "broken":
                    continue
                other_kind = str(getattr(other, "kind", "")).lower()
                ol, oh = sorted((float(other.proximal), float(other.distal)))
                if side == "LONG" and other_kind == "supply" and ol > entry:
                    candidates.append(ol)
                if side == "SHORT" and other_kind == "demand" and oh < entry:
                    candidates.append(oh)
            final_target = (min(candidates) if side == "LONG" else max(candidates)) if candidates else None
            if final_target is not None:
                rr_zone = (final_target - entry) / risk if side == "LONG" else (entry - final_target) / risk
                if rr_zone < 2:
                    final_target = None
            else:
                rr_zone = None

            results.append({
                "side": side,
                "zone": str(getattr(zone, "pattern", kind)),
                "zone_low": low,
                "zone_high": high,
                "tap_time": str(df.timestamp.iloc[touch_idx]),
                "confirmation_time": str(candle.timestamp),
                "touch_candle_index": int(touch_idx),
                "entry": entry,
                "stop": stop,
                "target_1_2r": target_2r,
                "final_target": final_target,
                "risk": risk,
                "atr_3m": float(atr),
                "buffer": float(atr) * float(buffer_atr),
                "rr_to_zone": rr_zone,
                "status": "CONFIRMED · NEXT 3M OPEN",
            })
            break

    return sorted(results, key=lambda x: x["confirmation_time"], reverse=True)
