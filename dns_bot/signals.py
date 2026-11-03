from __future__ import annotations

from dataclasses import dataclass
from .zones import Zone


@dataclass
class Signal:
    side: str
    entry: float
    stop: float
    zone_method: str
    zone_pattern: str
    zone_created_at: str
    touch_candle_index: int
    confirmation_index: int


def confirmation_signal(candles, zone: Zone, start_index: int | None = None) -> Signal | None:
    """Return a signal only when a closed candle confirms the most-extreme touch.

    Demand: touch candle has the lowest low; a later candle closes above its high.
    Supply: touch candle has the highest high; a later candle closes below its low.
    Entry is the next candle open. Caller must provide the next candle (no lookahead).
    """
    start = max(zone.base_end + 1, start_index or zone.base_end + 1)
    touches = []
    for i in range(start, len(candles) - 1):
        row = candles.iloc[i]
        intersects = float(row["low"]) <= zone.proximal and float(row["high"]) >= zone.distal
        if not intersects:
            continue
        if zone.kind == "demand" and float(row["low"]) <= zone.proximal:
            touches.append((i, float(row["low"]), float(row["high"])))
        elif zone.kind == "supply" and float(row["high"]) >= zone.distal:
            touches.append((i, float(row["high"]), float(row["low"])))

    if not touches:
        return None

    if zone.kind == "demand":
        touch_idx, _, touch_high = min(touches, key=lambda x: x[1])
        for i in range(touch_idx + 1, len(candles) - 1):
            if float(candles.iloc[i]["close"]) > touch_high:
                entry = float(candles.iloc[i + 1]["open"])
                return Signal("long", entry, float(candles.iloc[touch_idx]["low"]),
                              zone.method, zone.pattern, zone.created_at, touch_idx, i)
    else:
        touch_idx, _, touch_low = max(touches, key=lambda x: x[1])
        for i in range(touch_idx + 1, len(candles) - 1):
            if float(candles.iloc[i]["close"]) < touch_low:
                entry = float(candles.iloc[i + 1]["open"])
                return Signal("short", entry, float(candles.iloc[touch_idx]["high"]),
                              zone.method, zone.pattern, zone.created_at, touch_idx, i)
    return None
