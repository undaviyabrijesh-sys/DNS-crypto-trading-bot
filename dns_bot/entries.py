from __future__ import annotations

import pandas as pd


def atr_3m(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = df['close'].shift(1)
    tr = pd.concat([df['high'] - df['low'], (df['high'] - prev).abs(), (df['low'] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def find_entry_setups(candles_3m: pd.DataFrame, zones_15m: list, buffer_atr: float = 0.25):
    """Closed 3m tap/reclaim entries using 15m zones. Entry uses next bar open."""
    required = {'timestamp', 'open', 'high', 'low', 'close'}
    if not required.issubset(candles_3m.columns):
        raise ValueError(f'Missing columns: {sorted(required - set(candles_3m.columns))}')
    if len(candles_3m) < 16:
        return []
    df = candles_3m.reset_index(drop=True).copy()
    df['atr'] = atr_3m(df)
    results = []
    for zone in zones_15m:
        kind = str(zone.kind).lower()
        if kind not in ('demand', 'supply') or str(getattr(zone, 'status', 'fresh')).lower() == 'broken':
            continue
        low, high = sorted((float(zone.proximal), float(zone.distal)))
        origin = pd.to_datetime(getattr(zone, 'created_at', None), utc=True, errors='coerce')
        indices = df.index[df.timestamp >= origin] if pd.notna(origin) else df.index
        if len(indices) == 0:
            continue
        tapped = False
        tap_time = None
        for i in range(max(14, int(indices[0])), len(df) - 1):
            c = df.iloc[i]
            if pd.isna(c.atr):
                continue
            if not tapped and float(c.low) <= high and float(c.high) >= low:
                tapped, tap_time = True, str(c.timestamp)
            if not tapped:
                continue
            close = float(c.close)
            if kind == 'demand':
                confirmed, side = close > high, 'LONG'
                stop = low - float(c.atr) * buffer_atr
            else:
                confirmed, side = close < low, 'SHORT'
                stop = high + float(c.atr) * buffer_atr
            if not confirmed:
                if (kind == 'demand' and close < low) or (kind == 'supply' and close > high):
                    tapped, tap_time = False, None
                continue
            entry = float(df.iloc[i + 1].open)
            risk = entry - stop if side == 'LONG' else stop - entry
            if risk <= 0:
                break
            target_2r = entry + 2 * risk if side == 'LONG' else entry - 2 * risk
            candidates = []
            for other in zones_15m:
                if str(getattr(other, 'status', 'fresh')).lower() == 'broken':
                    continue
                ol, oh = sorted((float(other.proximal), float(other.distal)))
                if side == 'LONG' and str(other.kind).lower() == 'supply' and ol > entry:
                    candidates.append(ol)
                if side == 'SHORT' and str(other.kind).lower() == 'demand' and oh < entry:
                    candidates.append(oh)
            final_target = (min(candidates) if side == 'LONG' else max(candidates)) if candidates else None
            if final_target is not None:
                rr_zone = (final_target - entry) / risk if side == 'LONG' else (entry - final_target) / risk
                if rr_zone < 2:
                    final_target = None
            else:
                rr_zone = None
            results.append({'side': side, 'zone': str(getattr(zone, 'pattern', kind)), 'zone_low': low,
                'zone_high': high, 'tap_time': tap_time, 'confirmation_time': str(c.timestamp),
                'entry': entry, 'stop': stop, 'target_1_2r': target_2r, 'final_target': final_target,
                'risk': risk, 'atr_3m': float(c.atr), 'buffer': float(c.atr) * buffer_atr,
                'rr_to_zone': rr_zone, 'status': 'CONFIRMED · NEXT 3M OPEN'})
            break
    return sorted(results, key=lambda x: x['confirmation_time'], reverse=True)
