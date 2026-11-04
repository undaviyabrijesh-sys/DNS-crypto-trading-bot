from __future__ import annotations

from dataclasses import asdict, dataclass
import pandas as pd


@dataclass
class StructureEvent:
    index: int
    timestamp: str
    event: str
    direction: str
    level: float
    pivot_index: int


def detect_market_structure(
    df: pd.DataFrame, left: int = 3, right: int = 3
) -> list[StructureEvent]:
    """Return confirmed swing and BOS/CHoCH events without look-ahead.

    A pivot at p becomes usable only at p + right. A break is confirmed by
    candle close beyond the latest confirmed swing. The first break establishes
    trend; a break against the established trend is labelled CHoCH.
    """
    required = {"high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing OHLC columns: {sorted(missing)}")
    if left < 1 or right < 1:
        raise ValueError("left and right must be positive integers")
    if len(df) < left + right + 2:
        return []

    events: list[StructureEvent] = []
    last_high: tuple[int, float] | None = None
    last_low: tuple[int, float] | None = None
    trend = "neutral"
    broken_high: int | None = None
    broken_low: int | None = None

    for i in range(len(df)):
        pivot = i - right
        if pivot >= left:
            window = df.iloc[pivot-left:pivot+right+1]
            row = df.iloc[pivot]
            stamp = str(df.iloc[i].get("timestamp", i))
            if float(row["high"]) >= float(window["high"].max()):
                last_high = (pivot, float(row["high"]))
                events.append(StructureEvent(i, stamp, "SWING_HIGH", "bearish",
                                              last_high[1], pivot))
            if float(row["low"]) <= float(window["low"].min()):
                last_low = (pivot, float(row["low"]))
                events.append(StructureEvent(i, stamp, "SWING_LOW", "bullish",
                                              last_low[1], pivot))

        close = float(df.iloc[i]["close"])
        stamp = str(df.iloc[i].get("timestamp", i))
        if last_high and broken_high != last_high[0] and close > last_high[1]:
            event = "BOS" if trend in ("neutral", "bullish") else "CHOCH"
            trend = "bullish"
            broken_high = last_high[0]
            events.append(StructureEvent(i, stamp, event, "bullish",
                                          last_high[1], last_high[0]))
        if last_low and broken_low != last_low[0] and close < last_low[1]:
            event = "BOS" if trend in ("neutral", "bearish") else "CHOCH"
            trend = "bearish"
            broken_low = last_low[0]
            events.append(StructureEvent(i, stamp, event, "bearish",
                                          last_low[1], last_low[0]))
    return events


def structure_events_frame(events: list[StructureEvent]) -> pd.DataFrame:
    return pd.DataFrame([asdict(event) for event in events])
