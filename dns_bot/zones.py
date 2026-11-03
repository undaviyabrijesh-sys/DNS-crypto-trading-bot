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
    """Detect 3-candle gaps; zone boundaries follow the user's first-candle rule."""
    _valid_ohlc(df)
    zones: list[Zone] = []
    for i in range(2, len(df)):
        first, third = df.iloc[i - 2], df.iloc[i]
        stamp = str(df.iloc[i].get("timestamp", i))
        if float(third["low"]) > float(first["high"]):
            zones.append(Zone("demand", "fvg", float(first["high"]), float(first["low"]),
                              stamp, i - 2, i - 2, 1.0, "FVG"))
        elif float(third["high"]) < float(first["low"]):
            zones.append(Zone("supply", "fvg", float(first["low"]), float(first["high"]),
                              stamp, i - 2, i - 2, 1.0, "FVG"))
    return zones


def _body_ratio(row: pd.Series) -> float:
    candle_range = float(row["high"] - row["low"])
    return abs(float(row["close"] - row["open"])) / candle_range if candle_range > 0 else 0.0


def detect_base_leg_zones(
    df: pd.DataFrame,
    max_base: int = 5,
    range_lookback: int = 20,
    leg_body_ratio: float = 0.75,
    base_body_ratio: float = 0.50,
    expansion: float = 1.20,
) -> list[Zone]:
    """Detect simple DBR/RBR/RBD/DBD structures using closed OHLC candles.

    A base is 1..max_base candles with body/range <= base_body_ratio.
    The candle before the base is leg-in; the candle after is leg-out.
    Leg-out must have body/range >= leg_body_ratio and range >= expansion
    times the median recent range. This is a transparent mechanical proxy.
    """
    _valid_ohlc(df)
    if max_base < 1 or max_base > 5:
        raise ValueError("max_base must be between 1 and 5")
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
            # The ebook defines leg-in as a directional leg candle too;
            # unlike leg-out, it need not be range-expanded.
            if _body_ratio(leg_in) < leg_body_ratio:
                continue
            out_range = float(ranges.iloc[leg_out_idx])
            median = median_ranges.iloc[leg_out_idx]
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

            # Demand proximal is above distal; supply proximal is below distal.
            if kind == "demand" and proximal <= distal:
                continue
            if kind == "supply" and proximal >= distal:
                continue
            strength = min(1.0, _body_ratio(leg_out) * min(out_range / float(median), 2.0) / 2.0)
            stamp = str(df.iloc[leg_out_idx].get("timestamp", leg_out_idx))
            zones.append(Zone(kind, "base_leg", proximal, distal, stamp,
                              start, end, strength, pattern))
            seen.add((start, end))

    # Deduplicate overlapping detections from alternative base lengths.
    unique: dict[tuple, Zone] = {}
    for z in zones:
        key = (z.kind, round(z.proximal, 8), round(z.distal, 8), z.base_start, z.base_end)
        unique[key] = z
    return list(unique.values())
