from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal
import pandas as pd

ZoneType = Literal["demand", "supply"]

@dataclass
class Zone:
    kind: ZoneType
    method: str
    proximal: float
    distal: float
    created_at: str
    base_start: int
    base_end: int
    strength: float
    pattern: str
    touches: int = 0
    status: str = "fresh"
    defended_retests: int = 0
    score: float = 0.0
    created_index: int = -1

    def to_dict(self) -> dict:
        return asdict(self)


def _valid_ohlc(df: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing OHLC columns: {sorted(missing)}")
    if len(df) < 3:
        raise ValueError("At least three candles are required")


def detect_fvg_zones(df: pd.DataFrame) -> list[Zone]:
    """Detect three-candle gaps using the completed formation candle."""
    _valid_ohlc(df)
    zones: list[Zone] = []
    for i in range(2, len(df)):
        first, third = df.iloc[i - 2], df.iloc[i]
        stamp = str(df.iloc[i].get("timestamp", i))
        if float(third["low"]) > float(first["high"]):
            zones.append(Zone("demand", "fvg", float(first["high"]), float(first["low"]),
                              stamp, i - 2, i - 2, 1.0, "FVG", created_index=i))
        elif float(third["high"]) < float(first["low"]):
            zones.append(Zone("supply", "fvg", float(first["low"]), float(first["high"]),
                              stamp, i - 2, i - 2, 1.0, "FVG", created_index=i))
    return zones


def _body_ratio(row: pd.Series) -> float:
    candle_range = float(row["high"] - row["low"])
    return abs(float(row["close"] - row["open"])) / candle_range if candle_range > 0 else 0.0


def detect_base_leg_zones(df: pd.DataFrame, max_base: int = 5, range_lookback: int = 20,
                          leg_body_ratio: float = 0.75, base_body_ratio: float = 0.50,
                          expansion: float = 1.20) -> list[Zone]:
    """Detect DBR/RBR/RBD/DBD structures using closed OHLC candles (proxy)."""
    _valid_ohlc(df)
    if max_base < 1 or max_base > 6:
        raise ValueError("max_base must be between 1 and 6")
    ranges = (df["high"] - df["low"]).astype(float)
    median_ranges = ranges.rolling(range_lookback, min_periods=3).median()
    zones: list[Zone] = []
    seen: set[tuple[int, int]] = set()
    for base_len in range(1, max_base + 1):
        for start in range(1, len(df) - base_len):
            end = start + base_len - 1
            leg_out_idx = end + 1
            if (start, end) in seen:
                continue
            base = df.iloc[start:end + 1]
            if not all(_body_ratio(row) <= base_body_ratio for _, row in base.iterrows()):
                continue
            leg_in, leg_out = df.iloc[start - 1], df.iloc[leg_out_idx]
            if _body_ratio(leg_in) < leg_body_ratio:
                continue
            out_range, median = float(ranges.iloc[leg_out_idx]), median_ranges.iloc[leg_out_idx]
            if pd.isna(median) or out_range < float(median) * expansion:
                continue
            if _body_ratio(leg_out) < leg_body_ratio:
                continue
            in_up = float(leg_in["close"]) > float(leg_in["open"])
            out_up = float(leg_out["close"]) > float(leg_out["open"])
            if out_up:
                kind: ZoneType = "demand"
                pattern = "RBR" if in_up else "DBR"
                proximal = float(base[["open", "close"]].max(axis=1).max())
                distal = float(base["low"].min())
            else:
                kind = "supply"
                pattern = "DBD" if not in_up else "RBD"
                proximal = float(base[["open", "close"]].min(axis=1).min())
                distal = float(base["high"].max())
            if kind == "demand" and proximal <= distal:
                continue
            if kind == "supply" and proximal >= distal:
                continue
            strength = min(1.0, _body_ratio(leg_out) * min(out_range / float(median), 2.0) / 2.0)
            stamp = str(df.iloc[leg_out_idx].get("timestamp", leg_out_idx))
            zones.append(Zone(kind, "base_leg", proximal, distal, stamp, start, end,
                              strength, pattern, created_index=leg_out_idx))
            seen.add((start, end))
    unique: dict[tuple, Zone] = {}
    for zone in zones:
        key = (zone.kind, round(zone.proximal, 8), round(zone.distal, 8),
               zone.base_start, zone.base_end)
        unique[key] = zone
    return list(unique.values())


def _track_one_zone(df: pd.DataFrame, zone: Zone, start_index: int) -> tuple[Zone, Zone | None]:
    low, high = sorted((float(zone.distal), float(zone.proximal)))
    pending_touch = False
    touches = defended = 0
    broken_at = None
    for i in range(start_index + 1, len(df)):
        candle = df.iloc[i]
        candle_low, candle_high, close = float(candle["low"]), float(candle["high"]), float(candle["close"])
        if zone.kind == "demand" and close < low:
            broken_at = i
            break
        if zone.kind == "supply" and close > high:
            broken_at = i
            break
        overlaps = candle_low <= high and candle_high >= low
        if overlaps:
            if not pending_touch:
                touches += 1
            pending_touch = True
            if (zone.kind == "demand" and close > high) or (zone.kind == "supply" and close < low):
                defended += 1
                pending_touch = False
        elif pending_touch:
            if (zone.kind == "demand" and close > high) or (zone.kind == "supply" and close < low):
                defended += 1
            pending_touch = False
    zone.touches = touches
    zone.defended_retests = defended
    # Only defended reactions increase score; an unreacted touch adds nothing.
    zone.score = round(min(1.0, max(0.0, float(zone.strength)) * 0.70
                           + min(defended, 3) * 0.10), 4)
    if broken_at is not None:
        zone.status = "broken"
        flip_kind: ZoneType = "supply" if zone.kind == "demand" else "demand"
        flip_label = "SBR" if zone.kind == "demand" else "RBS"
        stamp = str(df.iloc[broken_at].get("timestamp", broken_at))
        flip = Zone(flip_kind, "flip", zone.proximal, zone.distal, stamp,
                    zone.base_start, zone.base_end, zone.strength * 0.70,
                    flip_label, status=flip_label, created_index=broken_at)
        return zone, flip
    zone.status = "tested" if touches else "fresh"
    return zone, None


def track_zone_lifecycle(df: pd.DataFrame, zones: list[Zone]) -> list[Zone]:
    """Track defended retests, invalidation and causal SBR/RBS flips."""
    _valid_ohlc(df)
    tracked: list[Zone] = []
    for zone in zones:
        start = zone.created_index
        if start < 0 or start >= len(df):
            if "timestamp" in df.columns:
                matches = [i for i, value in enumerate(df["timestamp"].astype(str))
                           if value == str(zone.created_at)]
                start = matches[-1] if matches else max(0, min(len(df) - 1, zone.base_end + 2))
            else:
                try:
                    start = max(0, min(len(df) - 1, int(zone.created_at)))
                except (TypeError, ValueError):
                    start = max(0, min(len(df) - 1, zone.base_end + 2))
        original, flip = _track_one_zone(df, zone, start)
        tracked.append(original)
        if flip is not None:
            flip, _ = _track_one_zone(df, flip, flip.created_index)
            tracked.append(flip)
    return tracked
