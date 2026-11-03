from __future__ import annotations

"""Structure-led demand/supply zones.

A zone is created only after a compact base is followed by a decisive
displacement candle. A close through a prior swing adds quality; it is not
assumed to reveal institutional orders.
"""

import numpy as np
import pandas as pd

from .zones import Zone, ZoneType, _body_ratio, _valid_ohlc


def detect_structure_zones(
    df: pd.DataFrame,
    max_base: int = 4,
    atr_period: int = 14,
    atr_multiple: float = 1.35,
    swing_lookback: int = 12,
    base_body_ratio: float = 0.50,
    leg_body_ratio: float = 0.65,
) -> list[Zone]:
    """Detect compact-base → displacement zones using completed candles only.

    Demand: bullish displacement after a compact base.
    Supply: bearish displacement after a compact base.
    A break of the pre-base swing high/low increases the zone's strength.
    Zone bounds use the base body edge (proximal) and full base extreme
    (distal), matching conventional proximal/distal zone marking.
    """
    _valid_ohlc(df)
    if max_base < 1 or atr_period < 2 or swing_lookback < 2:
        raise ValueError("Invalid structure-zone parameters")

    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    open_ = pd.to_numeric(df["open"], errors="coerce")
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(atr_period, min_periods=max(3, atr_period // 2)).mean()

    found: list[Zone] = []
    seen: set[tuple[int, int, str]] = set()

    for base_len in range(1, max_base + 1):
        for start in range(1, len(df) - base_len):
            end = start + base_len - 1
            leg_idx = end + 1
            key = (start, end, str(leg_idx))
            if key in seen or pd.isna(atr.iloc[leg_idx]):
                continue

            base = df.iloc[start : end + 1]
            if any(_body_ratio(row) > base_body_ratio for _, row in base.iterrows()):
                continue

            leg = df.iloc[leg_idx]
            leg_range = float(high.iloc[leg_idx] - low.iloc[leg_idx])
            if leg_range <= 0:
                continue
            body_ratio = _body_ratio(leg)
            if body_ratio < leg_body_ratio or leg_range < float(atr.iloc[leg_idx]) * atr_multiple:
                continue

            bullish = float(close.iloc[leg_idx]) > float(open_.iloc[leg_idx])
            bearish = float(close.iloc[leg_idx]) < float(open_.iloc[leg_idx])
            if not (bullish or bearish):
                continue

            swing_start = max(0, start - swing_lookback)
            prior = df.iloc[swing_start:start]
            if prior.empty:
                continue
            broke_structure = (
                float(close.iloc[leg_idx]) > float(prior["high"].max())
                if bullish else float(close.iloc[leg_idx]) < float(prior["low"].min())
            )

            if bullish:
                kind: ZoneType = "demand"
                pattern = "DBR" if float(df.iloc[start - 1]["close"]) < float(df.iloc[start - 1]["open"]) else "RBR"
                proximal = float(base[["open", "close"]].max(axis=1).max())
                distal = float(base["low"].min())
            else:
                kind = "supply"
                pattern = "RBD" if float(df.iloc[start - 1]["close"]) > float(df.iloc[start - 1]["open"]) else "DBD"
                proximal = float(base[["open", "close"]].min(axis=1).min())
                distal = float(base["high"].max())

            if (kind == "demand" and proximal <= distal) or (kind == "supply" and proximal >= distal):
                continue

            expansion = min(2.5, leg_range / max(float(atr.iloc[leg_idx]), 1e-12))
            displacement_quality = min(1.0, 0.55 * body_ratio + 0.30 * (expansion / 2.5))
            strength = min(1.0, displacement_quality + (0.15 if broke_structure else 0.0))
            stamp = str(df.iloc[leg_idx].get("timestamp", leg_idx))
            found.append(
                Zone(
                    kind=kind,
                    method="structure",
                    proximal=proximal,
                    distal=distal,
                    created_at=stamp,
                    base_start=start,
                    base_end=end,
                    strength=round(strength, 4),
                    pattern=pattern,
                    created_index=leg_idx,
                )
            )
            seen.add(key)

    # Suppress near-identical nested detections; keep the stronger candidate.
    ranked = sorted(found, key=lambda z: z.strength, reverse=True)
    selected: list[Zone] = []
    for zone in ranked:
        zlo, zhi = sorted((zone.proximal, zone.distal))
        duplicate = False
        for prior in selected:
            if prior.kind != zone.kind:
                continue
            plo, phi = sorted((prior.proximal, prior.distal))
            overlap = max(0.0, min(zhi, phi) - max(zlo, plo))
            smaller_width = min(zhi - zlo, phi - plo)
            if smaller_width > 0 and overlap / smaller_width >= 0.70:
                duplicate = True
                break
        if not duplicate:
            selected.append(zone)

    return sorted(selected, key=lambda z: z.created_index)
