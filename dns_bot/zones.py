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
        # A fair-value gap is the untraded space BETWEEN candle 1 and
        # candle 3, not the full range of candle 1.
        if float(third["low"]) > float(first["high"]):
            # Bullish FVG: bottom = first candle high, top = third candle low.
            zones.append(Zone("demand", "fvg", float(third["low"]), float(first["high"]),
                              stamp, i - 2, i - 2, 1.0, "FVG", created_index=i))
        elif float(third["high"]) < float(first["low"]):
            # Bearish FVG: bottom = third candle high, top = first candle low.
            zones.append(Zone("supply", "fvg", float(third["high"]), float(first["low"]),
                              stamp, i - 2, i - 2, 1.0, "FVG", created_index=i))
    return zones


def _body_ratio(row: pd.Series) -> float:
    candle_range = float(row["high"] - row["low"])
    return abs(float(row["close"] - row["open"])) / candle_range if candle_range > 0 else 0.0


def detect_base_leg_zones(df: pd.DataFrame, max_base: int = 6, range_lookback: int = 20,
                          leg_body_ratio: float = 0.60, base_body_ratio: float = 0.55,
                          expansion: float = 1.25, max_leg_out: int = 3) -> list[Zone]:
    """Detect compact-base zones followed by 1-3 candle displacement legs.

    Unlike the first version, the outgoing displacement may take several
    candles. This captures larger institutional-style moves that do not leave
    in one oversized candle. Zone bounds remain anchored to the compact base.
    """
    _valid_ohlc(df)
    if max_base < 1 or max_base > 6:
        raise ValueError("max_base must be between 1 and 6")
    if max_leg_out < 1 or max_leg_out > 5:
        raise ValueError("max_leg_out must be between 1 and 5")

    ranges = (df["high"] - df["low"]).astype(float)
    median_ranges = ranges.rolling(range_lookback, min_periods=3).median()
    zones: list[Zone] = []
    seen: set[tuple[int, int]] = set()

    for base_len in range(1, max_base + 1):
        for start in range(1, len(df) - base_len - 1):
            end = start + base_len - 1
            if (start, end) in seen:
                continue

            base = df.iloc[start:end + 1]
            if not all(_body_ratio(row) <= base_body_ratio for _, row in base.iterrows()):
                continue

            leg_in = df.iloc[start - 1]
            if _body_ratio(leg_in) < leg_body_ratio:
                continue

            # Find the first qualifying displacement after the base. The
            # displacement can be one strong candle or a coordinated 2-3 bar leg.
            selected = None
            for horizon in range(1, max_leg_out + 1):
                leg_end = end + horizon
                if leg_end >= len(df):
                    break
                leg = df.iloc[end + 1:leg_end + 1]
                first_open = float(leg.iloc[0]["open"])
                last_close = float(leg.iloc[-1]["close"])
                move = last_close - first_open
                leg_high = float(leg["high"].max())
                leg_low = float(leg["low"].min())
                leg_range = leg_high - leg_low
                median = median_ranges.iloc[leg_end]
                if pd.isna(median) or leg_range <= 0:
                    continue
                net_body_ratio = abs(move) / leg_range
                # Scale the required move with the number of candles, while
                # remaining sensitive to a genuine multi-candle impulse.
                required_move = float(median) * expansion * (horizon ** 0.5)
                if abs(move) < required_move or net_body_ratio < leg_body_ratio:
                    continue
                selected = (leg_end, move, leg_range, float(median), net_body_ratio)
                break

            if selected is None:
                continue

            leg_end, move, leg_range, median, net_body_ratio = selected
            in_up = float(leg_in["close"]) > float(leg_in["open"])
            out_up = move > 0

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

            displacement_factor = min(1.0, abs(move) / max(median * 3.0, 1e-12))
            strength = min(1.0, displacement_factor * net_body_ratio)
            stamp = str(df.iloc[leg_end].get("timestamp", leg_end))
            zones.append(Zone(kind, "base_leg", proximal, distal, stamp, start, end,
                              strength, pattern, created_index=leg_end))
            seen.add((start, end))

    # Swing-origin zones: a confirmed pivot candle contributes its FULL
    # high-low range, matching discretionary swing-high/swing-low marking.
    # Require a meaningful departure so every tiny pivot is not promoted.
    left_right = 2
    departure_bars = 3
    for pivot in range(left_right, len(df) - left_right):
        row = df.iloc[pivot]
        pivot_high, pivot_low = float(row["high"]), float(row["low"])
        local = df.iloc[pivot - left_right:pivot + left_right + 1]
        median = median_ranges.iloc[pivot]
        if pd.isna(median) or float(median) <= 0:
            continue

        is_swing_high = pivot_high >= float(local["high"].max())
        is_swing_low = pivot_low <= float(local["low"].min())
        confirm_index = pivot + left_right
        departure_end = min(len(df) - 1, pivot + departure_bars)
        after = df.iloc[pivot + 1:departure_end + 1]
        if after.empty:
            continue

        stamp = str(row.get("timestamp", pivot))
        if is_swing_high:
            departure = pivot_low - float(after["close"].min())
            if departure >= float(median) * 1.5:
                strength = min(1.0, departure / max(float(median) * 4.0, 1e-12))
                zones.append(Zone(
                    "supply", "base_leg", pivot_high, pivot_low, stamp,
                    pivot, pivot, strength, "SWING_HIGH",
                    created_index=confirm_index,
                ))
        if is_swing_low:
            departure = float(after["close"].max()) - pivot_high
            if departure >= float(median) * 1.5:
                strength = min(1.0, departure / max(float(median) * 4.0, 1e-12))
                zones.append(Zone(
                    "demand", "base_leg", pivot_high, pivot_low, stamp,
                    pivot, pivot, strength, "SWING_LOW",
                    created_index=confirm_index,
                ))

    # Collapse heavily overlapping same-side zones into one cluster. This
    # removes stacks of nearly identical supply boxes while preserving a
    # distinct swing candle when it is not actually overlapping the cluster.
    zones.sort(key=lambda z: (z.kind, min(z.proximal, z.distal)))
    clustered: list[Zone] = []
    for zone in zones:
        z_low, z_high = sorted((float(zone.proximal), float(zone.distal)))
        match = None
        for existing in reversed(clustered):
            if existing.kind != zone.kind:
                continue
            e_low, e_high = sorted((float(existing.proximal), float(existing.distal)))
            overlap = max(0.0, min(z_high, e_high) - max(z_low, e_low))
            smaller_width = max(1e-12, min(z_high - z_low, e_high - e_low))
            if overlap / smaller_width >= 0.60:
                match = existing
                break
        if match is None:
            clustered.append(zone)
            continue
        m_low, m_high = sorted((float(match.proximal), float(match.distal)))
        merged_low, merged_high = min(m_low, z_low), max(m_high, z_high)
        # Keep the strongest origin metadata while using the union of
        # overlapping price boundaries to represent the shared zone cluster.
        if zone.strength > match.strength:
            match.pattern = zone.pattern if zone.pattern.startswith("SWING_") else "ZONE_CLUSTER"
            match.strength = zone.strength
        elif match.pattern != zone.pattern and not match.pattern.startswith("SWING_"):
            match.pattern = "ZONE_CLUSTER"
        match.proximal = merged_high if match.kind == "demand" else merged_low
        match.distal = merged_low if match.kind == "demand" else merged_high
        match.base_start = min(match.base_start, zone.base_start)
        match.base_end = min(match.base_end, zone.base_end)
        match.created_index = min(match.created_index, zone.created_index)
        match.created_at = min(match.created_at, zone.created_at)

    zones = clustered

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
